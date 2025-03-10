from pathlib import Path
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QFileDialog, QHBoxLayout, QComboBox, QMessageBox, QSpinBox
)
from qtpy.QtCore import Qt
from magicgui import widgets
from ruamel.yaml import YAML
import matplotlib.pyplot as plt
import os
import napari
from napari.utils.colormaps import label_colormap


yaml = YAML()
USE_RUAMEL = True

class SegmentationEntry(widgets.Container):
    """A single segmentation entry with label and value fields"""
    def __init__(self, label='', value=1, viewer=None):
        super().__init__(layout='horizontal')
        self.viewer = viewer
        self.label_field = widgets.LineEdit(value=label, label='Label')
        self.value_field = widgets.SpinBox(value=value, label='Value')
        
        # Add simple color indicator
        self.color_indicator = widgets.PushButton()
        self.color_indicator.min_width = 20
        self.color_indicator.max_width = 20
        self.color_indicator.enabled = False
        self._update_color()
        
        self.remove_button = widgets.PushButton(text='Remove')
        self.extend([self.label_field, self.value_field, self.color_indicator, self.remove_button])

        # Connect value changes to color updates
        self.value_field.changed.connect(self._update_color)


    def _update_color(self):
        """Update the color indicator based on the value"""
        try:
            if not self.viewer:
                return
                
            label_value = self.value_field.value
            if label_value < 0:
                return
                
            for layer in self.viewer.layers:
                if isinstance(layer, napari.layers.Labels):
                    try:
                        color = layer.get_color(label_value)
                        r, g, b = (int(c * 255) for c in color[:3])
                        hex_color = f"#{r:02x}{g:02x}{b:02x}"
                        self.color_indicator.native.setStyleSheet(
                            f"background-color: {hex_color}; border: none; min-width: 20px; max-width: 20px;"
                        )
                        return
                    except Exception:
                        continue

            self.color_indicator.native.setStyleSheet("background-color: #ffffff; border: none; min-width: 20px; max-width: 20px;")
            
        except Exception:
            self.color_indicator.native.setStyleSheet("background-color: #ff0000; border: none; min-width: 20px; max-width: 20px;")


class SegmentationContainer(widgets.Container):
    """Container for multiple segmentation entries"""
    def __init__(self, experiment_manager):
        super().__init__(layout='vertical')
        self._entries = []
        self.add_button = widgets.PushButton(text='Add Entry')
        self.add_button.clicked.connect(self._add_entry)
        self.extend([self.add_button])
        self.experiment_manager = experiment_manager

    @property
    def entries(self):
        """Get list of current segmentation entries"""
        return self._entries

    @entries.setter
    def entries(self, value):
        self._entries = value

    def _set_values(self, values: dict):
        """Set segmentation values from dictionary"""
        # Clear existing entries
        while self.entries:
            self._remove_entry(self.entries[0])
        
        # Add new entries
        for label, value in values.items():
            self._add_entry(label=label, value=value)

    def _add_entry(self, label='', value=1):
        """Add a new segmentation entry"""
        entry = SegmentationEntry(label=label, value=value, viewer=self.experiment_manager.viewer)
        self.entries.append(entry)
        self.insert(-1, entry)

    def _remove_entry(self, entry):
        if entry in self.entries:
            self.entries.remove(entry)
            self.remove(entry)
    
    def get_values(self):
        return {
            entry.label_field.value: entry.value_field.value 
            for entry in self.entries
            if entry.label_field.value.strip()  # Only include non-empty labels
        }
    

