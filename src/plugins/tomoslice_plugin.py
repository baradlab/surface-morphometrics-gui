import napari
from pathlib import Path
import logging
from typing import Optional
import napari_tomoslice
import mrcfile
import numpy as np

class TomoslicePlugin:
    def __init__(self, viewer: napari.Viewer, config_editor):
        self.viewer = viewer
        self.config_editor = config_editor
        self.current_layer = None
        
        # Connect to config editor's data directory changes
        self.config_editor.containers['directories'].data_dir.changed.connect(self._on_data_dir_changed)
        
    def _get_first_supported_file(self, directory: Path) -> Optional[Path]:
        """Get the first supported file in the directory."""
        if not directory or not directory.exists():
            return None
            
        # Look for .mrc files first
        mrc_files = list(directory.glob('*.mrc'))
        if mrc_files:
            # Filter out hidden files (starting with ._)
            visible_files = [f for f in mrc_files if not f.name.startswith('._')]
            if visible_files:
                return visible_files[0]
            
        return None
        
    def _load_tomogram(self, file_path: Path) -> None:
        """Load and display a tomogram using mrcfile."""
        try:
            # Remove current layer if it exists
            if self.current_layer and self.current_layer in self.viewer.layers:
                self.viewer.layers.remove(self.current_layer)
            
            # Load the tomogram using mrcfile
            with mrcfile.open(file_path) as mrc:
                data = np.array(mrc.data)
            
            # Add to viewer
            self.current_layer = self.viewer.add_image(
                data,
                name=file_path.stem,
            )
            logging.info(f"Loaded tomogram from {file_path}")
            
        except Exception as e:
            logging.error(f"Error loading tomogram {file_path}: {str(e)}")
            
    def _on_data_dir_changed(self, path: str) -> None:
        """Handle data directory changes."""
        if not path:
            return
            
        directory = Path(path)
        supported_file = self._get_first_supported_file(directory)
        
        if supported_file:
            self._load_tomogram(supported_file)
        else:
            logging.warning(f"No supported files found in {path}")
            # Remove current layer if no files are available
            if self.current_layer and self.current_layer in self.viewer.layers:
                self.viewer.layers.remove(self.current_layer)
                self.current_layer = None
