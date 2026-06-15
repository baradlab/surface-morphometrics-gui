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
from qtpy.QtWidgets import QMessageBox, QScrollArea, QVBoxLayout, QWidget
from utils.archive_utils import check_and_archive_outputs
from utils.script_resolver import (
    resolve_cli_runner,
    CLI_MISSING_MESSAGE,
    DISTANCES_ORIENTATIONS,
    get_seg_dir,
    resolve_work_dir,
    cli_work_dir,
)

from widgets.job_status import JobStatusWidget


class IntraListEditor(widgets.Container):
    """Editor for intra membrane list"""
    def __init__(self):
        super().__init__(layout='vertical')
        self.entries = []
        self.add_button = widgets.PushButton(text='Add Membrane')
        self.add_button.clicked.connect(self._add_entry)
        self.extend([self.add_button])

    def _add_entry(self, label=''):
        entry = widgets.LineEdit(value=label)
        remove_button = widgets.PushButton(text='Remove')
        container = widgets.Container(layout='horizontal')
        container.extend([entry, remove_button])

        def remove():
            self.entries.remove((entry, container))
            self.remove(container)

        remove_button.clicked.connect(remove)
        self.entries.append((entry, container))
        self.insert(-1, container)

    def get_values(self):
        return [entry.value for entry, _ in self.entries if entry.value.strip()]

    def set_values(self, values):
        while self.entries:
            _, container = self.entries[0]
            self.entries.pop(0)
            self.remove(container)
        for value in values:
            self._add_entry(value)


class InterDictEditor(widgets.Container):
    """Editor for inter membrane dictionary"""
    def __init__(self):
        super().__init__(layout='vertical')
        # Keyed by an internal token, not the user-facing membrane name —
        # multiple new rows would otherwise collide on key='' and silently
        # overwrite each other.
        self.entries = {}
        self._next_token = 0
        self.add_button = widgets.PushButton(text='Add Membrane Pair')
        self.add_button.clicked.connect(lambda: self._add_entry())
        self.extend([self.add_button])

    def _add_entry(self, key='', values=None):
        if values is None:
            values = []

        key_edit = widgets.LineEdit(value=key, label='Membrane:')
        value_editor = IntraListEditor()
        value_editor.set_values(values)

        remove_button = widgets.PushButton(text='Remove')
        header = widgets.Container(layout='horizontal')
        header.extend([key_edit, remove_button])

        container = widgets.Container(layout='vertical')
        container.extend([header, value_editor])

        token = self._next_token
        self._next_token += 1

        def remove():
            if token in self.entries:
                self.entries.pop(token)
                self.remove(container)

        remove_button.clicked.connect(remove)

        self.entries[token] = (key_edit, value_editor, container)
        self.insert(-1, container)

    def get_values(self):
        return {
            entry[0].value: entry[1].get_values()
            for entry in self.entries.values()
            if entry[0].value.strip()
        }

    def set_values(self, values):
        for entry in list(self.entries.values()):
            self.remove(entry[2])
        self.entries.clear()
        for key, value_list in values.items():
            self._add_entry(key, value_list)


