import napari
from magicgui import magicgui, widgets
import yaml
from pathlib import Path
import re
import logging
from typing import Dict, Any, List, Optional
from qtpy.QtWidgets import QScrollArea,QWidget, QVBoxLayout

class ConfigYAMLPreserver:
    """Preserves YAML formatting while allowing updates"""
    
    def __init__(self, yaml_path: Path):
        self.yaml_path = Path(yaml_path)
        with open(self.yaml_path, 'r') as f:
            self.content = f.read()
        if not self.content.strip():  # Handle empty files
            self.content = ""
        self.yaml_data = yaml.safe_load(self.content) or {}
        self._static_fields = {
            'distance_and_orientation_measurements': {
                'intra': ['IMM', 'OMM', 'ER'],
                'inter': {'OMM': ['IMM', 'ER']}
            }
        }

    def _format_value(self, value: Any, indent_level: int = 0) -> str:
        """Format a value for YAML while preserving type and handling nested structures"""
        indent = ' ' * indent_level
        
        if isinstance(value, bool):
            return str(value).lower()
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            if ' ' in value or ':' in value:
                return f'"{value}"'
            return value
        elif isinstance(value, list):
            if not value:  # Empty list
                return '[]'
            return '\n'.join(f"{indent}- {self._format_value(item, indent_level)}" for item in value)
        elif isinstance(value, dict):
            if not value:  # Empty dict
                return '{}'
            nested = []
            for k, v in value.items():
                formatted_value = self._format_value(v, indent_level + 2)
                if isinstance(v, (list, dict)) and v:  # Non-empty list or dict
                    nested.append(f"{indent}{k}:\n{formatted_value}")
                else:
                    nested.append(f"{indent}{k}: {formatted_value}")
            return '\n'.join(nested)
        return str(value)

    def update(self, updates: Dict[str, Any]) -> None:
        """Update values while preserving formatting"""
        current_data = yaml.safe_load(self.content) or {}
        
        # Deep merge updates with current data
        def deep_merge(d1, d2):
            for k, v in d2.items():
                if k in d1 and isinstance(d1[k], dict) and isinstance(v, dict):
                    deep_merge(d1[k], v)
                else:
                    d1[k] = v
        
        deep_merge(current_data, updates)
        
        # Format the entire config as a string
        self.content = self._format_value(current_data) + '\n'
        self.yaml_data = current_data

    def save(self) -> None:
        """Save changes back to file"""
        if self.yaml_path.exists():
            backup_path = self.yaml_path.with_suffix('.bak')
            self.yaml_path.rename(backup_path)
            
        try:
            with open(self.yaml_path, 'w') as f:
                f.write(self.content)
        except Exception as e:
            if 'backup_path' in locals():
                backup_path.rename(self.yaml_path)
            raise e

class SegmentationEntry(widgets.Container):
    """A single segmentation entry with label and value fields"""
    def __init__(self, label='', value=1):
        super().__init__(layout='horizontal')
        self.label_field = widgets.LineEdit(value=label, label='Label')
        self.value_field = widgets.SpinBox(value=value, label='Value')
        self.remove_button = widgets.PushButton(text='Remove')
        self.extend([self.label_field, self.value_field, self.remove_button])

class SegmentationContainer(widgets.Container):
    """Container for multiple segmentation entries"""
    def __init__(self):
        super().__init__(layout='vertical')
        self.entries = []
        self.add_button = widgets.PushButton(text='Add Entry')
        self.add_button.clicked.connect(self._add_entry)
        self.extend([self.add_button])

    def _add_entry(self, label='', value=1):
        entry = SegmentationEntry(label=label, value=value)
        entry.remove_button.clicked.connect(lambda: self._remove_entry(entry))
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
    
    def _set_values(self, values: dict):
        """Set segmentation values from dictionary"""
        # Clear existing entries
        while self.entries:
            self._remove_entry(self.entries[0])
        
        # Add new entries
        for label, value in values.items():
            self._add_entry(label=label, value=value)

