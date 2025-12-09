import concurrent.futures
import copy
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from magicgui import widgets
from qtpy.QtCore import QTimer
from ruamel.yaml import YAML
from qtpy.QtWidgets import QMessageBox
from utils.archive_utils import check_and_archive_outputs

# These are assumed to be in your project structure
from morphometrics_config import IntraListEditor, InterDictEditor
from widgets.job_status import JobStatusWidget


class DistanceOrientationWidget(widgets.Container):
    """Widget for distance and orientation measurement settings"""

    def __init__(self, experiment_manager):
        super().__init__(layout='vertical', labels=True)
        self.experiment_manager = experiment_manager
        self.is_running = False

        # Header container
        header = widgets.Container(widgets=[
            widgets.Label(value='<b>Distance and Orientation Measurements</b>')
        ], layout='vertical')

        # Settings container
        settings = widgets.Container(layout='vertical', labels=True)
        settings.native.layout().setSpacing(5)
        settings.native.layout().setContentsMargins(3, 3, 3, 3)

        # Settings widgets
        self.min_dist = widgets.SpinBox(value=3, min=0, max=1000, label='Min Distance')
        self.max_dist = widgets.SpinBox(value=400, min=0, max=1000, label='Max Distance')
        self.tolerance = widgets.FloatSpinBox(value=0.1, min=0.0, max=1.0, step=0.01, label='Tolerance')
        self.verticality = widgets.CheckBox(value=True, label='Measure Verticality')
        self.relative_orientation = widgets.CheckBox(value=True, label='Measure Relative Orientation')

        # Custom editors for intra/inter measurements
        self.intra_editor = IntraListEditor()
        self.inter_editor = InterDictEditor()

        settings.extend([
            self.min_dist,
            self.max_dist,
            self.tolerance,
            self.verticality,
            self.relative_orientation,
            widgets.Label(value='<b>Intra-membrane Measurements:</b>'),
            self.intra_editor,
            widgets.Label(value='<b>Inter-membrane Measurements:</b>'),
            self.inter_editor
        ])

        # Status and submission button
        self.status = JobStatusWidget()
        self.submit_btn = widgets.PushButton(text='Run Distance/Orientation Analysis')
        self.submit_btn.clicked.connect(self._run_job)

        self.extend([
            header,
            settings,
            self.submit_btn,
            self.status
        ])

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

        # Distance tab specific: work_dir should point to results
        results_dir = exp_dir / 'results'
        results_dir.mkdir(exist_ok=True)
        existing['work_dir'] = str(results_dir) + os.sep
        
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

        # Manually read config to find script_location without triggering global refresh
        script_location = None
        try:
            yaml = YAML()
            with open(config_path, 'r') as f:
                loaded_config = yaml.load(f) or {}
            script_location = loaded_config.get('script_location')
        except Exception as e:
            print(f"[DistanceWidget] Error reading config for script_location: {e}")
        
        script_path = None
        if script_location:
             script_path = Path(script_location) / 'measure_distances_orientations.py'
        
        if not script_path or not script_path.exists():
            error_msg = (
                "Script 'measure_distances_orientations.py' not found.\n\n"
                "Please make sure to place the config file you are using as a template "
                "in the Surface Morphometrics directory.\n\n"
                "If it is already placed there, please check the 'script_location' path "
                "in the experiment-specific config file.\n\n"
                f"Checked location: {script_path if script_path else 'Not defined'}"
            )
            QMessageBox.critical(self.native, "Script Not Found", error_msg)
            print(f"[Error] {error_msg}")
            return

        # Archive Check (Targets 'measurements' as this is the primary output)
        try:
             work_dir = Path(self.experiment_manager.work_dir.value)
             exp_name = self.experiment_manager.experiment_name.currentText()
             exp_dir = work_dir / exp_name
             config_path = exp_dir / f"{exp_name}_config.yml"
             results_dir = exp_dir / 'results'
             
             if not check_and_archive_outputs(self.native, results_dir, config_path=config_path, file_patterns=['*.csv', '*.svg', '*.png'], exclude_patterns=['*AVV*', '*VV*', '*.gt', '*_runtimes.csv']):
                 return
        except Exception as e:
             print(f"Archive check failed: {e}")
             pass

        # Prepare job data
        job_data = {
            'script_path': script_path,
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
            script_path = job_data['script_path']
            config_path = job_data['config_path']
            
            # Read config again in thread to get paths (safe, reading file)
            yaml = YAML()
            with open(config_path, 'r') as f:
                exp_config = yaml.load(f)
                
            # Note: _update_config set 'work_dir' to the results directory in the saved file.
            work_dir = Path(exp_config.get('work_dir')).resolve() 
            data_dir = Path(exp_config.get('data_dir')).resolve()

            # Using passed script_path
            if not script_path.exists():
                self.status.update_status('Error: measure_distances_orientations.py not found')
                return

            mrc_files = [f for f in data_dir.glob('*.mrc') if not f.name.startswith('._')]
            if not mrc_files:
                self.status.update_status('Error: No MRC files found')
                return

            total_files = len(mrc_files)
            processed_count = 0
            success_count = 0
            lock = threading.Lock()
            max_workers = min(exp_config.get('cores', 1), total_files)

            self.status.update_status(f'Processing {total_files} files...')
            
            def process_mrc_file(mrc_file):
                """
                Processes a single file using a temporary symlink to trick
                the script into generating the correct filenames.
                """

                
                exp_name = work_dir.parent.name
                if work_dir.name != 'results':
                     # Fallback if structure is different
                     exp_name = work_dir.name
                
                link_name = f"{exp_name}{mrc_file.name}"
                link_path = data_dir / link_name
                
                cmd = [sys.executable, "-u", str(script_path), str(config_path), link_name]
                print(f"--- Running for: {mrc_file.name} (using link: {link_name}) ---")
                print(f"Executing: {' '.join(cmd)}")
                
                try:
                    # Create the temporary symlink
                    if os.path.exists(link_path):
                        os.remove(link_path) # Remove old link if it exists
                    os.symlink(mrc_file, link_path)
                    
                    result = subprocess.run(
                        cmd,
                        cwd=data_dir,
                        check=True,
                        text=True,
                        capture_output=True
                    )
                    if result.stdout: print(result.stdout)
                    if result.stderr: print(f"STDERR for {mrc_file.name}:\n{result.stderr}")
                    
                    print(f"--- Finished Successfully: {mrc_file.name} ---")
                    return {'file_name': mrc_file.name, 'return_code': 0}
                except subprocess.CalledProcessError as e:
                    error_details = f"STDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"
                    print(f"[ERROR] Subprocess for {mrc_file.name} failed.\n{error_details}")
                    return {'file_name': mrc_file.name, 'return_code': e.returncode}
                finally:
                    if os.path.islink(link_path):
                        os.remove(link_path)

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
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