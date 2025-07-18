import napari
from pathlib import Path
import mrcfile 
import numpy as np
from magicgui import widgets 
from qtpy.QtWidgets import QFileDialog
import logging
import starfile
import pandas as pd

class ProteinLoaderPlugin:
    def __init__(self,viewer: napari.Viewer):
        self.viewer = viewer
        self.structure_layer = None
        self.star_data = None
        self.logger = logging.getLogger(__name__)
        self._setup_ui()

    # Method to setup the UI
    def _setup_ui(self):
        self.container = widgets.Container(layout='vertical', labels=True)
        header = widgets.Label(value="<b>Protein Loader</b>")
        self.load_mrc_btn = widgets.PushButton(text='Load MRC File')
        self.load_mrc_btn.clicked.connect(self._load_mrc_file)
        
        # Add basic STAR file loading
        self.load_star_btn = widgets.PushButton(text='Load STAR File')
        self.load_star_btn.clicked.connect(self._load_star_file)
        
        self.status_label = widgets.Label(value='Status: Ready')
        self.container.extend([
            header, 
            self.load_mrc_btn,
            self.load_star_btn,
            self.status_label
        ])

    # Loading the MRC file

    def _load_mrc_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select MRC File",
            "",
            "MRC Files (*.mrc *.map);;All Files (*)"
        )
        if file_path:
            self._load_structure(Path(file_path))

    # Loading the STAR file
    def _load_star_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select STAR File",
            "",
            "STAR Files (*.star);;All Files (*)"
        )
        if file_path:
            self._load_star_data(Path(file_path))

    def _load_star_data(self, file_path: Path):
        """Basic STAR file loading and parsing."""
        try:
            # Read the STAR file
            star_data = starfile.read(file_path)
            self.logger.info(f"Loaded STAR file: {file_path}")
            
            # Handle different STAR file formats
            if isinstance(star_data, dict):
                # Multi-block STAR file
                self.logger.info(f"Multi-block STAR file with keys: {list(star_data.keys())}")
                # For now, use the first block
                first_key = list(star_data.keys())[0]
                self.star_data = star_data[first_key]
                self.logger.info(f"Using block: {first_key}")
            else:
                # Single block STAR file
                self.star_data = star_data
            
            # Log basic information about the data
            if isinstance(self.star_data, pd.DataFrame):
                self.logger.info(f"STAR data shape: {self.star_data.shape}")
                self.logger.info(f"STAR data columns: {list(self.star_data.columns)}")
                self.status_label.value = f'Status: STAR file loaded - {self.star_data.shape[0]} rows, {self.star_data.shape[1]} columns'
            else:
                self.logger.warning(f"Unexpected STAR data type: {type(self.star_data)}")
                self.status_label.value = 'Status: Error - unexpected STAR file format'
                
        except Exception as e:
            self.logger.error(f"Error loading STAR file {file_path}: {str(e)}")
            self.status_label.value = f'Status: Error loading STAR file - {str(e)}'

    # Method handles the logic of loading the data from a file path and adding it to napari

    def _load_structure(self, file_path: Path):
        try:
            if self.structure_layer and self.structure_layer in self.viewer.layers:
                self.viewer.layers.remove(self.structure_layer)
            with mrcfile.open(file_path) as mrc:
                data = np.array(mrc.data)

            # Ensure the data is in float32 format
            if data.dtype != np.float32:
                data = data.astype(np.float32)

            # Normalize the data to 0-1 range for contrast adjustment
            data_min = np.min(data)
            data_max = np.max(data)
            if data_max > data_min:
                data = (data - data_min) / (data_max - data_min)
            layer_name = f"{file_path.stem}_structure"
            self.structure_layer = self.viewer.add_image(
                data,
                name=layer_name,
                metadata={'source_path': str(file_path), 'type': 'structure'}
            )
            self.structure_layer.visible = True
            if hasattr(self.structure_layer, 'contrast_limits'):
                self.structure_layer.contrast_limits = (np.min(data), np.max(data))
            self.logger.info(f"Loaded structure from {file_path} with shape {data.shape}")
            self.status_label.value = f'Status: Structure loaded - {file_path.name}'
        except Exception as e:
            self.logger.error(f"Error loading structure {file_path}: {str(e)}")
            self.status_label.value = f'Status: Error loading structure - {str(e)}' 
