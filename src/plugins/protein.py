import napari
from pathlib import Path
import mrcfile 
import numpy as np
from magicgui import widgets 
from qtpy.QtWidgets import QFileDialog
import logging

class ProteinLoaderPlugin:
    def __init__(self,viewer: napari.Viewer):
        self.viewer = viewer
        self.structure_layer = None
        self.logger = logging.getLogger(__name__)
        self._setup_ui()

    # Method to setup the UI
    def _setup_ui(self):
        self.container = widgets.Container(layout='vertical', labels=True)
        header = widgets.Label(value="<b>Lorem Ipsum</b>")
        self.load_mrc_btn = widgets.PushButton(text='Load MRC File')
        self.load_mrc_btn.clicked.connect(self._load_mrc_file)
        self.status_label = widgets.Label(value='Status: Ready')
        self.container.extend([
            header, 
            self.load_mrc_btn,
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