class ExperimentManager(QWidget):
    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'config.yml'
        )
        self.current_config = {}
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.layout.setSpacing(10)

        # Set a fixed width for the dialog box
        self.setFixedWidth(400)

        # === Start New Experiment Section ===
        start_header = QLabel("Start New Experiment")
        start_header.setAlignment(Qt.AlignCenter)
        start_header.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.layout.addWidget(start_header)

        # Work Directory
        work_dir_layout = QHBoxLayout()
        work_dir_label = QLabel("Work Directory:")
        work_dir_label.setFixedWidth(120)  # Fixed width for labels
        self.work_dir = widgets.FileEdit(
            mode='d'
        )
        self.work_dir.changed.connect(self._update_experiment_names)  # Connect to update dropdown
        self.work_dir.changed.connect(self._check_start_button_state)  # Connect to enable/disable button
        work_dir_layout.addWidget(work_dir_label)
        work_dir_layout.addWidget(self.work_dir.native)
        self.layout.addLayout(work_dir_layout)

        # Experiment Name
        experiment_name_layout = QHBoxLayout()
        experiment_name_label = QLabel("Experiment Name:")
        experiment_name_label.setFixedWidth(120)
        self.experiment_name = QComboBox()
        self.experiment_name.setEditable(True)  # Allow typing new names
        self.experiment_name.setPlaceholderText("Enter or select an experiment name")
        self.experiment_name.currentTextChanged.connect(self._check_start_button_state)  # Connect to enable/disable button
        experiment_name_layout.addWidget(experiment_name_label)
        experiment_name_layout.addWidget(self.experiment_name)
        self.layout.addLayout(experiment_name_layout)

        # Data Directory
        data_dir_layout = QHBoxLayout()
        data_dir_label = QLabel("Data Directory:")
        data_dir_label.setFixedWidth(120)
        self.data_dir = widgets.FileEdit(
            mode='d'
        )
        self.data_dir.changed.connect(self._update_config_paths)  # Connect to update config paths
        self.data_dir.changed.connect(self._check_start_button_state)  # Connect to enable/disable button
        data_dir_layout.addWidget(data_dir_label)
        data_dir_layout.addWidget(self.data_dir.native)
        self.layout.addLayout(data_dir_layout)

        # Config Template File
        config_template_layout = QHBoxLayout()
        config_template_label = QLabel("Config Template File:")
        config_template_label.setFixedWidth(120)
        self.config_template = widgets.FileEdit(
            filter='*.yml',
            mode='r'
        )
        self.config_template.changed.connect(self._handle_config_template_selection)  # Connect to load config
        self.config_template.changed.connect(self._check_start_button_state)  # Connect to enable/disable button
        config_template_layout.addWidget(config_template_label)
        config_template_layout.addWidget(self.config_template.native)
        self.layout.addLayout(config_template_layout)

        # Cores Input
        cores_layout = QHBoxLayout()
        cores_label = QLabel("Cores:")
        cores_label.setFixedWidth(120)
        self.cores_input = QSpinBox()
        self.cores_input.setMinimum(1)
        self.cores_input.setMaximum(64)  # Adjust max cores as needed
        self.cores_input.setValue(14)  # Default value
        cores_layout.addWidget(cores_label)
        cores_layout.addWidget(self.cores_input)
        self.layout.addLayout(cores_layout)

        # === Segmentation Section ===
        segmentation_header = QLabel("Segmentation Values")
        segmentation_header.setAlignment(Qt.AlignCenter)  # Center align the text
        segmentation_header.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.layout.addWidget(segmentation_header)

        # Add segmentation container first
        self.segmentation_container = SegmentationContainer(self)
        self.layout.addWidget(self.segmentation_container.native)

        # Add "Add Entry" button below the entries
        add_button_container = widgets.Container(layout='horizontal')
        add_button_container.extend([self.segmentation_container.add_button])
        self.layout.addWidget(add_button_container.native)

        # Submit Button
        self.submit_button = QPushButton('New Experiment')
        self.submit_button.clicked.connect(self._create_experiment)
        self.submit_button.setEnabled(False)
        self.submit_button.setFixedWidth(200)
        self.submit_button.setStyleSheet("""
            QPushButton {
                padding: 8px;
                background-color: #7f7f7f;  /* Darker gray color */
                color: black;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #A0A0A0;  /* Lighter grey on hover */
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)

        # Center the submit button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.submit_button)
        button_layout.addStretch()
        self.layout.addLayout(button_layout)

        self.layout.addStretch()

    def _update_config_from_segmentation(self):
        """Update config with current segmentation values"""
        if self.current_config:
            self.current_config['segmentation_values'] = self.segmentation_container.get_values()

    def _update_experiment_names(self):
        """Update the experiment names dropdown based on the work directory"""
        if self.work_dir.value:
            work_dir_path = Path(self.work_dir.value)
            if work_dir_path.exists():
                # Get all subdirectories in the work directory
                experiment_names = [dir.name for dir in work_dir_path.iterdir() if dir.is_dir()]
                self.experiment_name.clear()  # Clear existing items
                self.experiment_name.addItems(experiment_names)  # Add new items

    def _check_start_button_state(self):
        """Enable start button only when all required fields are filled"""
        self.submit_button.setEnabled(
            all([
                self.work_dir.value,
                self.experiment_name.currentText().strip(),  # Check if experiment name is not empty
                self.config_template.value,
                self.data_dir.value
            ])
        )

    def _handle_config_template_selection(self, file_path):
        """Handle config template file selection with error handling"""
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.current_config = yaml.load(f)  # Use ruamel.yaml to load
                self._load_config(file_path)
                self._check_start_button_state()
            except Exception as e:
                print(f"Error loading config: {e}")
                self.current_config = None
                self.submit_button.setEnabled(False)

    def _load_config(self, file_path):
        """Load config and initialize segmentation values"""
        try:
            with open(file_path, 'r') as f:
                self.current_config = yaml.load(f)

            # Initialize segmentation values if present
            if self.current_config and 'segmentation_values' in self.current_config:
                self.segmentation_container._set_values(self.current_config['segmentation_values'])

        except Exception as e:
            print(f"Error loading config: {e}")
            self.current_config = None
            self.submit_button.setEnabled(False)

    def _update_config_paths(self):
        """Update paths in the config when directories are selected"""
        if self.current_config:
            if not 'data_dir' in self.current_config:
                self.current_config['data_dir'] = str(self.data_dir.value)
            if not 'work_dir' in self.current_config:
                self.current_config['work_dir'] = str(self.work_dir.value)

            self._check_start_button_state()

    def _create_experiment(self):
        """Create a new experiment by copying config template and setting up directories"""
        if not all([
            self.work_dir.value,
            self.experiment_name.currentText().strip(),
            self.config_template.value,
            self.data_dir.value
        ]):
            return

        try:
            # Create experiment directory
            experiment_name = self.experiment_name.currentText().strip()
            experiment_dir = Path(self.work_dir.value) / experiment_name
            experiment_dir.mkdir(parents=True, exist_ok=True)

            # Copy the config template to experiment directory with new name
            config_template_path = Path(self.config_template.value)
            new_config_path = experiment_dir / f"{experiment_name}_config.yml"

            # Read the config template
            with open(config_template_path, 'r') as f:
                config_data = yaml.load(f)  # Use ruamel.yaml to load

            # Update only the UNIVERSAL section
            config_data['data_dir'] = str(self.data_dir.value)
            config_data['work_dir'] = str(experiment_dir)
            config_data['exp_name'] = experiment_name  # Add experiment name to config
            config_data['cores'] = self.cores_input.value()  # Add cores to config
            config_data['segmentation_values'] = self.segmentation_container.get_values()  # Add segmentation values to config

            # Save the modified config to the new location
            with open(new_config_path, 'w') as f:
                yaml.dump(config_data, f)  # Use ruamel.yaml to dump

            print(f"Created new experiment config at: {new_config_path}")
            self.current_config = config_data

            QMessageBox.information(
                self,
                "Success",
                f"Experiment '{experiment_name}' created successfully!"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create experiment: {str(e)}"
            )