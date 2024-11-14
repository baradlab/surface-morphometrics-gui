import napari
from magicgui import magicgui, widgets
import yaml
from pathlib import Path
import re
import logging
from typing import Dict, Any, List, Optional

class ConfigYAMLPreserver:
    """Preserves YAML formatting while allowing updates"""
    
    def __init__(self, yaml_path: Path):
        self.yaml_path = Path(yaml_path)
        with open(self.yaml_path, 'r') as f:
            self.content = f.read()
        self.yaml_data = yaml.safe_load(self.content)
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
            return '\n'.join(f"{indent}- {self._format_value(item)}" for item in value)
        elif isinstance(value, dict):
            nested = []
            for k, v in value.items():
                formatted_value = self._format_value(v, indent_level + 2)
                if '\n' in formatted_value:
                    nested.append(f"{indent}{k}:\n{formatted_value}")
                else:
                    nested.append(f"{indent}{k}: {formatted_value}")
            return '\n'.join(nested)
        return str(value)

    def _find_yaml_path(self, path: List[str]) -> tuple:
        """Find the line number and indentation for a given path"""
        current_indent = 0
        current_path = []
        lines = self.content.splitlines()
        
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if not stripped or stripped.startswith('#'):
                continue
                
            indent = len(line) - len(stripped)
            if indent <= current_indent:
                while current_path and indent <= current_indent:
                    current_path.pop()
                    current_indent -= 2
                    
            if ':' in stripped:
                key = stripped.split(':', 1)[0].strip()
                current_path.append(key)
                current_indent = indent
                
                if current_path == path:
                    # Find the end of this section
                    end_line = i + 1
                    while end_line < len(lines):
                        next_line = lines[end_line].lstrip()
                        if not next_line or next_line.startswith('#'):
                            end_line += 1
                            continue
                        next_indent = len(lines[end_line]) - len(lines[end_line].lstrip())
                        if next_indent <= indent:
                            break
                        end_line += 1
                    return i, indent, end_line
                    
        return -1, 0, -1

    def update(self, updates: Dict[str, Any]) -> None:
        """Update values while preserving formatting"""
        lines = self.content.splitlines()
        
        def update_nested(current_updates: Dict[str, Any], prefix: List[str] = None):
            if prefix is None:
                prefix = []
                
            for key, value in current_updates.items():
                current_path = prefix + [key]
                
                # Check if this is a static field that shouldn't be updated
                skip_update = False
                temp_dict = self._static_fields
                for path_part in current_path:
                    if path_part in temp_dict:
                        temp_dict = temp_dict[path_part]
                        if not isinstance(temp_dict, dict):
                            skip_update = True
                            break
                    else:
                        temp_dict = {}
                
                if skip_update:
                    continue
                
                if isinstance(value, dict):
                    update_nested(value, current_path)
                else:
                    line_num, indent, end_line = self._find_yaml_path(current_path)
                    if line_num >= 0:
                        formatted_value = self._format_value(value, indent + 2)
                        if '\n' in formatted_value:
                            lines[line_num] = f"{' ' * indent}{key}:\n{formatted_value}"
                            # Remove any old nested lines
                            if end_line > line_num + 1:
                                del lines[line_num + 1:end_line]
                        else:
                            lines[line_num] = f"{' ' * indent}{key}: {formatted_value}"

        update_nested(updates)
        self.content = '\n'.join(lines)
        # Update internal representation
        self.yaml_data = yaml.safe_load(self.content)

    def save(self) -> None:
        """Save changes back to file"""
        backup_path = self.yaml_path.with_suffix('.bak')
        self.yaml_path.rename(backup_path)
        
        try:
            with open(self.yaml_path, 'w') as f:
                f.write(self.content)
        except Exception as e:
            backup_path.rename(self.yaml_path)
            raise e

class ConfigEditor(widgets.Container):  
    def __init__(self):
        super().__init__(layout='vertical')  # Specify layout
        
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
            'segmentation': widgets.Container(
                layout='vertical',
                widgets=[
                    widgets.SpinBox(name='omm_value', label='OMM Value', value=1),
                    widgets.SpinBox(name='imm_value', label='IMM Value', value=2),
                    widgets.SpinBox(name='er_value', label='ER Value', value=3)
                ]
            ),
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
                    widgets.CheckBox(name='relative_orientation', label='Relative Orientation', value=True)
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
        
        # Connect signals
        self.containers['file'].config_file.changed.connect(self._load_config)
        self.save_button.clicked.connect(self._save_config)
        
        self.yaml_preserver = None

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
            'segmentation_values': {
                'OMM': self.containers['segmentation'].omm_value.value,
                'IMM': self.containers['segmentation'].imm_value.value,
                'ER': self.containers['segmentation'].er_value.value
            },
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
                'intra': ['IMM', 'OMM', 'ER'],
                'inter': {'OMM': ['IMM', 'ER']}
            },
            'cores': self.containers['cores'].cores.value
        }

    def _set_values(self, config: dict):
        """Set widget values from config"""
        # Directories
        self.containers['directories'].data_dir.value = config.get('data_dir', '')
        self.containers['directories'].work_dir.value = config.get('work_dir', '')
        
        # Segmentation
        seg_values = config.get('segmentation_values', {})
        self.containers['segmentation'].omm_value.value = seg_values.get('OMM', 1)
        self.containers['segmentation'].imm_value.value = seg_values.get('IMM', 2)
        self.containers['segmentation'].er_value.value = seg_values.get('ER', 3)
        
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

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Create and show viewer with widget
    viewer = napari.Viewer()
    widget = ConfigEditor()
    viewer.window.add_dock_widget(
        widget,
        name='Configuration Editor',
        area='right'
    )
    napari.run()