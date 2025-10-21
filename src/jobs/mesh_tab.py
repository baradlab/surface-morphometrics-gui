from pathlib import Path
import re
import subprocess
import sys
import os
from magicgui import widgets
from widgets.job_status import JobStatusWidget
from ruamel.yaml import YAML
from qtpy.QtCore import QTimer, Signal, QObject
from qtpy.QtWidgets import QWidget
import threading

class MeshGenerationWidget(QWidget):
    """Widget for surface mesh generation settings"""
    
    # Signal to notify when mesh generation is complete
    mesh_generation_complete = Signal()
    
    def __init__(self, experiment_manager):
        super().__init__()
        self.experiment_manager = experiment_manager
        
        self.container = widgets.Container(layout='vertical', labels=True)
        self.native = self.container.native  # Use magicgui container's native widget
        self.experiment_manager = experiment_manager
        
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
        self.ultrafine = widgets.CheckBox(value=False, label='Ultrafine Surface (High Quality, Slow)')
        self.mesh_sampling = widgets.SpinBox(value=1, min=1, max=10, label='Mesh Sampling Rate')
        self.simplify = widgets.CheckBox(value=True, label='Simplify Surface')
        self.max_triangles = widgets.SpinBox(value=100000, min=1000, max=1000000, label='Max Triangles')
        self.extrapolation_distance = widgets.FloatSpinBox(value=1.5, min=0.1, max=10.0, step=0.1, label='Extrapolation Distance')
        self.octree_depth = widgets.SpinBox(value=9, min=1, max=15, label='Octree Depth')
        self.point_weight = widgets.FloatSpinBox(value=0.7, min=0.1, max=1.0, step=0.1, label='Point Weight')
        self.neighbor_count = widgets.SpinBox(value=300, min=10, max=1000, label='Neighbor Count')
        self.smoothing_iterations = widgets.SpinBox(value=1, min=0, max=10, label='Smoothing Iterations')
        
        # Add settings to container
        settings.extend([
            self.angstroms,
            self.ultrafine,
            self.mesh_sampling,
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
            self.ultrafine.value = mesh_cfg.get('ultrafine', False)
            self.mesh_sampling.value = mesh_cfg.get('mesh_sampling', 1)
            self.simplify.value = mesh_cfg.get('simplify', True)
            self.max_triangles.value = mesh_cfg.get('max_triangles', 100000)
            self.extrapolation_distance.value = mesh_cfg.get('extrapolation_distance', 1.5)
            self.octree_depth.value = mesh_cfg.get('octree_depth', 9)
            self.point_weight.value = mesh_cfg.get('point_weight', 0.7)
            self.neighbor_count.value = mesh_cfg.get('neighbor_count', 300)
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
                'mesh_sampling': self.mesh_sampling.value,
                'simplify': self.simplify.value,
                'max_triangles': self.max_triangles.value,
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
        self.submit_btn.enabled = False
        self.status.update_status('Running')
        threading.Thread(target=self._run_job_worker, daemon=True).start()

    def _run_job_worker(self):
        try:
            config_path, meshes_dir = self._update_config()
            work_dir = Path(self.experiment_manager.work_dir.value)
            
            # Get the directory containing the config file
            config_dir = Path(config_path).parent
            script_path = config_dir / "segmentation_to_meshes.py"
            if not script_path.exists():
                self.status.update_status('Error')
                print(f"Script not found: {script_path}")
                QTimer.singleShot(0, self._job_cleanup)
                return
            cmd = [sys.executable, str(script_path), str(config_path)]
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
                cwd=str(Path(self.experiment_manager.work_dir.value) / self.experiment_manager.experiment_name.currentText())
            )
            progress = 0
            if process.stdout is not None:
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        print(line)
                        if "Processing segmentation" in line:
                            progress += 10
                            self.status.update_progress(min(progress, 100))
                        elif "Generating xyz file:" in line:
                            progress += 10
                            self.status.update_progress(min(progress, 100))
                        elif "Generating a ply mesh" in line:
                            progress += 10
                            self.status.update_progress(min(progress, 100))
                        elif "Converting the ply file to a vtp file:" in line:
                            progress += 10
                            self.status.update_progress(min(progress, 100))
            return_code = process.wait()
            if return_code == 0:
                exp_dir = Path(self.experiment_manager.work_dir.value) / self.experiment_manager.experiment_name.currentText()
                work_dir = Path(self.experiment_manager.work_dir.value)
                
                # Check both work directory and experiment directory for mesh files
                moved_files = []
                search_dirs = [exp_dir, work_dir]
                
                for pattern in ['*.ply', '*.surface.vtp', '*.xyz']:
                    for search_dir in search_dirs:
                        if search_dir.exists():
                            for f in search_dir.glob(pattern):
                                if f.is_file():
                                    # Sanitize filename: remove any accidental leading digits before letters
                                    sanitized_name = re.sub(r'^[0-9]+(?=[A-Za-z])', '', f.name)
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