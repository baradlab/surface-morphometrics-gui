import napari
from pathlib import Path
import logging
from typing import Optional
import napari_tomoslice
import mrcfile
import numpy as np
from qtpy.QtWidgets import QLabel
from qtpy.QtCore import Qt
from qtpy.QtGui import QCursor
import matplotlib.pyplot as plt
from matplotlib.colors import rgb2hex

class TomoslicePlugin:
    def __init__(self, viewer: napari.Viewer, experiment_manager):
        self.viewer = viewer
        self.experiment_manager = experiment_manager
        self.current_layer = None
        
        # Connect to experiment manager's data directory widget
        self.experiment_manager.data_dir.changed.connect(self._on_data_dir_changed)

        # Setup tooltip
        self.setup_tooltip()

    def setup_tooltip(self):
        """Setup a custom QLabel tooltip"""
        self._tooltip = QLabel(self.viewer.window._qt_window)
        self._tooltip.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self._tooltip.setAttribute(Qt.WA_ShowWithoutActivating)
        self._tooltip.setAlignment(Qt.AlignCenter)
        self._tooltip.setStyleSheet(
            "color: black; background-color: white; padding: 2px; border: 1px solid black;"
        )
        self._tooltip.hide()  # Initially hidden

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
                # Disconnect old mouse_move_callbacks if they exist
                if hasattr(self.current_layer, 'mouse_move_callbacks'):
                    try:
                        self.current_layer.mouse_move_callbacks.remove(self._on_mouse_move)
                    except ValueError:
                        pass
                self.viewer.layers.remove(self.current_layer)

            # Load the tomogram using mrcfile
            with mrcfile.open(file_path) as mrc:
                data = np.array(mrc.data)

            # Convert data to integer type for segmentation
            data = data.astype(np.int32)
            
            # Add layer with default napari colors
            self.current_layer = self.viewer.add_labels(
                data,
                name=file_path.stem,
            )
            
            # Connect mouse move callback for tooltip
            self.current_layer.mouse_move_callbacks.append(self._on_mouse_move)
            
            logging.info(f"Loaded tomogram from {file_path}")
        except Exception as e:
            logging.error(f"Error loading tomogram {file_path}: {str(e)}")

    def _get_segmentation_label(self, value):
        """Get segmentation label for given value"""
        values = self.experiment_manager.segmentation_container.get_values()
        for label, val in values.items():
            if val == value:
                return label
        return None


    def _on_data_dir_changed(self, path: str) -> None:
        """Handle data directory changes"""
        if not path:
            return
            
        directory = Path(path)
        supported_file = self._get_first_supported_file(directory)
        
        if supported_file:
            self._load_tomogram(supported_file)
        else:
            logging.warning(f"No supported files found in {path}")
            if self.current_layer and self.current_layer in self.viewer.layers:
                self.viewer.layers.remove(self.current_layer)
                self.current_layer = None

    def _on_mouse_move(self, layer, event):
        """Update tooltip on mouse movement"""
        if self.current_layer is None:
            self._tooltip.hide()
            return

        cursor_position = self.viewer.cursor.position
        if cursor_position is None or not np.all(np.array(cursor_position) >= 0):
            self._tooltip.hide()
            return

        # Get value at cursor position
        data_coordinates = self.current_layer.world_to_data(cursor_position)
        value = self._get_value_at_position(data_coordinates)

        if value is not None:
            # Get segmentation label
            label = self._get_segmentation_label(value)
            
            # Move tooltip next to cursor
            self._tooltip.move(QCursor.pos().x() + 20, QCursor.pos().y() + 20)
            
            # Format tooltip text as label:value
            if label:
                tooltip_text = f"{label}:{int(value)}"
            else:
                tooltip_text = f"Segment:{int(value)}"

            self._tooltip.setText(tooltip_text)
            self._tooltip.setStyleSheet(
                "color: black; background-color: white; "
                "padding: 2px; border: 1px solid black;"
            )
            self._tooltip.adjustSize()
            self._tooltip.show()
        else:
            self._tooltip.hide()

    def _get_value_at_position(self, position):
        """Get the value at a specific position in the tomogram data"""
        if self.current_layer is None:
            return None
            
        indices = np.round(position).astype(int)
        try:
            data = self.current_layer.data
            if all(0 <= idx < shape for idx, shape in zip(indices, data.shape)):
                return data[tuple(indices)]
            return None
        except IndexError:
            return None