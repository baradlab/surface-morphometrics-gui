import vtk
from vtk.util import numpy_support
import numpy as np
from napari.layers import Surface
import os
import glob
from magicgui import widgets
from qtpy.QtCore import QTimer
from magicgui.widgets import FloatRangeSlider, FloatSpinBox
from qtpy.QtWidgets import QWidget, QVBoxLayout, QPushButton, QSizePolicy, QScrollArea, QFileDialog
from qtpy.QtCore import Qt

# We implement our own camera-following lighting directly on vispy's
# ShadingFilter rather than using napari-threedee's LightingControl,
# which has compatibility issues with shading_filter initialization.

# Import libigl for ambient occlusion
try:
    import igl
    IGL_AVAILABLE = True
except ImportError:
    IGL_AVAILABLE = False
    print("Warning: libigl not available for ambient occlusion")


class MeshViewer(QWidget):
    def __init__(self, viewer, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.viewer = viewer

        # Initialize automatic lighting and ambient occlusion
        self._initialize_automatic_lighting_ao()

        # Create main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create a completely new layout with just the essential controls
        self.controls_container = widgets.Container(layout='vertical', labels=True)
        self.controls_container.native.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.controls_container.native.setMinimumWidth(250)
        self.controls_container.native.layout().setSpacing(8)
        self.controls_container.native.layout().setContentsMargins(10, 10, 10, 10)

        # Load Mesh button
        self.load_mesh_button = QPushButton("Load Mesh")
        self.load_mesh_button.setMinimumWidth(100)
        self.load_mesh_button.setFixedHeight(28)
        self.load_mesh_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.load_mesh_button.clicked.connect(self._on_load_mesh_clicked)

        self.property_selector = widgets.ComboBox(
            label="Property",
            choices=[],
            enabled=False,
            tooltip="Select a property to visualize"
        )

        self.colormap_selector = widgets.ComboBox(
            label="Colormap",
            choices=['viridis', 'plasma', 'inferno', 'magma', 'cividis', 'coolwarm', 'RdBu', 'Spectral', 'hsv', 'jet', 'hot', 'gray'],
            value='viridis',
            enabled=False,
            tooltip="Select colormap for visualization"
        )

        self.auto_apply = widgets.CheckBox(
            label="Auto-apply colormap",
            value=True,
            enabled=False,
            tooltip="Automatically apply appropriate colormap for selected property"
        )

        self.ao_enabled = widgets.CheckBox(
            label="Ambient Occlusion",
            value=True,
            enabled=True,
            tooltip="Toggle ambient occlusion effect on surface meshes"
        )

        self.shading_selector = widgets.ComboBox(
            label="Shading",
            choices=['smooth', 'flat', 'none'],
            value='smooth',
            enabled=True,
            tooltip="Select shading mode for the surface"
        )

        # Universal contrast slider
        self.contrast_slider = FloatRangeSlider(
            label="Contrast",
            value=(0.0, 1.0),
            enabled=False,
            readout=False,
            tracking=True,
            step=0.01,
            tooltip="Adjust the data range for the colormap"
        )
        self.contrast_min = FloatSpinBox(
            label="Min",
            value=0.0,
            enabled=False,
            tooltip="Set minimum value for contrast"
        )
        self.contrast_max = FloatSpinBox(
            label="Max",
            value=1.0,
            enabled=False,
            tooltip="Set maximum value for contrast"
        )

        # Container for slider and spinboxes
        self.contrast_container = widgets.Container(layout='vertical', labels=True)

        # Min/Max row
        self.contrast_minmax_row = widgets.Container(layout='horizontal', labels=True)
        self.contrast_minmax_row.append(self.contrast_min)
        self.contrast_minmax_row.append(self.contrast_max)

        self.contrast_slider.native.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.contrast_container.append(self.contrast_slider)
        self.contrast_container.append(self.contrast_minmax_row)
        self.contrast_container.visible = False

        self.stats_label = widgets.Label(value="No data loaded")

        # Build load mesh row
        mesh_row_container = widgets.Container(layout='horizontal')
        mesh_display_label = widgets.Label(value="Mesh")
        mesh_row_container.append(mesh_display_label)

        button_container = widgets.Container()
        button_container.native.layout().addWidget(self.load_mesh_button)
        mesh_row_container.append(button_container)

        # Add the components to our controls
        self.controls_container.extend([
            mesh_row_container,
            self.property_selector,
            self.colormap_selector,
            self.auto_apply,
            self.ao_enabled,
            self.shading_selector,
            self.stats_label,
            self.contrast_container,
        ])

        # Compact child widget internal margins while keeping outer spacing
        for i in range(self.controls_container.native.layout().count()):
            item = self.controls_container.native.layout().itemAt(i)
            if item and item.widget():
                child_layout = item.widget().layout()
                if child_layout:
                    child_layout.setSpacing(4)
                    child_layout.setContentsMargins(0, 2, 0, 2)

        # Wrap controls in a scroll area so content is scrollable when dock space is tight
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setWidget(self.controls_container.native)
        layout.addWidget(scroll_area)
        self.setMinimumHeight(400)

        # Push all controls to the top so they don't spread out vertically
        self.controls_container.native.layout().addStretch(1)

        # --- Connect Signals ---
        self.viewer.layers.events.inserted.connect(self._on_layer_inserted)
        self.viewer.layers.selection.events.active.connect(self._on_active_layer_changed)
        self.property_selector.changed.connect(self._on_property_changed)
        self.colormap_selector.changed.connect(self._on_colormap_changed)
        self.auto_apply.changed.connect(self._on_auto_apply_changed)
        self.contrast_slider.changed.connect(self._on_contrast_slider_changed)
        self.contrast_min.changed.connect(self._on_contrast_min_changed)
        self.contrast_max.changed.connect(self._on_contrast_max_changed)
        self.ao_enabled.changed.connect(self._on_ao_toggled)
        self.shading_selector.changed.connect(self._on_shading_changed)

    def _on_load_mesh_clicked(self):
        """Open a file dialog and load the selected mesh file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open Mesh File",
            "",
            "Mesh Files (*.vtp *.ply *.stl *.obj);;VTP Files (*.vtp);;PLY Files (*.ply);;STL Files (*.stl);;OBJ Files (*.obj);;All Files (*)"
        )
        if not filepath:
            return

        self._load_mesh_file(filepath)

    def _load_mesh_file(self, filepath):
        """Load a mesh file using VTK and add it to napari."""
        ext = os.path.splitext(filepath)[1].lower()

        reader = None
        if ext == '.vtp':
            reader = vtk.vtkXMLPolyDataReader()
        elif ext == '.ply':
            reader = vtk.vtkPLYReader()
        elif ext == '.stl':
            reader = vtk.vtkSTLReader()
        elif ext == '.obj':
            reader = vtk.vtkOBJReader()
        else:
            print(f"Unsupported file format: {ext}")
            return

        reader.SetFileName(filepath)
        reader.Update()
        polydata = reader.GetOutput()

        if polydata is None or polydata.GetNumberOfPoints() == 0:
            print(f"Failed to load mesh from {filepath}")
            return

        # Extract vertices
        vtk_points = polydata.GetPoints()
        vertices = numpy_support.vtk_to_numpy(vtk_points.GetData())

        # Extract faces
        vtk_cells = polydata.GetPolys()
        if vtk_cells is None or vtk_cells.GetNumberOfCells() == 0:
            print(f"No polygon data in {filepath}")
            return

        cell_array = numpy_support.vtk_to_numpy(vtk_cells.GetData())
        # VTK cell array format: [n_verts, v0, v1, v2, n_verts, v0, v1, v2, ...]
        # For triangles: [3, v0, v1, v2, 3, v0, v1, v2, ...]
        n_cells = vtk_cells.GetNumberOfCells()
        # Assume triangular faces (stride of 4: count + 3 vertices)
        faces = cell_array.reshape(n_cells, -1)[:, 1:]  # skip the vertex count column

        # Default scalar values (ones so AO can attenuate them)
        values = np.ones(len(vertices))
        mesh_tuple = (vertices, faces, values)

        name = os.path.splitext(os.path.basename(filepath))[0]
        metadata = {'source_vtp_path': filepath}

        self.viewer.add_surface(mesh_tuple, name=name, metadata=metadata)

    def _is_vtp_surface_layer(self, layer):
        """Checks if a layer is a Surface derived from a VTP file."""
        if not isinstance(layer, Surface):
            return False

        # Check if layer has VTP metadata
        if hasattr(layer, 'metadata') and layer.metadata:
            if layer.metadata.get('vtp_initialized', False):
                return True
            if layer.metadata.get('vtp_scalar_data'):
                return True
            if layer.metadata.get('vtp_path'):
                return True

        # Check if layer has source path
        if hasattr(layer, 'source') and hasattr(layer.source, 'path'):
            return layer.source.path and layer.source.path.endswith('.vtp')

        # Check if layer name suggests it's from VTP (including renamed layers)
        if hasattr(layer, 'name') and layer.name:
            if '.vtp' in layer.name.lower():
                return True
            if '[' in layer.name and ']' in layer.name:
                property_part = layer.name.split('[')[1].split(']')[0]
                if property_part.startswith(('Cell_', 'Point_')):
                    return True

        # Check if layer has scalar data (might be from VTP)
        if hasattr(layer, 'data') and len(layer.data) == 3:
            vertices, faces, values = layer.data
            if values is not None and len(values) > 0:
                return True

        return False

    def _on_layer_inserted(self, event):
        """Handle new layer insertion."""
        layer = event.value

        if isinstance(layer, Surface):
            # 1. Initialize VTP data (loads scalars, sets initial property)
            self._initialize_vtp_layer(layer)

            # 2. Apply lighting and AO only after VTP init is complete
            self._apply_automatic_lighting_ao(layer)

    def _on_active_layer_changed(self, event):
        """Update UI when the active layer changes."""
        layer = event.value
        if layer and isinstance(layer, Surface):
            if not layer.metadata.get('vtp_initialized'):
                self._initialize_vtp_layer(layer)
            self._update_ui_from_layer(layer)
        else:
            self._disable_controls()

    def _disable_controls(self):
        """Disable all controls when no VTP layer is active."""
        self.property_selector.enabled = False
        self.colormap_selector.enabled = False
        self.auto_apply.enabled = False

    def _initialize_vtp_layer(self, layer):
        """Read VTP file once, cache data, and apply initial colormap."""
        if layer.metadata.get('vtp_initialized', False):
            return

        vtp_path = None

        # Priority 1: Check for a source path embedded in metadata (most reliable)
        if layer.metadata.get('source_vtp_path'):
            candidate_path = layer.metadata['source_vtp_path']
            if os.path.exists(candidate_path):
                vtp_path = candidate_path

        # Priority 2: Check napari's native layer.source.path (for drag-and-drop)
        if not vtp_path and hasattr(layer, 'source') and hasattr(layer.source, 'path') and layer.source.path:
            candidate_path = str(layer.source.path)
            if os.path.exists(candidate_path):
                vtp_path = candidate_path

        # Priority 3: Search filesystem and match name, or use single-file heuristic
        if not vtp_path:
            search_dirs = {os.getcwd(), os.path.dirname(os.getcwd())}

            all_vtp_files = []
            for d in search_dirs:
                all_vtp_files.extend(glob.glob(os.path.join(d, "*.vtp")))

            unique_vtp_files = list(set(all_vtp_files))

            for f_path in unique_vtp_files:
                base_filename = os.path.splitext(os.path.basename(f_path))[0]
                if layer.name.startswith(base_filename):
                    vtp_path = f_path
                    break

            if not vtp_path and len(unique_vtp_files) == 1:
                vtp_path = unique_vtp_files[0]

        if vtp_path and os.path.exists(vtp_path):
            self._load_vtp_data(layer, vtp_path)
        else:
            self._extract_data_from_layer(layer)

    def _load_vtp_data(self, layer, vtp_path):
        """Load data from VTP file."""
        try:
            reader = vtk.vtkXMLPolyDataReader()
            reader.SetFileName(vtp_path)
            reader.Update()

            polydata = reader.GetOutput()
            point_data = polydata.GetPointData()
            cell_data = polydata.GetCellData()

            scalar_data = {}
            scalar_names = []

            for i in range(point_data.GetNumberOfArrays()):
                array = point_data.GetArray(i)
                name = point_data.GetArrayName(i)
                scalar_names.append(f"Point_{name}")
                scalar_data[f"Point_{name}"] = numpy_support.vtk_to_numpy(array)

            for i in range(cell_data.GetNumberOfArrays()):
                array = cell_data.GetArray(i)
                name = cell_data.GetArrayName(i)
                scalar_names.append(f"Cell_{name}")
                scalar_data[f"Cell_{name}"] = numpy_support.vtk_to_numpy(array)

            if not scalar_names:
                self._extract_data_from_layer(layer)
                return

            layer.metadata['vtp_scalar_data'] = scalar_data
            layer.metadata['vtp_scalar_names'] = scalar_names
            layer.metadata['vtp_path'] = vtp_path

            initial_property = self._select_initial_scalar(scalar_names)

            if initial_property:
                self._update_layer_data(layer, initial_property)
                layer.metadata['vtp_initialized'] = True
                self._update_ui_from_layer(layer)
            else:
                self._extract_data_from_layer(layer)

        except Exception as e:
            print(f"Error loading VTP file: {e}")
            import traceback
            traceback.print_exc()
            self._extract_data_from_layer(layer)

    def _extract_data_from_layer(self, layer):
        """Extract data from existing layer if VTP file is not available."""
        if len(layer.data) == 3:
            vertices, faces, values = layer.data

            scalar_data = {'Current_Values': values}
            scalar_names = ['Current_Values']

            layer.metadata['vtp_scalar_data'] = scalar_data
            layer.metadata['vtp_scalar_names'] = scalar_names
            layer.metadata['vtp_initialized'] = True
            layer.metadata['active_property'] = 'Current_Values'

            self._update_ui_from_layer(layer)

    def _create_user_friendly_names(self, scalar_names):
        """Create a clean list of property names, similar to the raw names in Paraview."""
        friendly_names = {}
        display_names = ["Solid Color"]

        for name in scalar_names:
            if name.startswith('Point_'):
                clean_name = name[6:]
            elif name.startswith('Cell_'):
                clean_name = name[5:]
            else:
                clean_name = name

            friendly_names[clean_name] = name
            display_names.append(clean_name)

        friendly_names['Solid Color'] = 'solid_color'

        return friendly_names, display_names

    def _select_initial_scalar(self, scalar_names):
        """Select the best initial scalar to display."""
        priority_arrays = [
            'gauss_curvature', 'mean_curvature', 'min_curvature', 'max_curvature',
            'shape_index_VV', 'curvedness_VV',
            'area',
            'orientation_class',
            'kappa_1', 'kappa_2'
        ]

        for priority in priority_arrays:
            for name in scalar_names:
                if priority.lower() in name.lower():
                    return name

        if scalar_names:
            return scalar_names[0]

        return None

    def _update_ui_from_layer(self, layer):
        """Populate UI controls based on the selected layer's data."""
        scalar_names = layer.metadata.get('vtp_scalar_names', [])

        if not scalar_names:
            self._disable_controls()
            return

        friendly_names, display_names = self._create_user_friendly_names(scalar_names)
        layer.metadata['friendly_names'] = friendly_names

        with self.property_selector.changed.blocked():
            self.property_selector.choices = display_names
            current_property = layer.metadata.get('active_property', scalar_names[0])

            current_friendly = None
            for friendly, original in friendly_names.items():
                if original == current_property:
                    current_friendly = friendly
                    break

            if current_friendly is None or current_friendly not in display_names:
                current_friendly = display_names[0]
                current_property = friendly_names[current_friendly]
                layer.metadata['active_property'] = current_property

            self.property_selector.value = current_friendly
            self.property_selector.enabled = True

        with self.colormap_selector.changed.blocked():
            self.colormap_selector.value = layer.colormap.name
            self.colormap_selector.enabled = True

        self.auto_apply.enabled = True

        self._update_statistics(layer)
        self._update_contrast_slider_state(layer)

    def _find_active_surface_layer(self):
        """Find the active surface layer, falling back to any VTP surface layer."""
        layer = self.viewer.layers.selection.active
        if layer and self._is_vtp_surface_layer(layer):
            return layer
        for potential_layer in self.viewer.layers:
            if self._is_vtp_surface_layer(potential_layer):
                return potential_layer
        return None

    def _on_ao_toggled(self, value):
        """Handle AO checkbox toggle."""
        layer = self._find_active_surface_layer()
        if layer:
            active = layer.metadata.get('active_property')
            if active and active != 'solid_color':
                self._update_layer_data(layer, active)

    def _on_shading_changed(self, value):
        """Handle shading mode change."""
        layer = self._find_active_surface_layer()
        if layer:
            self._setup_shading(layer)

    def _on_property_changed(self, new_property: str):
        """Handle user selecting a new property from the dropdown."""
        layer = self.viewer.layers.selection.active

        if not layer or not self._is_vtp_surface_layer(layer):
            for potential_layer in self.viewer.layers:
                if self._is_vtp_surface_layer(potential_layer):
                    layer = potential_layer
                    break

        if layer and self._is_vtp_surface_layer(layer):
            friendly_names = layer.metadata.get('friendly_names', {})
            original_property = friendly_names.get(new_property, new_property)

            self._update_layer_data(layer, original_property)
            self._update_ui_from_layer(layer)

    def _on_colormap_changed(self, new_colormap: str):
        """Handle user selecting a new colormap from the dropdown."""
        layer = self.viewer.layers.selection.active
        if layer and self._is_vtp_surface_layer(layer):
            layer.colormap = new_colormap

    def _on_auto_apply_changed(self):
        """Handle auto-apply checkbox changes."""
        layer = self.viewer.layers.selection.active
        if layer and self._is_vtp_surface_layer(layer):
            self._update_layer_data(layer, layer.metadata['active_property'])

    def _update_layer_data(self, layer, scalar_array_name):
        """Update the layer's data tuple to trigger a refresh."""

        # Handle Solid Color selection
        if scalar_array_name == 'solid_color':
            if len(layer.data) == 3:
                vertices, faces, _ = layer.data
                layer.data = (vertices.copy(), faces.copy())
                self._setup_shading(layer)
            layer.metadata['active_property'] = 'solid_color'
            layer.name = layer.name.split(' [')[0]
            self._update_ui_from_layer(layer)
            return

        scalar_data = layer.metadata.get('vtp_scalar_data', {})
        new_values = scalar_data.get(scalar_array_name)

        if new_values is None:
            return

        if len(layer.data) == 3:
            vertices, faces, _ = layer.data
        else:
            vertices, faces = layer.data

        n_vertices = len(vertices)
        n_values = len(new_values)

        is_vector_data = len(new_values.shape) > 1 and new_values.shape[1] == 3

        if n_values != n_vertices:
            if is_vector_data:
                vertex_values = self._cell_to_vertex_interpolation_vector(faces, new_values, n_vertices)
            else:
                vertex_values = self._cell_to_vertex_interpolation(faces, new_values, n_vertices)
            new_values = vertex_values

        if len(new_values.shape) > 1:
            new_values = np.linalg.norm(new_values, axis=1)

        # Compute contrast limits from the ORIGINAL data (before AO)
        # so that AO-darkened areas actually appear darker in the colormap.
        finite_values = new_values[np.isfinite(new_values)]
        if len(finite_values) > 0:
            original_limits = (float(np.min(finite_values)), float(np.max(finite_values)))
        else:
            original_limits = (0.0, 1.0)

        # Apply ambient occlusion if available and enabled
        ao_factors = layer.metadata.get('ao_factors')
        if ao_factors is not None and self.ao_enabled.value:
            if len(new_values.shape) == 1 and len(ao_factors) == len(new_values):
                new_values = new_values * ao_factors

        layer.data = (vertices.copy(), faces.copy(), new_values)

        # Reassigning layer.data rebuilds the vispy visual; re-apply shading
        self._setup_shading(layer)

        # Use the original (pre-AO) range for contrast limits
        layer.contrast_limits = original_limits
        layer.metadata['active_property'] = scalar_array_name

        base_name = layer.name.split(' [')[0]
        layer.name = f'{base_name} [{scalar_array_name}]'

        try:
            if layer not in self.viewer.layers.selection:
                self.viewer.layers.selection.add(layer)
        except Exception:
            pass

        if self.auto_apply.value:
            self._apply_auto_colormap(layer, scalar_array_name, new_values)

    def _cell_to_vertex_interpolation_vector(self, faces, cell_values, n_vertices):
        """Convert cell-based vector data to vertex-based vector data by averaging."""
        vertex_values = np.zeros((n_vertices, 3))
        vertex_counts = np.zeros(n_vertices)

        for i, face in enumerate(faces):
            face_vector = cell_values[i]
            for vertex_idx in face:
                vertex_values[vertex_idx] += face_vector
                vertex_counts[vertex_idx] += 1

        vertex_counts[vertex_counts == 0] = 1
        vertex_values = vertex_values / vertex_counts[:, np.newaxis]

        return vertex_values

    def _cell_to_vertex_interpolation(self, faces, cell_values, n_vertices):
        """Convert cell-based scalar data to vertex-based data by averaging."""
        vertex_values = np.zeros(n_vertices)
        vertex_counts = np.zeros(n_vertices)

        for i, face in enumerate(faces):
            face_value = cell_values[i]
            for vertex_idx in face:
                vertex_values[vertex_idx] += face_value
                vertex_counts[vertex_idx] += 1

        vertex_counts[vertex_counts == 0] = 1
        vertex_values = vertex_values / vertex_counts

        return vertex_values

    def _update_statistics(self, layer):
        """Update statistics display."""
        current_property = layer.metadata.get('active_property')
        if current_property and current_property in layer.metadata.get('vtp_scalar_data', {}):
            data = layer.metadata['vtp_scalar_data'][current_property]

            stats_text = f"Property: {current_property}\n"
            stats_text += f"Shape: {data.shape}\n"
            stats_text += f"Range: [{np.min(data):.3f}, {np.max(data):.3f}]\n"
            stats_text += f"Mean: {np.mean(data):.3f}\n"
            stats_text += f"Std: {np.std(data):.3f}\n"
            stats_text += f"Has NaN: {np.any(np.isnan(data))}\n"
            stats_text += f"Has Inf: {np.any(np.isinf(data))}"

            self.stats_label.value = stats_text

    def _apply_auto_colormap(self, layer, property_name, data):
        """Automatically apply appropriate colormap based on property type."""
        property_lower = property_name.lower()

        is_diverging = np.nanmin(data) < 0 and np.nanmax(data) > 0

        if 'orientation' in property_lower:
            layer.colormap = 'hsv'
        elif 'shape_index' in property_lower:
            layer.colormap = 'Spectral'
        elif is_diverging:
            layer.colormap = 'coolwarm'
        else:
            layer.colormap = 'viridis'

        with self.colormap_selector.changed.blocked():
            self.colormap_selector.value = layer.colormap.name

    def _update_contrast_slider_state(self, layer):
        active_property = layer.metadata.get('active_property')
        if active_property == 'solid_color' or len(layer.data) != 3:
            self.contrast_container.visible = False
            return

        all_values = layer.metadata['vtp_scalar_data'][active_property]
        if hasattr(all_values, 'ndim') and all_values.ndim > 1:
            self.contrast_container.visible = False
            return
        finite_values = all_values[np.isfinite(all_values)]
        if len(finite_values) == 0:
            self.contrast_container.visible = False
            return
        data_min, data_max = float(np.min(finite_values)), float(np.max(finite_values))

        if np.isclose(data_min, data_max):
            self.contrast_container.visible = False
            return

        self.contrast_container.visible = True
        self.contrast_slider.enabled = True
        self.contrast_min.enabled = True
        self.contrast_max.enabled = True

        current_min, current_max = layer.contrast_limits

        with self.contrast_slider.changed.blocked(), self.contrast_min.changed.blocked(), self.contrast_max.changed.blocked():
            self.contrast_slider.min = data_min
            self.contrast_slider.max = data_max
            self.contrast_min.min = data_min
            self.contrast_min.max = data_max
            self.contrast_max.min = data_min
            self.contrast_max.max = data_max

            clamped_min = max(min(current_min, data_max), data_min)
            clamped_max = max(min(current_max, data_max), data_min)

            actual_min = self.contrast_min.min
            actual_max = self.contrast_max.max

            final_min = max(min(clamped_min, actual_max), actual_min)
            final_max = max(min(clamped_max, actual_max), actual_min)

            self.contrast_slider.value = (final_min, final_max)
            self.contrast_min.value = final_min
            self.contrast_max.value = final_max

    def _on_contrast_slider_changed(self, value):
        layer = self.viewer.layers.selection.active
        if layer and self._is_vtp_surface_layer(layer):
            layer.contrast_limits = value
            with self.contrast_min.changed.blocked(), self.contrast_max.changed.blocked():
                min_val = max(min(value[0], self.contrast_min.max), self.contrast_min.min)
                max_val = max(min(value[1], self.contrast_max.max), self.contrast_max.min)
                self.contrast_min.value = min_val
                self.contrast_max.value = max_val

    def _on_contrast_min_changed(self, value):
        layer = self.viewer.layers.selection.active
        if layer and self._is_vtp_surface_layer(layer):
            min_val = value
            max_val = self.contrast_max.value
            if min_val > max_val:
                min_val = max_val
            layer.contrast_limits = (min_val, max_val)
            with self.contrast_slider.changed.blocked():
                clamped_min = max(min(min_val, self.contrast_slider.max), self.contrast_slider.min)
                clamped_max = max(min(max_val, self.contrast_slider.max), self.contrast_slider.min)
                self.contrast_slider.value = (clamped_min, clamped_max)

    def _on_contrast_max_changed(self, value):
        layer = self.viewer.layers.selection.active
        if layer and self._is_vtp_surface_layer(layer):
            min_val = self.contrast_min.value
            max_val = value
            if max_val < min_val:
                max_val = min_val
            layer.contrast_limits = (min_val, max_val)
            with self.contrast_slider.changed.blocked():
                clamped_min = max(min(min_val, self.contrast_slider.max), self.contrast_slider.min)
                clamped_max = max(min(max_val, self.contrast_slider.max), self.contrast_slider.min)
                self.contrast_slider.value = (clamped_min, clamped_max)

    def _initialize_automatic_lighting_ao(self):
        """Initialize ambient occlusion and smooth shading."""
        self.processed_layers = set()

    def _get_vispy_visual(self, layer):
        """Get the vispy visual for a napari layer."""
        try:
            return self.viewer.window._qt_window._qt_viewer.layer_to_visual[layer]
        except Exception:
            return None

    def _compute_ao_factors(self, vertices, faces):
        """Compute per-vertex ambient occlusion using normal divergence."""
        normals = igl.per_vertex_normals(vertices, faces)
        adj = igl.adjacency_list(faces)
        n_verts = len(vertices)
        raw_ao = np.zeros(n_verts)

        for i in range(n_verts):
            neighbors = adj[i]
            if len(neighbors) < 2:
                raw_ao[i] = 1.0
                continue
            neighbor_normals = normals[neighbors]
            dots = neighbor_normals @ normals[i]
            raw_ao[i] = np.mean(dots)

        ao_min = 0.25
        ao_normalized = np.clip((raw_ao + 1.0) / 2.0, 0, 1)
        ao_factors = ao_min + (1.0 - ao_min) * ao_normalized
        return ao_factors

    def _apply_automatic_lighting_ao(self, layer):
        """Apply ambient occlusion and smooth shading to a surface layer."""
        if not isinstance(layer, Surface):
            return

        if layer in self.processed_layers:
            return
        self.processed_layers.add(layer)

        if IGL_AVAILABLE:
            try:
                if len(layer.data) >= 2:
                    vertices, faces = layer.data[0], layer.data[1]
                    ao_factors = self._compute_ao_factors(
                        vertices, faces.astype(int)
                    )
                    layer.metadata['ao_factors'] = ao_factors
                    active = layer.metadata.get('active_property')
                    if active and active != 'solid_color':
                        self._update_layer_data(layer, active)
            except Exception as e:
                print(f"Warning: AO computation failed for {layer.name}: {e}")

        self._setup_shading(layer)

    def _setup_shading(self, layer):
        """Configure shading based on the current selector value."""
        try:
            if layer not in self.viewer.layers:
                return
            layer.shading = self.shading_selector.value
            if layer.shading != 'none':
                QTimer.singleShot(200, lambda l=layer: self._configure_shading_filter(l))
        except Exception as e:
            print(f"Warning: Could not set up shading for {layer.name}: {e}")

    def _configure_shading_filter(self, layer, retries=5):
        """Configure the vispy shading filter with directional lighting."""
        try:
            if layer not in self.viewer.layers:
                return
            visual = self._get_vispy_visual(layer)
            if visual is None or visual.node.shading_filter is None:
                if retries > 0:
                    QTimer.singleShot(100, lambda l=layer, r=retries-1: self._configure_shading_filter(l, r))
                return
            sf = visual.node.shading_filter
            # Moderate ambient so AO darkening and flat/smooth differences
            # are clearly visible, with strong directional light.
            sf.ambient_light = (1, 1, 1, 0.35)
            sf.diffuse_light = (1, 1, 1, 0.55)
            sf.specular_light = (1, 1, 1, 0.1)
            sf.light_dir = (0, -1, 1)
        except Exception:
            pass
