import concurrent.futures
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from magicgui import widgets
from qtpy.QtCore import QTimer
from ruamel.yaml import YAML

# This assumes you have a JobStatusWidget defined elsewhere in your project.
from widgets.job_status import JobStatusWidget


class PyCurvWidget(widgets.Container):
    """
    Widget for pycurv curvature measurement that runs analysis and leaves
    result files in the main working directory.
    """

    def __init__(self, experiment_manager):
        super().__init__(layout='vertical', labels=True)
        self.experiment_manager = experiment_manager
        self.vtp_checkboxes = []
        self.is_running = False

        # --- UI Elements ---
        header = widgets.Label(value='<b>Curvature Measurement Settings</b>')

        settings_container = widgets.Container(layout='vertical', labels=True)
        settings_container.native.layout().setSpacing(5)
        settings_container.native.layout().setContentsMargins(3, 3, 3, 3)

        self.radius_hit_input = widgets.SpinBox(value=8, min=1, max=20, label='Radius Hit')
        self.min_component_input = widgets.SpinBox(value=30, min=1, max=1000, label='Min Component')
        self.exclude_borders_input = widgets.SpinBox(value=1, min=0, max=100, label='Exclude Borders')

        settings_container.extend([
            self.radius_hit_input,
            self.min_component_input,
            self.exclude_borders_input,
        ])

        self.vtp_list_header_label = widgets.Label(value="<b>VTP Files to Process:</b>")
        self.select_all_vtp_checkbox = widgets.CheckBox(text="Select/Deselect All")
        self.select_all_vtp_checkbox.changed.connect(self._on_select_all_changed)
        
        # Add refresh button
        self.refresh_btn = widgets.PushButton(text='Refresh VTP List')
        self.refresh_btn.clicked.connect(self._populate_vtp_file_list)
        
        self.vtp_file_list_container = widgets.Container(layout='vertical')

        self.submit_btn = widgets.PushButton(text='Run Curvature Analysis')
        self.status = JobStatusWidget()
        
        self.submit_btn.clicked.connect(self._run_job)

        self.extend([
            header,
            settings_container,
            self.vtp_list_header_label,
            self.select_all_vtp_checkbox,
            self.refresh_btn,
            self.vtp_file_list_container,
            self.submit_btn,
            self.status
        ])

        if hasattr(self.experiment_manager, 'config_loaded'):
            self.experiment_manager.config_loaded.connect(self._on_config_loaded)
            if self.experiment_manager.current_config:
                self._on_config_loaded()
        else:
            print("[PyCurvWidget] ExperimentManager does not have 'config_loaded' signal.")

    def _on_select_all_changed(self, event=None):
        """Handles the 'Select/Deselect All' checkbox change event."""
        is_checked = self.select_all_vtp_checkbox.value
        for checkbox in self.vtp_checkboxes:
            checkbox.value = is_checked

    def _populate_vtp_file_list(self):
        """Populates the list of VTP files with checkboxes."""
        self.vtp_file_list_container.clear()
        self.vtp_checkboxes.clear()
        try:
            if not self.experiment_manager.current_config:
                self.vtp_file_list_container.append(widgets.Label(value="Experiment configuration not loaded."))
                return

            # Construct experiment directory the same way as mesh tab
            try:
                exp_dir = Path(self.experiment_manager.work_dir.value) / self.experiment_manager.experiment_name.currentText()
            except Exception as e:
                self.vtp_file_list_container.append(widgets.Label(value=f"Could not determine experiment directory: {e}"))
                return

            # Look for VTP files in the main directory and a 'meshes' or 'results' subdirectory
            vtp_files = sorted(list(exp_dir.glob('*.surface.vtp')) + list(exp_dir.glob('*.SURFACE.VTP')))
            
            if not vtp_files and (exp_dir / 'meshes').exists():
                 vtp_files.extend(sorted(list((exp_dir / 'meshes').glob('*.surface.vtp')) + 
                                    list((exp_dir / 'meshes').glob('*.SURFACE.VTP'))))
            
            if not vtp_files and (exp_dir / 'results').exists():
                vtp_files.extend(sorted(list((exp_dir / 'results').glob('*.surface.vtp')) + 
                                   list((exp_dir / 'results').glob('*.SURFACE.VTP'))))
            
            if not vtp_files:
                self.vtp_file_list_container.append(widgets.Label(value="No VTP files found. Generate surface meshes first."))
                return

            # Add a label showing how many files were found
            self.vtp_file_list_container.append(widgets.Label(value=f"Found {len(vtp_files)} VTP file(s):"))
            
            for vtp_file in vtp_files:
                checkbox = widgets.CheckBox(text=vtp_file.name)
                checkbox.file_path = str(vtp_file)
                self.vtp_checkboxes.append(checkbox)
                self.vtp_file_list_container.append(checkbox)
            
        except Exception as e:
            self.vtp_file_list_container.append(widgets.Label(value=f"Error loading files: {e}"))
            print(f"[PyCurvWidget] Error populating VTP file list: {e}")
            import traceback
            traceback.print_exc()

    def _on_config_loaded(self):
        """Update UI when experiment is loaded or resumed."""
        try:
            self.status.update_status('Ready')
            self.status.update_progress(0)
            self._populate_vtp_file_list()
            
            if self.experiment_manager.current_config:
                exp_config = self.experiment_manager.current_config
                curvature_settings = exp_config.get('curvature_measurements', {})
                self.radius_hit_input.value = curvature_settings.get('radius_hit', 8)
                self.min_component_input.value = curvature_settings.get('min_component', 30)
                self.exclude_borders_input.value = curvature_settings.get('exclude_borders', 1)
        except Exception as e:
            print(f"[PyCurvWidget] Error in _on_config_loaded: {e}")

    def _update_config(self):
        """Update the YAML config file with current widget values."""
        if not self.experiment_manager.current_config:
            raise ValueError("Experiment configuration not loaded.")

        # Construct experiment directory the same way as mesh tab
        exp_dir = Path(self.experiment_manager.work_dir.value) / self.experiment_manager.experiment_name.currentText()
        config_path = exp_dir / 'config.yml'

        pycurv_specific_config_data = {
            'work_dir': str(exp_dir) + os.sep,
            'cores': self.experiment_manager.current_config.get('cores', 1),
            'curvature_measurements': {
                'radius_hit': self.radius_hit_input.value,
                'min_component': self.min_component_input.value,
                'exclude_borders': self.exclude_borders_input.value,
            }
        }
        
        yaml = YAML()
        yaml.preserve_quotes = True
        with open(config_path, 'w') as f:
            yaml.dump(pycurv_specific_config_data, f)
        
        return config_path

    def _run_job(self):
        """Start the curvature analysis in a background thread."""
        if self.is_running:
            print("[PyCurvWidget] A job is already in progress. Please wait.")
            return

        self.is_running = True
        self.submit_btn.enabled = False
        self.status.update_status('Running...')
        self.status.update_progress(0)
        
        threading.Thread(target=self._run_job_worker, daemon=True).start()

    def _run_job_worker(self):
        """The core worker function that runs the analysis."""
        try:
            config_path = self._update_config()
            exp_config = self.experiment_manager.current_config
            work_dir = Path(exp_config.get('work_dir')).resolve()
            base_work_dir = work_dir.parent
            pycurv_script_path = base_work_dir.parent / 'run_pycurv.py'

            if not pycurv_script_path.exists():
                print(f"[ERROR] Script not found at {pycurv_script_path}")
                self.status.update_status('Error: run_pycurv.py not found')
                return

            selected_vtp_files = sorted(list(set([cb.file_path for cb in self.vtp_checkboxes if cb.value])))

            if not selected_vtp_files:
                self.status.update_status('No VTP files selected')
                return

            total_files = len(selected_vtp_files)
            processed_count = 0
            success_count = 0
            lock = threading.Lock()
            max_workers = min(exp_config.get('cores', 1), total_files)
            
            status_msg = f'Processing {total_files} files using {max_workers} workers...'
            self.status.update_status(status_msg)
            print(status_msg)

            def process_vtp_file(vtp_file_path):
                vtp_file = Path(vtp_file_path)
                # The vtp_file_arg needs to be relative to where the script is run from (work_dir)
                # If the file is in a subdirectory, the path needs to reflect that.
                try:
                    vtp_file_arg = vtp_file.relative_to(work_dir)
                except ValueError:
                    # If the file is not in work_dir, we can't make a relative path.
                    # This might happen if files are in various subdirs.
                    # The script itself might handle absolute paths, but let's stick to relative for consistency.
                    print(f"[ERROR] File {vtp_file} is not inside the working directory {work_dir}.")
                    return {'file_name': vtp_file.name, 'return_code': -1}

                cmd = [sys.executable, "-u", str(pycurv_script_path), str(config_path), str(vtp_file_arg)]
                
                print(f"--- Starting: {vtp_file.name} ---")
                
                try:
                    subprocess.run(cmd, cwd=work_dir, check=True, text=True)
                    print(f"--- Finished Successfully: {vtp_file.name} ---")
                    return {'file_name': vtp_file.name, 'return_code': 0}

                except subprocess.CalledProcessError:
                    print(f"[ERROR] Subprocess for {vtp_file.name} failed. Check terminal output for details.")
                    return {'file_name': vtp_file.name, 'return_code': 1}
                except Exception as e:
                    print(f"[ERROR] An unexpected error occurred while processing {vtp_file.name}: {e}")
                    return {'file_name': vtp_file.name, 'return_code': -1}

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
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
        self._populate_vtp_file_list()

    def on_mesh_generation_complete(self):
        """Handle mesh generation completion signal in a thread-safe way"""
        QTimer.singleShot(0, self._populate_vtp_file_list)