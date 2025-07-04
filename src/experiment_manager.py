from pathlib import Path
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QHBoxLayout, QComboBox, QMessageBox, QSpinBox, QDialog, 
    QCompleter
)
from qtpy.QtCore import Qt, QTimer, QStringListModel, Signal  # type: ignore
from magicgui import widgets
from ruamel.yaml import YAML
import matplotlib.pyplot as plt
import os
import napari

class SegmentationEntry(widgets.Container):
    """A single segmentation entry with label and value fields"""
    def __init__(self, label='', value=1, viewer=None):
        super().__init__(layout='horizontal')
        self.viewer = viewer
        
        # Label implementation
        self.label_field = widgets.LineEdit(value=label)
        
        # Value field
        self.value_field = widgets.SpinBox(value=value)
        
        # Color indicator with initialization
        self.color_indicator = widgets.PushButton()
        self.color_indicator.min_width = 20
        self.color_indicator.max_width = 20
        self.color_indicator.enabled = False
        self._update_color()
        
        self.remove_button = widgets.PushButton(text='Remove')
        self.extend([self.label_field, self.value_field, self.color_indicator, self.remove_button])

        # Connect value changes to color updates
        self.value_field.changed.connect(self._update_color)
        
        # Prevent creating new windows
        self.native.setWindowFlags(Qt.Widget)


    def _update_color(self):
        """Update the color indicator based on the value"""
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


class SegmentationContainer(widgets.Container):
    """Container for multiple segmentation entries"""
    def __init__(self, experiment_manager):
        super().__init__(layout='vertical')
        self._entries = []
        self.add_button = widgets.PushButton(text='Add Entry')
        self.add_button.clicked.connect(self._add_entry)
        self.extend([self.add_button])
        self.experiment_manager = experiment_manager
        # Prevent creating new windows
        self.native.setWindowFlags(Qt.Widget)

    @property
    def entries(self):
        """Get list of current segmentation entries"""
        return self._entries

    @entries.setter
    def entries(self, value):
        self._entries = value

    def _set_values(self, values: dict):

        """Set segmentation values from dictionary"""
        # Update existing entries first
        existing_entries = {entry.label_field.value: entry for entry in self.entries}

        
        for label, value in values.items():

            if label in existing_entries:

                # Update existing entry
                entry = existing_entries[label]
                entry.value_field.value = value
                entry._update_color()
            else:

                # Add new entry only if it doesn't exist
                self._add_entry(label=label, value=value)
        
        # Remove entries that are no longer needed
        for entry in list(self.entries):
            if entry.label_field.value not in values:

                self._remove_entry(entry)

    def _add_entry(self, label='', value=1):
        """Add a new segmentation entry"""
        entry = SegmentationEntry(label=label, value=value, viewer=self.experiment_manager.viewer)
        entry.remove_button.clicked.connect(lambda: self._remove_entry(entry))
        # Connect label field changes to update config
        entry.label_field.changed.connect(self._update_config)
        # Connect value field changes to update config
        entry.value_field.changed.connect(self._update_config)
        self._entries.append(entry)
        self.insert(len(self) - 1, entry)

    def _remove_entry(self, entry):
        if entry in self.entries:
            self.entries.remove(entry)
            self.remove(entry)
    
    def _update_config(self):
        """Update the configuration when labels or values change"""
        if hasattr(self.experiment_manager, '_update_config_from_segmentation'):
            self.experiment_manager._update_config_from_segmentation()
    
    def get_values(self):
        return {
            entry.label_field.value: entry.value_field.value 
            for entry in self.entries
            if entry.label_field.value.strip()  # Only include non-empty labels
        }
    