class DistanceOrientationWidget(QWidget):
    """Widget for distance and orientation measurement settings"""

    def __init__(self, experiment_manager):
        super().__init__()
        self.experiment_manager = experiment_manager
        self.is_running = False

        self.container = widgets.Container(layout='vertical', labels=True)
        self.container.native.layout().setContentsMargins(3, 3, 3, 3)
        self.container.native.layout().setSpacing(3)

        scroll_area = QScrollArea()
        scroll_area.setWidget(self.container.native)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scroll_area)

        self.native = self

        # Header container
        header = widgets.Container(widgets=[
            widgets.Label(value='<b>Distance and Orientation Measurements</b>')
        ], layout='vertical')
        header.native.layout().setContentsMargins(0, 0, 0, 0)
        header.native.layout().setSpacing(0)

        # Settings container
        settings = widgets.Container(layout='vertical', labels=True)
        settings.native.layout().setSpacing(5)
        settings.native.layout().setContentsMargins(3, 3, 3, 3)

        # Settings widgets
        self.min_dist = widgets.FloatSpinBox(value=3.0, min=0.0, max=1000.0, step=0.1, label='Min Distance')
        self.max_dist = widgets.FloatSpinBox(value=400.0, min=0.0, max=1000.0, step=0.1, label='Max Distance')
        self.tolerance = widgets.FloatSpinBox(value=0.1, min=0.0, max=1.0, step=0.01, label='Tolerance')
        self.verticality = widgets.CheckBox(value=True, label='Measure Verticality')
        self.relative_orientation = widgets.CheckBox(value=True, label='Measure Relative Orientation')

        # Custom editors for intra/inter measurements
        self.intra_editor = IntraListEditor()
        self.inter_editor = InterDictEditor()

        self.n_jobs_input = widgets.SpinBox(value=1, min=1, max=128, label='Concurrent Jobs (Parallel Files)')
        self.n_jobs_input.tooltip = "Number of files to process simultaneously."

        settings.extend([
            self.min_dist,
            self.max_dist,
            self.tolerance,
            self.verticality,
            self.relative_orientation,
            self.n_jobs_input,
            widgets.Label(value='<b>Intra-membrane Measurements:</b>'),
            self.intra_editor,
            widgets.Label(value='<b>Inter-membrane Measurements:</b>'),
            self.inter_editor
        ])

        # Status and submission button
        self.status = JobStatusWidget()
        self.submit_btn = widgets.PushButton(text='Run Distance/Orientation Analysis')
        self.submit_btn.clicked.connect(self._run_job)

        self.container.extend([
            header,
            settings,
            self.submit_btn,
            self.status
        ])

        # Absorb leftover vertical space at the bottom so the content
        # hugs the top instead of being spread out across the viewport.
        self.container.native.layout().addStretch(1)

        # Connect signal for loading experiment configurations
        if hasattr(self.experiment_manager, 'config_loaded'):
            self.experiment_manager.config_loaded.connect(self._on_config_loaded)
            if self.experiment_manager.current_config:
                self._on_config_loaded()

    def _on_config_loaded(self):
        """Update UI when an experiment is loaded or resumed."""
        try:
            self.status.update_status('Ready')
            self.status.update_progress(0)

            if self.experiment_manager.current_config:
                exp_config = self.experiment_manager.current_config
                distance_settings = exp_config.get('distance_and_orientation_measurements', {})
                self.min_dist.value = distance_settings.get('mindist', 3)
                self.max_dist.value = distance_settings.get('maxdist', 400)
                self.tolerance.value = distance_settings.get('tolerance', 0.1)
                self.verticality.value = distance_settings.get('verticality', True)
                self.relative_orientation.value = distance_settings.get('relative_orientation', True)

                if 'intra' in distance_settings:
                    self.intra_editor.set_values(distance_settings['intra'])
                if 'inter' in distance_settings:
                    self.inter_editor.set_values(distance_settings['inter'])
        except Exception as e:
            print(f"[DistanceOrientationWidget] Error in _on_config_loaded: {e}")

    def _update_config(self):
        """Update the YAML config file with current widget values."""
        if not self.experiment_manager or not self.experiment_manager.current_config:
            raise ValueError("Experiment configuration not loaded.")

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
            # If neither exists, use preferred path for new file (matching PyCurv behavior)
            config_path = preferred_config_path
            existing = copy.deepcopy(self.experiment_manager.current_config)

        # All steps share one output directory (results/ or the flat exp_dir
        # for an adopted CLI project); trailing separator required by the CLI.
        out_dir = resolve_work_dir(exp_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        existing['work_dir'] = cli_work_dir(out_dir)
        
        # Merge distance settings
        existing.setdefault('distance_and_orientation_measurements', {})
        existing['distance_and_orientation_measurements'].update({
            'mindist': self.min_dist.value,
            'maxdist': self.max_dist.value,
            'tolerance': self.tolerance.value,
            'verticality': self.verticality.value,
            'relative_orientation': self.relative_orientation.value,
            'intra': self.intra_editor.get_values(),
            'inter': self.inter_editor.get_values()
        })

        with open(config_path, 'w') as f:
            yaml.dump(existing, f)
        
        return config_path

    def _run_job(self):
        """Starts the analysis job in a background thread."""
        if self.is_running:
            return

        # Strict script location check
        try:
            config_path = self._update_config()
        except FileNotFoundError as e:
            QMessageBox.critical(self.native, "Config Missing", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self.native, "Error", f"Failed to update config: {e}")
            return

        # Resolve the morphometrics CLI (installed package), not a loose script.
        runner = resolve_cli_runner()
        if runner is None:
            QMessageBox.critical(self.native, "morphometrics CLI not found", CLI_MISSING_MESSAGE)
            print(f"[Error] {CLI_MISSING_MESSAGE}")
            return

        # Archive Check (Targets 'measurements' as this is the primary output)
        try:
             work_dir = Path(self.experiment_manager.work_dir.value)
             exp_name = self.experiment_manager.experiment_name.currentText()
             exp_dir = work_dir / exp_name
             archive_config_path = exp_dir / f"{exp_name}_config.yml"
             archive_dir = resolve_work_dir(exp_dir)

             if not check_and_archive_outputs(self.native, archive_dir, config_path=archive_config_path, file_patterns=['*.csv', '*.svg', '*.png'], exclude_patterns=['*AVV*', '*VV*', '*.gt', '*_runtimes.csv']):
                 return
        except Exception as e:
             print(f"Archive check failed: {e}")
             pass

        # Prepare job data
        job_data = {
            'runner': runner,
            'config_path': config_path
        }

        self.is_running = True
        self.submit_btn.enabled = False
        self.status.update_status('Starting...')
        self.status.update_progress(0)

        threading.Thread(target=self._run_job_worker, args=(job_data,), daemon=True).start()

    def _run_job_worker(self, job_data):
        """The core worker function that runs the analysis."""
        try:
            # Unpack data
            runner = job_data['runner']
            config_path = job_data['config_path']

            # Read config again in thread to get paths (safe, reading file)
            yaml = YAML()
            with open(config_path, 'r') as f:
                exp_config = yaml.load(f)

            # Note: _update_config set 'work_dir' to the results directory in the saved file.
            work_dir = Path(exp_config.get('work_dir')).resolve()
            data_dir = Path(get_seg_dir(exp_config)).resolve()

            mrc_files = [f for f in data_dir.glob('*.mrc') if not f.name.startswith('._')]
            if not mrc_files:
                self.status.update_status('Error: No MRC files found')
                return

            total_files = len(mrc_files)
            processed_count = 0
            success_count = 0
            lock = threading.Lock()
            
            # Explicit N_Jobs Logic
            n_jobs = self.n_jobs_input.value
            
            # Distance scripts are single-threaded python, but may use OMP libraries.
            # We assume 1 core per job primarily, unless configured otherwise in environment.
            cores_per_job = 1
            
            # Validation (Warning only)
            total_threads = n_jobs * cores_per_job
            import os
            sys_cores = os.cpu_count() or 1
            if total_threads > sys_cores:
                print(f"[WARNING] Requesting {total_threads} jobs on {sys_cores}-core system. System may freeze.")
            
            print(f"Cluster-Style Execution: Launching {n_jobs} parallel jobs.")
            status_msg = f'Processing {total_files} files using {n_jobs} parallel jobs...'
            self.status.update_status(status_msg)
            print(status_msg)
            
            def process_mrc_file(mrc_file):
                """
                Processes a single file. The distance script only uses the
                mrc filename to derive the basename of the existing pycurv
                graph files (e.g. "TE1.mrc" -> "TE1_OMM.AVV_rh9.gt") — it
                never opens the mrc — so we pass the bare name directly.
                Prefixing it (as the mesh tab does) would point the script at
                graph files that don't exist; it would then skip every
                measurement and still exit 0, a silent no-op.
                """

                # -f skips the interactive core-oversubscription prompt that
                # would otherwise hang the subprocess forever (no stdin).
                cmd = runner + [DISTANCES_ORIENTATIONS, str(config_path), mrc_file.name, '-f']
                print(f"--- Running for: {mrc_file.name} ---")
                print(f"Executing: {' '.join(cmd)}")

                try:
                    result = subprocess.run(
                        cmd,
                        cwd=data_dir,
                        check=True,
                        text=True,
                        capture_output=True
                    )
                    if result.stdout: print(result.stdout)
                    if result.stderr: print(f"STDERR for {mrc_file.name}:\n{result.stderr}")

                    # The script exits 0 even when it finds no graph files, so
                    # treat "No file found" in its output as a failure rather
                    # than reporting a misleading success.
                    if "No file found" in (result.stdout or ""):
                        print(f"[ERROR] No matching pycurv graph files for {mrc_file.name}. "
                              "Run the PyCurv step first.")
                        return {'file_name': mrc_file.name, 'return_code': 1}

                    print(f"--- Finished Successfully: {mrc_file.name} ---")
                    return {'file_name': mrc_file.name, 'return_code': 0}
                except subprocess.CalledProcessError as e:
                    error_details = f"STDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"
                    print(f"[ERROR] Subprocess for {mrc_file.name} failed.\n{error_details}")
                    return {'file_name': mrc_file.name, 'return_code': e.returncode}

            with concurrent.futures.ThreadPoolExecutor(max_workers=n_jobs) as executor:
                future_to_file = {executor.submit(process_mrc_file, f): f for f in mrc_files}
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

            final_msg = f'Completed. Successful: {success_count}/{total_files}. See terminal for logs.'
            self.status.update_status(final_msg)
            print(f"===== {final_msg} =====")

        except Exception as e:
            error_msg = f'A critical error occurred in the job worker: {e}'
            self.status.update_status(f'Error: {e}')
            import traceback
            print(error_msg)
            traceback.print_exc()
        finally:
            QTimer.singleShot(0, self._job_cleanup)
            
    def _job_cleanup(self):
        """Resets the UI after the job is finished or has failed."""
        self.is_running = False
        self.submit_btn.enabled = True