class IntraListEditor(widgets.Container):
    """Editor for intra membrane list"""
    def __init__(self):
        super().__init__(layout='vertical')
        self.entries = []
        self.add_button = widgets.PushButton(text='Add Membrane')
        self.add_button.clicked.connect(self._add_entry)
        self.extend([self.add_button])

    def _add_entry(self, label=''):
        entry = widgets.LineEdit(value= label)
        remove_button = widgets.PushButton(text='Remove')
        container = widgets.Container(layout='horizontal')
        container.extend([entry, remove_button])

        def remove():
            self.entries.remove((entry,container))
            self.remove(container)

        remove_button.clicked.connect(remove)
        self.entries.append((entry, container)) 
        self.insert(-1, container)

    def get_values(self):
        return [entry.value for entry, _ in self.entries if entry.value.strip()]
    
    def set_values(self, values):
        # Clear existing
        while self.entries:
            _, container = self.entries[0]
            self.entries.pop(0)
            self.remove(container)
        
        # Add new
        for value in values:
            self._add_entry(value)

class InterDictEditor(widgets.Container):
    """Editor for inter membrane dictionary"""
    def __init__(self):
        super().__init__(layout='vertical')
        self.entries = {}  # key -> (key_edit, value_list_editor, container)
        self.add_button = widgets.PushButton(text='Add Membrane Pair')
        self.add_button.clicked.connect(lambda: self._add_entry())
        self.extend([self.add_button])

    def _add_entry(self, key='', values=None):
        if values is None:
            values = []
            
        key_edit = widgets.LineEdit(value=key, label='Membrane:')
        value_editor = IntraListEditor()  # Reuse IntraListEditor for the target list
        value_editor.set_values(values)
        
        remove_button = widgets.PushButton(text='Remove')
        header = widgets.Container(layout='horizontal')
        header.extend([key_edit, remove_button])
        
        container = widgets.Container(layout='vertical')
        container.extend([header, value_editor])
        
        def remove():
            if key_edit.value in self.entries:
                self.entries.pop(key_edit.value)
                self.remove(container)
                
        remove_button.clicked.connect(remove)
        
        self.entries[key] = (key_edit, value_editor, container)
        self.insert(-1, container)

    def get_values(self):
        return {
            entry[0].value: entry[1].get_values()
            for entry in self.entries.values()
            if entry[0].value.strip()
        }

    def set_values(self, values):
        # Clear existing
        for entry in list(self.entries.values()):
            self.remove(entry[2])
        self.entries.clear()
        
        # Add new
        for key, value_list in values.items():
            self._add_entry(key, value_list)

            
