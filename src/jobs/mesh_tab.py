from pathlib import Path
import re
import subprocess
import sys
import os
from magicgui import widgets
from widgets.job_status import JobStatusWidget
from ruamel.yaml import YAML
from qtpy.QtCore import QTimer, Signal, QObject
from qtpy.QtWidgets import QWidget, QMessageBox, QScrollArea, QVBoxLayout
import threading
from utils.archive_utils import check_and_archive_outputs
from utils.script_resolver import resolve_cli_runner, CLI_MISSING_MESSAGE, MAKE_MESHES

class MeshGenerationWidget(QWidget):
    """Widget for surface mesh generation settings"""
    
    # Signal to notify when mesh generation is complete
    mesh_generation_complete = Signal()
    
    def __init__(self, experiment_manager):
        super().__init__()
        self.experiment_manager = experiment_manager

        self.container = widgets.Container(layout='vertical', labels=True)

        # Wrap the container in a scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.container.native)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_area)

        self.native = self  # The QWidget itself is now the native widget
        
        # Create header container
        header = widgets.Container(widgets=[
            widgets.Label(value='<b>Surface Generation Settings</b>')
        ], layout='vertical')
        
        # Create settings container
        settings = widgets.Container(layout='vertical', labels=True)
        settings.native.layout().setSpacing(5)
        settings.native.layout().setContentsMargins(3, 3, 3, 3)
        
        # Create settings widgets
        self.angstroms = widgets.CheckBox(value=False, label='Angstrom Scaling')
        self.ultrafine = widgets.CheckBox(value=True, label='Ultrafine Surface (High Quality, Slow)')
        self.target_area = widgets.FloatSpinBox(value=1.0, min=0.1, max=100.0, step=0.1, label='Target Triangle Area')
        self.isotropic_remesh = widgets.CheckBox(value=False, label='Isotropic Remesh')
        self.simplify = widgets.CheckBox(value=False, label='Simplify Surface')
        self.max_triangles = widgets.SpinBox(value=300000, min=1000, max=1000000, label='Max Triangles')
        self.extrapolation_distance = widgets.FloatSpinBox(value=1.5, min=0.1, max=10.0, step=0.1, label='Extrapolation Distance')
        self.octree_depth = widgets.SpinBox(value=7, min=1, max=15, label='Octree Depth')
        self.point_weight = widgets.FloatSpinBox(value=0.7, min=0.1, max=1.0, step=0.1, label='Point Weight')
        self.neighbor_count = widgets.SpinBox(value=400, min=10, max=1000, label='Neighbor Count')
        self.smoothing_iterations = widgets.SpinBox(value=1, min=0, max=10, label='Smoothing Iterations')
        
        # Add settings to container
        settings.extend([
            self.angstroms,
            self.ultrafine,
            self.target_area,
            self.isotropic_remesh,
            self.simplify,
            self.max_triangles,
            self.extrapolation_distance,
            self.octree_depth,
            self.point_weight,
            self.neighbor_count,
            self.smoothing_iterations,
        ])
        
        self.status = JobStatusWidget()
        self.submit_btn = widgets.PushButton(text='Generate Surface Mesh')
        self.submit_btn.clicked.connect(self._run_job)
        
        # Add all widgets to layout
        self.container.extend([
            header,
            settings,
            self.submit_btn,
            self.status
        ])

        # Compact the layout: reduce spacing and margins on the main container and children
        self.container.native.layout().setSpacing(4)
        self.container.native.layout().setContentsMargins(10, 10, 10, 10)
        header.native.layout().setSpacing(2)
        header.native.layout().setContentsMargins(0, 0, 0, 0)
        self.status.native.layout().setSpacing(2)
        self.status.native.layout().setContentsMargins(0, 0, 0, 0)
        # Push everything to the top
        self.container.native.layout().addStretch(1)
        
        ##testing
        # Listen for config_loaded signal to update UI on resume
        if hasattr(self.experiment_manager, 'config_loaded'):
            self.experiment_manager.config_loaded.connect(self._on_config_loaded)

    def _on_config_loaded(self):
        """Update mesh tab UI and status when experiment is resumed"""
        config = getattr(self.experiment_manager, 'current_config', None)
        if not config:
            print('[MeshTab] No config found on resume')
            return
        mesh_cfg = config.get('surface_generation', {})
        # Set widget values from config if present
        if mesh_cfg:
            self.angstroms.value = mesh_cfg.get('angstroms', False)
            self.ultrafine.value = mesh_cfg.get('ultrafine', True)
            self.target_area.value = mesh_cfg.get('target_area', 1.0)
            self.isotropic_remesh.value = mesh_cfg.get('isotropic_remesh', False)
            self.simplify.value = mesh_cfg.get('simplify', False)
            self.max_triangles.value = mesh_cfg.get('simplify_max_triangles', mesh_cfg.get('max_triangles', 300000))
            self.extrapolation_distance.value = mesh_cfg.get('extrapolation_distance', 1.5)
            self.octree_depth.value = mesh_cfg.get('octree_depth', 7)
            self.point_weight.value = mesh_cfg.get('point_weight', 0.7)
            self.neighbor_count.value = mesh_cfg.get('neighbor_count', 400)
            self.smoothing_iterations.value = mesh_cfg.get('smoothing_iterations', 1)
        # Check for mesh outputs and update status
        exp_dir = None
        try:
            exp_dir = Path(self.experiment_manager.work_dir.value) / self.experiment_manager.experiment_name.currentText()
        except Exception as e:
            print(f'[MeshTab] Could not determine experiment directory: {e}')
        if exp_dir and exp_dir.exists():
            meshes_dir = exp_dir / 'results'
            mesh_files = list(meshes_dir.glob('*.ply')) + list(meshes_dir.glob('*.surface.vtp')) + list(meshes_dir.glob('*.xyz'))
            if mesh_files:
                self.status.update_status('Completed')
                self.status.update_progress(100)
            else:
                self.status.update_status('Not Started')
                self.status.update_progress(0)
                print('[MeshTab] No mesh outputs found')
        else:
            self.status.update_status('Not Started')
            self.status.update_progress(0)
            print('[MeshTab] Experiment directory does not exist')
        ## testing
    def _update_config(self):
        """Update the config file with current widget values"""
        try:
            # Get experiment directory and config path
            exp_dir = Path(self.experiment_manager.work_dir.value) / self.experiment_manager.experiment_name.currentText()
            config_path = exp_dir / f"{self.experiment_manager.experiment_name.currentText()}_config.yml"
            
            # Create meshes directory
            meshes_dir = exp_dir / 'results'
            meshes_dir.mkdir(exist_ok=True)
        
            if not config_path.exists():
                raise FileNotFoundError(f"Config file not found: {config_path}")
        
            # Load existing config
            yaml = YAML()
            with open(config_path, 'r') as f:
                config = yaml.load(f)

            # Update surface generation settings and output dir
            config['surface_generation'] = {
                'angstroms': self.angstroms.value,
                'ultrafine': self.ultrafine.value,
                'target_area': self.target_area.value,
                'isotropic_remesh': self.isotropic_remesh.value,
                'simplify': self.simplify.value,
                'simplify_max_triangles': self.max_triangles.value,
                'extrapolation_distance': self.extrapolation_distance.value,
                'octree_depth': self.octree_depth.value,
                'point_weight': self.point_weight.value,
                'neighbor_count': self.neighbor_count.value,
                'smoothing_iterations': self.smoothing_iterations.value,
                'output_dir': str(meshes_dir)  # Pass to script
            }

            # Save config
            with open(config_path, 'w') as f:
                yaml.dump(config, f)

            return config_path, meshes_dir
        except Exception as e:
            raise Exception(f"Failed to update config: {str(e)}")

    def _run_job(self):
        """Run surface mesh generation"""

        # Update config FIRST, before any dialogs, to capture current widget
        # values.  Qt dialogs (like the archive prompt below) run a nested event
        # loop which can process pending config_loaded signals and reset widget
        # values to whatever is on disk.  Writing the config here ensures the
        # user's GUI values are persisted before that can happen.
        try:
            config_path, meshes_dir = self._update_config()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update config: {e}")
            return

        # Resolve the morphometrics CLI (installed package), not a loose script.
        runner = resolve_cli_runner()
        if runner is None:
            QMessageBox.critical(self, "morphometrics CLI not found", CLI_MISSING_MESSAGE)
            print(f"[Error] {CLI_MISSING_MESSAGE}")
            return

        # Check for existing results and prompt specifically for Mesh Generation (Archives ALL)
        if not check_and_archive_outputs(self, meshes_dir, config_path=config_path, targets='all'):
            self.status.update_status('Cancelled')
            return

        # Snapshot widget-derived state on the GUI thread; the worker must not
        # read QWidget values directly (they can change mid-run if the user
        # switches experiment or work_dir).
        exp_dir = Path(self.experiment_manager.work_dir.value) / self.experiment_manager.experiment_name.currentText()

        self.submit_btn.enabled = False
        self.status.update_status('Running')
        threading.Thread(
            target=self._run_job_worker,
            args=(runner, config_path, meshes_dir, exp_dir),
            daemon=True,
        ).start()

    def _run_job_worker(self, runner, config_path, meshes_dir, exp_dir):
        try:
            cmd = runner + [MAKE_MESHES, str(config_path)]
            print(f"Running: {' '.join(map(str, cmd))}")
            my_env = os.environ.copy()
            my_env["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=my_env,
                # Run inside the experiment directory to avoid picking up sibling experiments
                cwd=str(exp_dir),
            )
            progress = 0
            step_count = 0
            if process.stdout is not None:
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        print(line)
                        if any(kw in line for kw in [
                            "Processing segmentation",
                            "Generating xyz file:",
                            "Generating a ply mesh",
                            "Converting the ply file to a vtp file:",
                        ]):
                            step_count += 1
                            # Scale progress so it approaches but never reaches 100
                            # 100% is only set on actual completion below
                            progress = min(95, int(95 * (1 - 1 / (1 + step_count * 0.3))))
                            self.status.update_progress(progress)
            return_code = process.wait()
            if return_code == 0:
                # segmentation_to_meshes.py treats work_dir as a path prefix, so
                # outputs land in exp_dir.parent with names like
                # "<exp_name><seg>_<label>.ply" — not inside exp_dir itself.
                # Sweep both locations, but in the parent restrict to files
                # prefixed with this experiment's name so we don't steal output
                # from sibling experiments.
                exp_name = exp_dir.name
                moved_files = []
                sweep_specs = [
                    (exp_dir, ['*.ply', '*.surface.vtp', '*.xyz']),
                    (exp_dir.parent, [f'{exp_name}*.ply', f'{exp_name}*.surface.vtp', f'{exp_name}*.xyz']),
                ]
                for sweep_dir, patterns in sweep_specs:
                    if not sweep_dir.exists():
                        continue
                    for pattern in patterns:
                        for f in sweep_dir.glob(pattern):
                            if not f.is_file():
                                continue
                            # Skip anything already inside meshes_dir
                            try:
                                if f.resolve().is_relative_to(meshes_dir.resolve()):
                                    continue
                            except AttributeError:
                                # Python <3.9 fallback
                                if str(f.resolve()).startswith(str(meshes_dir.resolve())):
                                    continue
                            # Strip the experiment-name prefix when present so
                            # downstream tools see clean "<seg>_<label>" names.
                            name = f.name
                            if name.startswith(exp_name):
                                name = name[len(exp_name):]
                            # Also strip any stray leading digits before letters
                            sanitized_name = re.sub(r'^[0-9]+(?=[A-Za-z])', '', name)
                            dest_path = meshes_dir / sanitized_name
                            try:
                                f.rename(dest_path)
                                moved_files.append(dest_path)
                            except Exception as e:
                                print(f"Error moving {f}: {e}")
                
                # Check if files exist in results directory (whether moved or already there)
                mesh_files = list(meshes_dir.glob('*.ply')) + list(meshes_dir.glob('*.surface.vtp')) + list(meshes_dir.glob('*.xyz'))
                if mesh_files:
                    self.status.update_status('Completed')
                    self.status.update_progress(100)
                    print(f"Added {len(moved_files)} files to results")
                    # Emit signal that mesh generation is complete - this will trigger other tabs to refresh
                    QTimer.singleShot(100, lambda: self.mesh_generation_complete.emit())
                else:
                    self.status.update_status('Warning: No mesh files found')
                    print("Warning: Process completed but no mesh files found in results directory")
            else:
                self.status.update_status('Failed')
                print("Process failed! Check output for details.")
        except Exception as e:
            self.status.update_status('Error')
            print(f"Error: {str(e)}")
        finally:
            QTimer.singleShot(0, self._job_cleanup)

    def _job_cleanup(self):
        self.submit_btn.enabled = True