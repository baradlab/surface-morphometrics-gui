import concurrent.futures
import copy
import os
import subprocess
import sys
import threading
from pathlib import Path

from magicgui import widgets
from qtpy.QtCore import QTimer
from ruamel.yaml import YAML
from qtpy.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QCheckBox, QLabel, QPushButton, QHBoxLayout, QMessageBox
from ..utils.archive_utils import check_and_archive_outputs
from ..utils.script_resolver import (
    resolve_cli_runner,
    CLI_MISSING_MESSAGE,
    PYCURV,
    resolve_work_dir,
    cli_work_dir,
)

# This assumes you have a JobStatusWidget defined elsewhere in your project.
from ..widgets.job_status import JobStatusWidget


class PyCurvWidget(QWidget):
    """
    Unified QWidget for pycurv curvature measurement, including settings, VTP file list, and controls.
    """
    def __init__(self, experiment_manager):
        super().__init__()
        self.experiment_manager = experiment_manager
        self.vtp_checkboxes = []
        self.is_running = False

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        self.setLayout(main_layout)

        # --- Settings section (magicgui widgets, use .native) ---
        settings_container = widgets.Container(layout='vertical', labels=True)
        settings_container.native.layout().setSpacing(5)
        settings_container.native.layout().setContentsMargins(3, 3, 3, 3)
        self.radius_hit_input = widgets.SpinBox(value=9, min=1, max=500, label='Radius Hit')
        self.min_component_input = widgets.SpinBox(value=30, min=1, max=1000, label='Min Component')
        self.exclude_borders_input = widgets.SpinBox(value=1, min=0, max=100, label='Exclude Borders')
        self.n_jobs_input = widgets.SpinBox(value=1, min=1, max=128, label='Concurrent Jobs (Parallel Files)')
        self.n_jobs_input.tooltip = "Number of files to process simultaneously. 'Cores' setting controls threads per file."
        settings_container.extend([
            self.radius_hit_input,
            self.min_component_input,
            self.exclude_borders_input,
            self.n_jobs_input
        ])
        main_layout.addWidget(QLabel("<b>Curvature Measurement Settings</b>"))
        main_layout.addWidget(settings_container.native)

        # --- VTP file list section (pure Qt) ---
        self.vtp_section_widget = QWidget()
        self.vtp_section_layout = QVBoxLayout()
        self.vtp_section_layout.setContentsMargins(0, 0, 0, 0)
        self.vtp_section_widget.setLayout(self.vtp_section_layout)
        self.vtp_list_header_label_qt = QLabel("<b>VTP Files to Process:</b>")
        self.vtp_list_header_label_qt.setTextFormat(1)  # Qt.RichText
        self.vtp_section_layout.addWidget(self.vtp_list_header_label_qt)
        self.select_all_vtp_checkbox_qt = QCheckBox("Select/Deselect All")
        self.select_all_vtp_checkbox_qt.stateChanged.connect(self._on_select_all_changed)
        self.vtp_section_layout.addWidget(self.select_all_vtp_checkbox_qt)
        self.refresh_btn_qt = QPushButton('Refresh VTP List')
        self.refresh_btn_qt.clicked.connect(self._populate_vtp_file_list)
        self.vtp_section_layout.addWidget(self.refresh_btn_qt)
        self.vtp_file_list_widget = QWidget()
        self.vtp_file_list_layout = QVBoxLayout()
        self.vtp_file_list_layout.setContentsMargins(0, 0, 0, 0)
        self.vtp_file_list_widget.setLayout(self.vtp_file_list_layout)
        self.vtp_file_list_scroll = QScrollArea()
        self.vtp_file_list_scroll.setWidgetResizable(True)
        self.vtp_file_list_scroll.setWidget(self.vtp_file_list_widget)
        self.vtp_file_list_scroll.setMinimumHeight(100)
        self.vtp_file_list_scroll.setMaximumHeight(300)
        self.vtp_section_layout.addWidget(self.vtp_file_list_scroll)
        main_layout.addWidget(self.vtp_section_widget)

        # --- Submit button and status (magicgui widgets, use .native) ---
        self.submit_btn = widgets.PushButton(text='Run Curvature Analysis')
        self.status = JobStatusWidget()
        self.submit_btn.clicked.connect(self._run_job)
        main_layout.addWidget(self.submit_btn.native)
        main_layout.addWidget(self.status.native)
        


        if hasattr(self.experiment_manager, 'config_loaded'):
            self.experiment_manager.config_loaded.connect(self._on_config_loaded)
            if self.experiment_manager.current_config:
                self._on_config_loaded()
        else:
            print("[PyCurvWidget] ExperimentManager does not have 'config_loaded' signal.")

    def _on_select_all_changed(self, event=None):
        is_checked = self.select_all_vtp_checkbox_qt.isChecked()
        for checkbox in self.vtp_checkboxes:
            checkbox.setChecked(is_checked)

    def _populate_vtp_file_list(self):
        for i in reversed(range(self.vtp_file_list_layout.count())):
            widget = self.vtp_file_list_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)
        self.vtp_checkboxes.clear()
        try:
            if not self.experiment_manager.current_config:
                label = QLabel("Experiment configuration not loaded.")
                self.vtp_file_list_layout.addWidget(label)
                print("[PyCurvWidget] No experiment config loaded.")
                return
            try:
                exp_dir = Path(self.experiment_manager.work_dir.value) / self.experiment_manager.experiment_name.currentText()
                print(f"[PyCurvWidget] Searching for VTP files in: {exp_dir}")
            except Exception as e:
                label = QLabel(f"Could not determine experiment directory: {e}")
                self.vtp_file_list_layout.addWidget(label)
                print(f"[PyCurvWidget] Could not determine experiment directory: {e}")
                return
            # Look where this experiment's outputs live (results/ or the flat
            # exp_dir), then the legacy meshes/ dir as a last resort.
            search_dirs = [resolve_work_dir(exp_dir), exp_dir / 'meshes']
            vtp_files = []
            for d in search_dirs:
                if d.exists():
                    vtp_files = sorted(list(d.glob('*.surface.vtp')) + list(d.glob('*.SURFACE.VTP')))
                    if vtp_files:
                        break
            print(f"[PyCurvWidget] Found VTP files: {[str(f) for f in vtp_files]}")
            if not vtp_files:
                label = QLabel("No VTP files found. Generate surface meshes first.")
                self.vtp_file_list_layout.addWidget(label)
                return
            label = QLabel(f"Found {len(vtp_files)} VTP file(s):")
            self.vtp_file_list_layout.addWidget(label)
            for vtp_file in vtp_files:
                checkbox = QCheckBox(vtp_file.name)
                checkbox.file_path = str(vtp_file)
                self.vtp_checkboxes.append(checkbox)
                self.vtp_file_list_layout.addWidget(checkbox)
            print(f"[PyCurvWidget] Added {len(self.vtp_checkboxes)} checkboxes to the layout.")
            self.vtp_file_list_widget.update()
            self.vtp_file_list_widget.repaint()
            self.vtp_file_list_layout.update()
        except Exception as e:
            label = QLabel(f"Error loading files: {e}")
            self.vtp_file_list_layout.addWidget(label)
            print(f"[PyCurvWidget] Error populating VTP file list: {e}")
            import traceback
            traceback.print_exc()

    def _on_config_loaded(self):
        try:
            self.status.update_status('Ready')
            self.status.update_progress(0)
            self._populate_vtp_file_list()
            if self.experiment_manager.current_config:
                exp_config = self.experiment_manager.current_config
                curvature_settings = exp_config.get('curvature_measurements', {})
                self.radius_hit_input.value = curvature_settings.get('radius_hit', 9)
                self.min_component_input.value = curvature_settings.get('min_component', 30)
                self.exclude_borders_input.value = curvature_settings.get('exclude_borders', 1)
        except Exception as e:
            print(f"[PyCurvWidget] Error in _on_config_loaded: {e}")

    def _update_config(self):
        """Update the YAML config file with current widget values."""
        if not self.experiment_manager.current_config:
            raise ValueError("Experiment configuration not loaded.")

        # Construct experiment directory the same way as mesh tab
        exp_name = self.experiment_manager.experiment_name.currentText()
        exp_dir = Path(self.experiment_manager.work_dir.value) / exp_name
        # Prefer the same config naming as mesh tab; fallback to config.yml if needed
        preferred_config_path = exp_dir / f"{exp_name}_config.yml"
        fallback_config_path = exp_dir / 'config.yml'
        config_path = preferred_config_path if preferred_config_path.exists() else fallback_config_path

        # Load existing config if present; else start with current_config snapshot
        yaml = YAML()
        yaml.preserve_quotes = True
        existing = {}
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    existing = yaml.load(f) or {}
            except Exception:
                existing = {}
        else:
            # If neither exists, use preferred path for new file
            config_path = preferred_config_path
            existing = copy.deepcopy(self.experiment_manager.current_config)

        # All steps read/write a single directory; the trailing separator is
        # required because the CLI concatenates work_dir + basename. Use the
        # layout the surfaces already live in (results/ or the flat exp_dir).
        out_dir = resolve_work_dir(exp_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        existing['work_dir'] = cli_work_dir(out_dir)
        existing['cores'] = self.experiment_manager.cores_input.value()

        # Merge curvature settings
        existing.setdefault('curvature_measurements', {})
        existing['curvature_measurements'].update({
            'radius_hit': self.radius_hit_input.value,
            'min_component': self.min_component_input.value,
            'exclude_borders': self.exclude_borders_input.value,
        })

        # Write back
        with open(config_path, 'w') as f:
            yaml.dump(existing, f)

        return config_path

    def _run_job(self):
        """Start the curvature analysis in a background thread."""
        if self.is_running:
            print("[PyCurvWidget] A job is already in progress. Please wait.")
            return

        # Save current settings to config file
        try:
            config_path = self._update_config()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update config: {e}")
            return
            
        # Resolve the morphometrics CLI (installed package), not a loose script.
        runner = resolve_cli_runner()
        if runner is None:
            QMessageBox.critical(self, "morphometrics CLI not found", CLI_MISSING_MESSAGE)
            print(f"[Error] {CLI_MISSING_MESSAGE}")
            return

        # Collect data from UI in the main thread
        selected_vtp_files = sorted(list(set([cb.file_path for cb in self.vtp_checkboxes if cb.isChecked()])))
        
        if not selected_vtp_files:
            QMessageBox.warning(self, "No Files", "No VTP files selected.")
            return

        # Archive check for PyCurv (Targets 'measurements' to keep data clean)
        # We now generate specific patterns for the selected files to avoid false positive prompts
        try:
             exp_name = self.experiment_manager.experiment_name.currentText()
             exp_dir = Path(self.experiment_manager.work_dir.value) / exp_name
             archive_dir = resolve_work_dir(exp_dir)

             # Generate specific patterns for selected files
             base_patterns = ['*AVV*', '*VV*', '*.log', '*.csv', '*.gt', '*.svg', '*.png']
             specific_patterns = []
             
             for vtp_path in selected_vtp_files:
                 # Extract stem: remove .surface.vtp or .SURFACE.VTP
                 fname = Path(vtp_path).name
                 stem = fname.replace('.surface.vtp', '').replace('.SURFACE.VTP', '')
                 # Add patterns for this stem
                 for pattern in base_patterns:
                     specific_patterns.append(f"{stem}{pattern}")
             
             # Use specific patterns if we have selected files, otherwise fallback 
             patterns_to_check = specific_patterns if specific_patterns else base_patterns

             if not check_and_archive_outputs(self, archive_dir, config_path=config_path, file_patterns=patterns_to_check):
                 print("User cancelled.")
                 return
        except Exception as e:
            print(f"Archive check failed: {e}")
            import traceback
            traceback.print_exc()
            pass

        # Get number of cores
        cores = self.experiment_manager.cores_input.value()

        self.is_running = True
        self.submit_btn.enabled = False
        self.status.update_status('Running...')
        self.status.update_progress(0)
        
        # Pass all necessary data to worker
        job_data = {
            'runner': runner,
            'config_path': config_path,
            'files': selected_vtp_files,
            'cores': cores,
            'radius_hit': self.radius_hit_input.value,
        }
        
        threading.Thread(target=self._run_job_worker, args=(job_data,), daemon=True).start()

    def _run_job_worker(self, job_data):
        """The core worker function that runs the analysis."""
        try:
            runner = job_data['runner']
            config_path = job_data['config_path']
            selected_vtp_files = job_data['files']
            radius_hit = job_data['radius_hit']

            # The CLI reads and writes the experiment's output directory (the
            # saved work_dir). Resolve it the same way _update_config did so the
            # bare-basename surface argument and outputs line up.
            work_dir = resolve_work_dir(Path(config_path).parent).resolve()

            total_files = len(selected_vtp_files)
            processed_count = 0
            success_count = 0
            lock = threading.Lock()
            
            # Explicit N_Jobs Logic
            n_jobs = self.n_jobs_input.value
            cores_per_job = job_data['cores']
            
            # Validation (Warning only)
            total_threads = n_jobs * cores_per_job
            import os
            sys_cores = os.cpu_count() or 1
            if total_threads > sys_cores:
                print(f"[WARNING] Requesting {total_threads} threads on {sys_cores}-core system. System may freeze.")
            
            print(f"Cluster-Style Execution: Launching {n_jobs} parallel jobs.")
            print(f"Each job will use {cores_per_job} cores (Total Load: {total_threads}/{sys_cores}).")
            
            status_msg = f'Processing {total_files} files using {n_jobs} parallel jobs (Cores/Job: {cores_per_job})...'
            self.status.update_status(status_msg)
            print(status_msg)

            def process_vtp_file(vtp_file_path):
                vtp_file = Path(vtp_file_path)
                if not vtp_file.name.endswith('.surface.vtp'):
                    print(f"[ERROR] {vtp_file.name} is not a .surface.vtp file.")
                    return {'file_name': vtp_file.name, 'return_code': -1}

                # curvature.run_pycurv derives the basename by stripping the
                # suffix and builds outputs as work_dir + basename, so the
                # surface argument MUST be a bare filename (no directory).
                # -f skips the interactive core-oversubscription prompt, which
                # would otherwise hang the subprocess forever (no stdin).
                cmd = runner + [PYCURV, str(config_path), vtp_file.name, '-f']

                print(f"--- Starting: {vtp_file.name} ---")

                stem = vtp_file.name[:-len('.surface.vtp')]
                expected_gt = work_dir / f"{stem}.AVV_rh{radius_hit}.gt"
                try:
                    subprocess.run(cmd, cwd=work_dir, check=True, text=True)
                except subprocess.CalledProcessError:
                    print(f"[ERROR] Subprocess for {vtp_file.name} failed. Check terminal output for details.")
                    return {'file_name': vtp_file.name, 'return_code': 1}
                except Exception as e:
                    print(f"[ERROR] An unexpected error occurred while processing {vtp_file.name}: {e}")
                    return {'file_name': vtp_file.name, 'return_code': -1}

                # pycurv catches per-surface errors and still exits 0, so an
                # exit code of 0 does not mean this surface succeeded. Confirm
                # the curvature graph was actually written.
                if not expected_gt.exists():
                    print(f"[ERROR] {vtp_file.name}: pycurv produced no output "
                          f"({expected_gt.name}). The surface likely failed; check the log.")
                    return {'file_name': vtp_file.name, 'return_code': 1}

                print(f"--- Finished Successfully: {vtp_file.name} ---")
                return {'file_name': vtp_file.name, 'return_code': 0}

            with concurrent.futures.ThreadPoolExecutor(max_workers=n_jobs) as executor:
                future_to_file = {executor.submit(process_vtp_file, fp): fp for fp in selected_vtp_files}
                for future in concurrent.futures.as_completed(future_to_file):
                    result = future.result()
                    with lock:
                        processed_count += 1
                        progress = int((processed_count / total_files) * 100)
                        if result and result.get('return_code') == 0:
                            success_count += 1
                            status_msg = f'Success: {result["file_name"]}'
                        else:
                            status_msg = f'Failed: {result["file_name"] if result else "Unknown"}'
                        
                        self.status.update_status(f'({processed_count}/{total_files}) {status_msg}')
                        self.status.update_progress(progress)

            final_msg = f'Completed. See terminal for logs. Successful: {success_count}/{total_files}.'
            self.status.update_status(final_msg)
            print(f"===== {final_msg} =====")

        except Exception as e:
            error_msg = f'A critical error occurred in the job worker: {e}'
            self.status.update_status(f'Error: {e}')
            print(error_msg)
            import traceback
            traceback.print_exc()
        finally:
            QTimer.singleShot(0, self._job_cleanup)

    def _job_cleanup(self):
        """Reset the UI after the job is finished."""
        self.submit_btn.enabled = True
        self.is_running = False
        # Do not auto-refresh list here, as it clears selection

    def on_mesh_generation_complete(self):
        """Handle mesh generation completion signal in a thread-safe way"""
        QTimer.singleShot(0, self._populate_vtp_file_list)