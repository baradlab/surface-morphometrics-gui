import napari
from magicgui import magicgui, widgets
from qtpy.QtWidgets import QPushButton
from qtpy.QtCore import QObject, Signal
import subprocess
import logging
from pathlib import Path
import os
import sys
from morphometrics_config import ConfigEditor
from widgets.job_status import JobStatusWidget
import threading

class SegToMeshSubmissionWidget(widgets.Container):
    """Job submission widget for segmentation to mesh conversion"""
    
    class Signals(QObject):
        button_enabled = Signal(bool)
    
    def __init__(self, config_editor):
        super().__init__(layout='vertical')
        
        self.config_editor = config_editor
        self.signals = self.Signals()
        
        # Create container for submit button
        button_container = widgets.Container(layout='vertical')
        
        # Create and add submit button
        self.submit_btn = QPushButton('Run Segmentation to Mesh')
        self.submit_btn.clicked.connect(self._run_job)
        button_container.native.layout().addWidget(self.submit_btn)
        
        # Create header label
        header_label = widgets.Label(value='Process segmentation files using current configuration')
        
        # Add status widget
        self.status = JobStatusWidget()
        
        # Add to layout
        self.extend([
            header_label,
            button_container,
            self.status
        ])
        
        # Connect signals
        self.signals.button_enabled.connect(self._set_button_enabled)
        
    def _set_button_enabled(self, enabled: bool):
        """Thread-safe button enable/disable"""
        self.submit_btn.setEnabled(enabled)
        # Disable/enable all config editor widgets
        if hasattr(self.config_editor, 'set_widgets_enabled'):
            self.config_editor.set_widgets_enabled(enabled)
            
    def _run_job(self):
        """Run segmentation to mesh conversion"""
        # Disable buttons before starting
        self._set_button_enabled(False)
        
        # Clear previous output
        self.status.clear()
        
        try:
            # Check if we have an active config file
            if not self.config_editor.yaml_preserver:
                self.status.append_output("Error: No configuration file loaded")
                self.status.update_status("Failed")
                self._set_button_enabled(True)
                return
                
            config_path = self.config_editor.yaml_preserver.yaml_path
            
            # Update status
            self.status.update_status('Running')
            self.status.append_output(f"Using config file: {config_path}")
            
            try:
                # Run in separate thread
                thread = threading.Thread(target=self._run_process, args=(config_path,))
                thread.start()
            finally:
                pass
            
        except Exception as e:
            self.status.append_output(f"Error starting job: {str(e)}")
            self.status.update_status('Error')
            self._set_button_enabled(True)
            
    def _run_process(self, config_file: Path):
        """Run the actual process in a separate thread"""
        try:
            # Get the directory containing the config file
            config_dir = Path(config_file).parent
            script_path = config_dir / "segmentation_to_meshes.py"
            
            if not script_path.exists():
                self.status.append_output(f"Error: Could not find segmentation_to_meshes.py in {config_dir}")
                self.status.update_status('Error')
                self._set_button_enabled(True)
                return
            
            # Prepare command and change to config directory
            cmd = [sys.executable, str(script_path), str(config_file)]
            self.status.append_output(f"Running command: {' '.join(cmd)}")
            
            # Initialize progress tracking
            current_file = None
            current_membrane = None
            total_progress = 0
            
            # Set PYTHONUNBUFFERED to force unbuffered output
            my_env = os.environ.copy()
            my_env["PYTHONUNBUFFERED"] = "1"
            
            # Run process from config directory
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    env=my_env,
                    cwd=str(config_dir)  # Set working directory to config directory
                )
                
                # Read output
                if process.stdout is None:
                    self.status.append_output("Error: No stdout from process")
                    self.status.update_status('Error')
                    self._set_button_enabled(True)
                    return

                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                        
                    line = line.strip()
                    if line:  # Only process non-empty lines
                        self.status.append_output(line)
                        
                        # Track current file and membrane being processed
                        if "Processing segmentation" in line:
                            current_file = line.split()[-1]
                            total_progress += 5
                            self.status.update_progress(min(total_progress, 100))
                        elif "Generating xyz file:" in line:
                            current_membrane = line.split('_')[-1].split('.')[0]
                            total_progress += 5
                            self.status.update_progress(min(total_progress, 100))
                        elif "Generating a ply mesh" in line:
                            total_progress += 5
                            self.status.update_progress(min(total_progress, 100))
                        elif "Converting the ply file to a vtp file:" in line:
                            total_progress += 5
                            self.status.update_progress(min(total_progress, 100))
                
                # Get the return code
                return_code = process.poll()
                
                if return_code == 0:
                    self.status.update_status('Completed')
                    self.status.update_progress(100)
                else:
                    self.status.update_status('Failed')
                    self.status.append_output(f"Process failed with return code: {return_code}")
                    
            except Exception as e:
                self.status.append_output(f"Error running process: {str(e)}")
                self.status.update_status('Error')
                
        except Exception as e:
            self.status.append_output(f"Error running process: {str(e)}")
            self.status.update_status('Error')
        finally:
            self._set_button_enabled(True)