class ExperimentManager(QWidget):
    config_loaded = Signal()
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

        # Experiment Name with proper completer setup
        experiment_name_layout = QHBoxLayout()
        experiment_name_label = QLabel("Experiment Name:")
        experiment_name_label.setFixedWidth(120)
        self.experiment_name = QComboBox()
        self.experiment_name.setEditable(True)
        self.experiment_name.setInsertPolicy(QComboBox.NoInsert)
        self.experiment_name.setPlaceholderText("Enter or select an experiment name")
        
        # Setup the completer for filtering
        self.setup_experiment_completer()
        
        self.experiment_name.currentIndexChanged.connect(self._on_experiment_selected)
        self.experiment_name.editTextChanged.connect(self._check_start_button_state)
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

    def setup_experiment_completer(self):
        """Set up the experiment name completer for better filtering"""
        # Create model for the completer
        self.completer_model = QStringListModel()
        self.all_experiment_names = []
        
        # Create completer
        self.completer = QCompleter()
        self.completer.setModel(self.completer_model)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchStartsWith)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        
        # Set completer on combobox
        self.experiment_name.setCompleter(self.completer)
        
        # Connect to update filter on text changes
        self.experiment_name.lineEdit().textChanged.connect(self.filter_experiments)

    def filter_experiments(self, text):
        """Filter experiment names based on the text"""
        if not text:
            # If empty, show all items but don't show popup
            self.completer_model.setStringList(self.all_experiment_names)
            return
            
        # Filter to only matching items
        matching_items = [name for name in self.all_experiment_names 
                         if text.lower() in name.lower()]
        
        # Update completer model with filtered items
        self.completer_model.setStringList(matching_items)
        
        # Show popup with filtered options if we have matches
        if matching_items:
            # Show completer popup
            self.completer.complete()
            
            # Make sure line edit maintains focus and cursor position
            line_edit = self.experiment_name.lineEdit()
            cursor_pos = line_edit.cursorPosition()
            QTimer.singleShot(10, lambda: line_edit.setCursorPosition(cursor_pos))

    def _update_config_from_segmentation(self):
        """Update config with current segmentation values"""
        if self.current_config:
            self.current_config['segmentation_values'] = self.segmentation_container.get_values()

    def _update_experiment_names(self):
        """Populate experiment names from work directory"""
        self.experiment_name.clear()
        self.all_experiment_names = []
        
        if not self.work_dir.value:
            return
            
        work_dir = Path(self.work_dir.value)
        
        if not work_dir.exists():
            return
        
        existing_experiments = [
            d.name for d in work_dir.iterdir() 
            if d.is_dir() and list(d.glob('*_config.yml'))
        ]
        
        if existing_experiments:
            self.all_experiment_names = existing_experiments
            self.experiment_name.addItems(existing_experiments)
            self.completer_model.setStringList(existing_experiments)

    def _on_experiment_selected(self):
        """Handle explicit experiment selection"""
        # Only update fields if this is a valid selection
        if self.experiment_name.currentIndex() >= 0:
            # Update button text

            self.submit_button.setText('Resume Experiment')
            
            # Try to load the experiment config if it exists

            self._load_existing_experiment_config()
            
            # Enable/disable button based on state
            self._check_start_button_state()
            
            # Keep focus in the text box
            self.experiment_name.lineEdit().setFocus()
        else:
            # Clear fields if typing a new name
            self._clear_experiment_fields()
            self.submit_button.setText('Start New Experiment')

    def _load_existing_experiment_config(self):

        """Load configuration from an existing experiment"""
        selected_experiment = self.experiment_name.currentText()

        if not selected_experiment or not self.work_dir.value:

            return
            
        # Build path to the experiment directory and config file
        exp_dir = Path(self.work_dir.value) / selected_experiment
        print(f'[Resume] Experiment directory: {exp_dir}')
        config_path = next(exp_dir.glob(f"*_config.yml"), None)
        print(f'[Resume] Found config_path (wildcard): {config_path}')
        
        if not config_path or not config_path.exists():
            print('[Resume] Wildcard config not found, trying config.yml')
            config_path = exp_dir / "config.yml"
            if not config_path.exists():

                return
        
        # Load the existing config
        yaml = YAML(typ='safe')
        try:
            print(f'[Resume] Opening config file: {config_path}')
            with open(config_path, 'r') as f:
                existing_config = yaml.load(f)

            # Update current config
            self.current_config = existing_config

            # Update UI with loaded config values
            if 'data_dir' in existing_config:

                self.data_dir.value = existing_config['data_dir']
            # Load the original config template if available
            if 'config_template' in existing_config:

                self.config_template.value = existing_config['config_template']
            else:

                self.config_template.value = str(config_path)
            # Set cores if available
            if 'cores' in existing_config:

                self.cores_input.setValue(existing_config['cores'])
            # Load segmentation values if available
            if 'segmentation_values' in existing_config:

                self.segmentation_container._set_values(existing_config['segmentation_values'])
            # Emit signal that config was loaded - this will update job tabs

            self.config_loaded.emit()
        except Exception as e:
            pass

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
        """Handle config template file selection"""
        if file_path and file_path.is_file() and file_path.suffix in ('.yml', '.yaml'):
            yaml = YAML(typ='safe')
            try:
                with open(file_path, 'r') as f:
                    self.current_config = yaml.load(f)
                self._load_config(file_path)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error Loading Config",
                    f"Failed to load config file: {str(e)}"
                )

    def _load_config(self, file_path):
        """Load config and initialize segmentation values"""
        yaml = YAML(typ='safe')
        with open(file_path, 'r') as f:
            self.current_config = yaml.load(f)

        # Initialize segmentation values if present
        if self.current_config and 'segmentation_values' in self.current_config:
            self.segmentation_container._set_values(self.current_config['segmentation_values'])

    def _update_config_paths(self):
        """Update paths in the config when directories are selected"""
        if self.current_config:
            # Don't overwrite existing paths when resuming
            if 'data_dir' not in self.current_config and self.data_dir.value:
                self.current_config['data_dir'] = str(self.data_dir.value)
            elif 'data_dir' in self.current_config:
                # Update UI to reflect config value
                self.data_dir.value = self.current_config['data_dir']
            
            if 'work_dir' not in self.current_config and self.work_dir.value:
                self.current_config['work_dir'] = str(self.work_dir.value)
            elif 'work_dir' in self.current_config:
                    # No need to update work_dir UI since that's how we loaded the config
                pass

        self._check_start_button_state()

    def _create_experiment(self):
        """Handle both new experiment creation and resuming"""
        if self.submit_button.text() == 'Resume Experiment':
            self._confirm_resume()
        else:
            self._create_new_experiment()

    def _confirm_resume(self):

        """Show resume confirmation dialog"""

        dialog = QDialog(self)
        dialog.setWindowTitle('Confirm Resume')
        dialog.setFixedWidth(400)
        
        layout = QVBoxLayout()
        dialog.setLayout(layout)
        
        # Header
        header = QLabel('Confirm Resume')
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet('font-size: 16px; font-weight: bold;')
        layout.addWidget(header)
        
        # Warning message
        warning = QLabel('Resuming will use existing files and may overwrite data!')
        warning.setAlignment(Qt.AlignCenter)
        layout.addWidget(warning)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # OK button
        ok_button = QPushButton('Resume')
        ok_button.setFixedWidth(100)
        ok_button.setStyleSheet(
            """
            QPushButton {
                padding: 8px;
                background-color: #7f7f7f;
                color: black;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #A0A0A0;
            }
            """
        )
        ok_button.clicked.connect(lambda: self._handle_resume_confirmation(dialog, True))
        
        # Cancel button
        cancel_button = QPushButton('Cancel')
        cancel_button.setFixedWidth(100)
        cancel_button.setStyleSheet(
            """
            QPushButton {
                padding: 8px;
                background-color: #7f7f7f;
                color: black;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #A0A0A0;
            }
            """
        )
        cancel_button.clicked.connect(lambda: self._handle_resume_confirmation(dialog, False))
        
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        dialog.exec_()
    
    def _handle_resume_confirmation(self, dialog, confirmed):

        """Handle resume confirmation result"""
        dialog.close()

        if confirmed:

            self._resume_experiment()
        else:
            pass    

    def _resume_experiment(self):
        """Resume existing experiment"""
        try:
            # Get experiment name and validate
            experiment_name = self.experiment_name.currentText().strip()

            if not experiment_name:

                raise ValueError("Experiment name cannot be empty")
                
            # Validate experiment directory
            exp_dir = Path(self.work_dir.value) / experiment_name

            if not exp_dir.exists():

                raise FileNotFoundError(f'Experiment directory {exp_dir} not found')
            
            # Find config file (either format)
            config_path = next(exp_dir.glob(f"*_config.yml"), None)

            if not config_path:

                config_path = exp_dir / "config.yml"
            if not config_path.exists():

                raise FileNotFoundError(f'Config file not found in {exp_dir}')
            
            # Load existing config
            yaml = YAML(typ='safe')
            print(f'[Resume] Opening config file: {config_path}')
            with open(config_path, 'r') as f:
                self.current_config = yaml.load(f)

            
            # Make sure we use the correct paths

            self._update_config_paths()
            
            # Emit signal that config was loaded - this will update job tabs
            self.config_loaded.emit()
            
            # Notify plugins
            if hasattr(self, 'tomoslice_plugin'):

                self.tomoslice_plugin.update_directories()
            

            QMessageBox.information(self, 'Experiment Resumed', 
                                   f'Successfully resumed experiment: {experiment_name}')
        except Exception as e:

            QMessageBox.critical(self, 'Resume Error',
                                f'Failed to resume experiment: {str(e)}')


    def _create_new_experiment(self):
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
            yaml = YAML()
            yaml.preserve_quotes = True
            with open(config_template_path, 'r') as f:
                config_data = yaml.load(f)

            # Update only the UNIVERSAL section
            config_data['data_dir'] = str(self.data_dir.value)
            config_data['work_dir'] = str(experiment_dir)
            config_data['exp_name'] = experiment_name  # Add experiment name to config
            config_data['cores'] = self.cores_input.value()  # Add cores to config
            config_data['segmentation_values'] = self.segmentation_container.get_values()  # Add segmentation values to config

            # Save the modified config to the new location
            with open(new_config_path, 'w') as f:
                yaml.dump(config_data, f)

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

    def _update_ui_from_config(self):
        """Update UI state from loaded config"""
        if self.current_config:
            self.work_dir.value = self.current_config['work_dir']
            self.data_dir.value = self.current_config['data_dir']
            self.config_template.value = self.current_config['config_template']
            self.cores_input.setValue(self.current_config['cores'])
            self.segmentation_container._set_values(self.current_config['segmentation_values'])

    def _clear_experiment_fields(self):
        """Clear experiment fields when typing a new name"""
        self.data_dir.value = ''
        self.config_template.value = ''
        self.cores_input.setValue(1)
        self.segmentation_container._set_values({})
        self.submit_button.setText('Start New Experiment')