class ConfigEditor(widgets.Container):  
    def __init__(self):
        super().__init__(layout='vertical')  # Specify layout
        
        intra_editor = IntraListEditor()
        inter_editor = InterDictEditor()

        # Create containers for each section
        self.containers = {
            'file': widgets.Container(
                layout='vertical',
                widgets=[
                    widgets.FileEdit(
                        name='config_file',
                        label='Config File',
                        filter='*.yml',
                        mode='r'
                    )
                ]
            ),
            'directories': widgets.Container(
                layout='vertical',
                widgets=[
                    widgets.FileEdit(name='data_dir', label='Data Directory', mode='d'),
                    widgets.FileEdit(name='work_dir', label='Work Directory', mode='d')
                ]
            ),
            'segmentation': SegmentationContainer(),
            'surface': widgets.Container(
                layout='vertical',
                widgets=[
                    widgets.CheckBox(name='angstroms', label='Angstroms Scale', value=False),
                    widgets.CheckBox(name='ultrafine', label='Ultra Fine Mode', value=True),
                    widgets.FloatSpinBox(name='mesh_sampling', label='Mesh Sampling', value=0.99),
                    widgets.CheckBox(name='simplify', label='Simplify', value=False),
                    widgets.SpinBox(name='max_triangles', label='Max Triangles', value=300000),
                    widgets.FloatSpinBox(name='extrapolation_distance', label='Extrapolation Distance', value=1.5),
                    widgets.SpinBox(name='octree_depth', label='Octree Depth', value=7),
                    widgets.FloatSpinBox(name='point_weight', label='Point Weight', value=0.7),
                    widgets.SpinBox(name='neighbor_count', label='Neighbor Count', value=400),
                    widgets.SpinBox(name='smoothing_iterations', label='Smoothing Iterations', value=1)
                ]
            ),
            'curvature_measurements': widgets.Container(  # Note the full name
                layout='vertical',
                widgets=[
                    widgets.SpinBox(name='radius_hit', label='Radius Hit', value=9),
                    widgets.SpinBox(name='min_component', label='Min Component', value=30),
                    widgets.FloatSpinBox(name='exclude_borders', label='Exclude Borders', value=1.0)
                ]
            ),
            
            'measurements': widgets.Container(
                layout='vertical',
                widgets=[
                    widgets.FloatSpinBox(name='mindist', label='Min Distance', value=3.0),
                    widgets.FloatSpinBox(name='maxdist', label='Max Distance', value=400.0),
                    widgets.FloatSpinBox(name='tolerance', label='Tolerance', value=0.1),
                    widgets.CheckBox(name='verticality', label='Measure Verticality', value=True),
                    widgets.CheckBox(name='relative_orientation', label='Relative Orientation', value=True),
                    widgets.Label(value='Intra Membrane Measurements:'),
                    intra_editor,
                    widgets.Label(value='Inter-membrane Measurements:'),
                    inter_editor
                ]
            ),
            'cores': widgets.Container(
                layout='vertical',
                widgets=[
                    widgets.SpinBox(name='cores', label='CPU Cores', value=4)
                ]
            ),
        }
        
        # Add sections to main container
        self.extend([
            widgets.Label(value='Configuration Editor'),
            self.containers['file'],
            widgets.Label(value='Directories'),
            self.containers['directories'],
            widgets.Label(value='Segmentation Values'),
            self.containers['segmentation'],
            widgets.Label(value='Surface Generation'),
            self.containers['surface'],
            widgets.Label(value='Curvature Measurements'),  
            self.containers['curvature_measurements'],
            widgets.Label(value='Measurements'),
            self.containers['measurements'],
            self.containers['cores'],
            widgets.PushButton(text='Save Configuration', name='save_button')

        ])
        
        self._intra_editor = intra_editor
        self._inter_editor = inter_editor

        # Connect signals
        self.containers['file'].config_file.changed.connect(self._load_config)
        self.save_button.clicked.connect(self._save_config)
        
        self.yaml_preserver = None

    def set_widgets_enabled(self, enabled: bool):
        """Enable or disable all widgets"""
        # Disable all container widgets
        for container in self.containers.values():
            if hasattr(container, 'native'):
                for child in container.native.findChildren(QWidget):
                    child.setEnabled(enabled)
            
        # Disable save button
        self.save_button.enabled = enabled

    def _load_config(self, file_path: str):
        """Load configuration from file"""
        if not file_path:
            return
            
        try:
            self.yaml_preserver = ConfigYAMLPreserver(Path(file_path))
            config = self.yaml_preserver.yaml_data
            
            # Update widget values
            self._set_values(config)
            logging.info(f"Loaded configuration from {file_path}")
            
        except Exception as e:
            logging.error(f"Error loading config: {str(e)}")

    def _get_values(self) -> dict:
        """Get current values from widgets"""
        return {
            'data_dir': str(self.containers['directories'].data_dir.value),
            'work_dir': str(self.containers['directories'].work_dir.value),
            'segmentation_values': self.containers['segmentation'].get_values(),
            'surface_generation': {
                'angstroms': self.containers['surface'].angstroms.value,
                'ultrafine': self.containers['surface'].ultrafine.value,
                'mesh_sampling': self.containers['surface'].mesh_sampling.value,
                'simplify': self.containers['surface'].simplify.value,
                'max_triangles': self.containers['surface'].max_triangles.value,
                'extrapolation_distance': self.containers['surface'].extrapolation_distance.value,
                'octree_depth': self.containers['surface'].octree_depth.value,
                'point_weight': self.containers['surface'].point_weight.value,
                'neighbor_count': self.containers['surface'].neighbor_count.value,
                'smoothing_iterations': self.containers['surface'].smoothing_iterations.value
            },
            'curvature_measurements': {
                'radius_hit': self.containers['curvature_measurements'].radius_hit.value,
                'min_component': self.containers['curvature_measurements'].min_component.value,
                'exclude_borders': self.containers['curvature_measurements'].exclude_borders.value
            },
            'distance_and_orientation_measurements': {
                'mindist': self.containers['measurements'].mindist.value,
                'maxdist': self.containers['measurements'].maxdist.value,
                'tolerance': self.containers['measurements'].tolerance.value,
                'verticality': self.containers['measurements'].verticality.value,
                'relative_orientation': self.containers['measurements'].relative_orientation.value,
                'intra': self._intra_editor.get_values(),
                'inter': self._inter_editor.get_values()
            },
            'cores': self.containers['cores'].cores.value
        }
        return values

    def _set_values(self, config: dict):
        """Set widget values from config"""
        # Directories
        self.containers['directories'].data_dir.value = config.get('data_dir', '')
        self.containers['directories'].work_dir.value = config.get('work_dir', '')
        
        # Segmentation
        seg_values = config.get('segmentation_values', {})
        self.containers['segmentation']._set_values(seg_values)
        
        # Surface generation
        surf_gen = config.get('surface_generation', {})
        self.containers['surface'].angstroms.value = surf_gen.get('angstroms', False)
        self.containers['surface'].ultrafine.value = surf_gen.get('ultrafine', True)
        self.containers['surface'].mesh_sampling.value = surf_gen.get('mesh_sampling', 0.99)
        self.containers['surface'].simplify.value = surf_gen.get('simplify', False)
        self.containers['surface'].max_triangles.value = surf_gen.get('max_triangles', 300000)
        self.containers['surface'].extrapolation_distance.value = surf_gen.get('extrapolation_distance', 1.5)
        self.containers['surface'].octree_depth.value = surf_gen.get('octree_depth', 7)
        self.containers['surface'].point_weight.value = surf_gen.get('point_weight', 0.7)
        self.containers['surface'].neighbor_count.value = surf_gen.get('neighbor_count', 400)
        self.containers['surface'].smoothing_iterations.value = surf_gen.get('smoothing_iterations', 1)

        
        # Curvature measurements
        curv_meas = config.get('curvature_measurements', {})
        self.containers['curvature_measurements'].radius_hit.value = curv_meas.get('radius_hit', 9)
        self.containers['curvature_measurements'].min_component.value = curv_meas.get('min_component', 30)
        self.containers['curvature_measurements'].exclude_borders.value = curv_meas.get('exclude_borders', 1.0)
        
        # Distance and orientation measurements  
        dist_meas = config.get('distance_and_orientation_measurements', {})
        self.containers['measurements'].mindist.value = dist_meas.get('mindist', 3.0)
        self.containers['measurements'].maxdist.value = dist_meas.get('maxdist', 400.0)
        self.containers['measurements'].tolerance.value = dist_meas.get('tolerance', 0.1)
        self.containers['measurements'].verticality.value = dist_meas.get('verticality', True)
        self.containers['measurements'].relative_orientation.value = dist_meas.get('relative_orientation', True)
        self._intra_editor.set_values(dist_meas.get('intra', []))
        self._inter_editor.set_values(dist_meas.get('inter', {}))
        
        # Cores
        self.containers['cores'].cores.value = config.get('cores', 4)

    def _save_config(self):
        """Save current configuration"""
        if not self.yaml_preserver:
            logging.warning("No configuration file loaded")
            return
            
        try:
            # Get current values and update
            values = self._get_values()
            self.yaml_preserver.update(values)
            self.yaml_preserver.save()
            logging.info("Configuration saved successfully")
            
        except Exception as e:
            logging.error(f"Error saving configuration: {str(e)}")