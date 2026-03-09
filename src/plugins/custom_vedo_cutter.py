from napari_vedo_bridge._cutter_widget import VedoCutter
from napari_vedo_bridge._cutter_widget import is_ragged
import vtk
from vtk.util import numpy_support
import numpy as np
from napari.layers import Surface
import os
import glob
from magicgui import widgets
from qtpy.QtCore import QTimer
from magicgui.widgets import FloatRangeSlider, FloatSpinBox
from qtpy.QtWidgets import QSizePolicy, QScrollArea
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


class CustomVedoCutter(VedoCutter):
    def __init__(self, *args, **kwargs):
        self.viewer = args[0]
        super().__init__(*args, **kwargs)

        # Initialize automatic lighting and ambient occlusion
        self._initialize_automatic_lighting_ao()

        # Hide all UI elements from parent class
        self._hide_parent_ui_elements()

        # Extract the load mesh button from parent class
        self.load_mesh_button = None
        if hasattr(self, 'pushButton_load_mesh'):
            self.load_mesh_button = self.pushButton_load_mesh

        # Create a completely new layout with just the essential controls
        self.controls_container = widgets.Container(layout='vertical', labels=True)
        self.controls_container.native.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.controls_container.native.setMinimumWidth(250)
        self.controls_container.native.layout().setSpacing(8)
        self.controls_container.native.layout().setContentsMargins(10, 10, 10, 10)

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

        # Universal contrast slider
        self.contrast_slider = FloatRangeSlider(
            label="Contrast",
            value=(0.0, 1.0),
            enabled=False,
            readout=False,  
            tracking=True, 
            step=0.01,  # Set a reasonable step size
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

        # Container for slider and spinboxes — vertical layout to avoid cramping
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

        # Create a clean container for the load mesh button with a Mesh label beside it
        if self.load_mesh_button:
            mesh_row_container = widgets.Container(layout='horizontal')
            mesh_display_label = widgets.Label(value="Mesh")
            mesh_row_container.append(mesh_display_label)

            self.load_mesh_button.setMinimumWidth(100)
            self.load_mesh_button.setFixedHeight(28)
            self.load_mesh_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
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
                self.stats_label,
                self.contrast_container,
            ])
        else:
            self.controls_container.extend([
                self.property_selector,
                self.colormap_selector,
                self.auto_apply,
                self.ao_enabled,
                self.stats_label,
                self.contrast_container,
            ])

        # Clear the existing layout and add our clean container
        layout = self.layout()
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

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

        # --- Auto-send to napari functionality ---
        self.last_mesh_filename = None
        self._start_auto_send_monitor()



    def _start_auto_send_monitor(self):
        """Start monitoring for new meshes and automatically send them to napari."""
        self.mesh_monitor_timer = QTimer()
        self.mesh_monitor_timer.timeout.connect(self._check_for_new_mesh)
        self.mesh_monitor_timer.start(500)  # Check every 500ms

    def _check_for_new_mesh(self):
        """Check if a new mesh has been loaded and send it to napari."""
        try:
            if hasattr(self, 'mesh') and self.mesh is not None:
                current_filename = getattr(self.mesh, 'filename', None)
                if current_filename and current_filename != self.last_mesh_filename:
                    self.last_mesh_filename = current_filename
                    self.send_to_napari()
        except Exception:
            pass

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
            # Check for VTP file extension
            if '.vtp' in layer.name.lower():
                return True
            # Check for property names in layer name (e.g., "Mesh [Cell_gauss_curvature]")
            if '[' in layer.name and ']' in layer.name:
                property_part = layer.name.split('[')[1].split(']')[0]
                if property_part.startswith(('Cell_', 'Point_')):
                    return True

        # Check if layer has scalar data (might be from VTP)
        if hasattr(layer, 'data') and len(layer.data) == 3:
            vertices, faces, values = layer.data
            # If it has scalar data, it might be from VTP
            if values is not None and len(values) > 0:
                return True

        return False

    def _on_layer_inserted(self, event):
        """Handle new layer insertion."""
        layer = event.value

        # Check if this is a Surface layer with data
        if isinstance(layer, Surface):
            # 1. Initialize VTP data (loads scalars, sets initial property)
            self._initialize_vtp_layer(layer)

            # 2. Apply lighting and AO only after VTP init is complete
            self._apply_automatic_lighting_ao(layer)

    def _on_active_layer_changed(self, event):
        """Update UI when the active layer changes."""
        layer = event.value
        if layer and isinstance(layer, Surface):
            # If layer is not initialized, do it now.
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

        # --- File Finding Logic ---

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

        # Priority 3: Search filesystem and match name, or use single-file heuristic as last resort
        if not vtp_path:
            search_dirs = {os.getcwd(), os.path.dirname(os.getcwd())} # Use set to avoid duplicates

            all_vtp_files = []
            for d in search_dirs:
                all_vtp_files.extend(glob.glob(os.path.join(d, "*.vtp")))

            unique_vtp_files = list(set(all_vtp_files))

            # Try to match layer name to a file in the list
            for f_path in unique_vtp_files:
                base_filename = os.path.splitext(os.path.basename(f_path))[0]
                if layer.name.startswith(base_filename):
                    vtp_path = f_path
                    break

            # If no match is found and there is only ONE vtp file, assume it's the one.
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

            # Get both point and cell data
            polydata = reader.GetOutput()
            point_data = polydata.GetPointData()
            cell_data = polydata.GetCellData()

            # Cache all scalar arrays in metadata
            scalar_data = {}
            scalar_names = []

            # Process point data
            for i in range(point_data.GetNumberOfArrays()):
                array = point_data.GetArray(i)
                name = point_data.GetArrayName(i)
                scalar_names.append(f"Point_{name}")
                scalar_data[f"Point_{name}"] = numpy_support.vtk_to_numpy(array)

            # Process cell data
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

            # Determine initial property to display
            initial_property = self._select_initial_scalar(scalar_names)

            if initial_property:
                # Apply the property and let auto-colormap handle the rest
                self._update_layer_data(layer, initial_property)

                layer.metadata['vtp_initialized'] = True

                # Update UI after successful initialization
                self._update_ui_from_layer(layer)
            else:
                self._extract_data_from_layer(layer)

        except Exception as e:
            print(f"Error loading VTP file: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to extracting data from existing layer
            self._extract_data_from_layer(layer)

    def _extract_data_from_layer(self, layer):
        """Extract data from existing layer if VTP file is not available."""
        # Check if layer already has scalar data
        if len(layer.data) == 3:
            vertices, faces, values = layer.data

            # Create a simple property name
            scalar_data = {'Current_Values': values}
            scalar_names = ['Current_Values']

            layer.metadata['vtp_scalar_data'] = scalar_data
            layer.metadata['vtp_scalar_names'] = scalar_names
            layer.metadata['vtp_initialized'] = True

            # Set initial property
            layer.metadata['active_property'] = 'Current_Values'

            # Update UI
            self._update_ui_from_layer(layer)

    def _create_user_friendly_names(self, scalar_names):
        """Create a clean list of property names, similar to the raw names in Paraview."""
        friendly_names = {}
        display_names = ["Solid Color"] # Add Solid Color option at the top

        # Original names map to themselves for simplicity
        for name in scalar_names:
            if name.startswith('Point_'):
                clean_name = name[6:]
            elif name.startswith('Cell_'):
                clean_name = name[5:]
            else:
                clean_name = name

            friendly_names[clean_name] = name
            display_names.append(clean_name)

        # Add a mapping for Solid Color to a placeholder
        friendly_names['Solid Color'] = 'solid_color'

        return friendly_names, display_names

    def _select_initial_scalar(self, scalar_names):
        """Select the best initial scalar to display."""
        # Priority order for different property types
        priority_arrays = [
            'gauss_curvature', 'mean_curvature', 'min_curvature', 'max_curvature',
            'shape_index_VV', 'curvedness_VV',
            'area',
            'orientation_class',
            'kappa_1', 'kappa_2'
        ]

        # Check for priority arrays (case insensitive)
        for priority in priority_arrays:
            for name in scalar_names:
                if priority.lower() in name.lower():
                    return name

        # Fallback to first available array
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

            # If not found, use the first available
            if current_friendly is None or current_friendly not in display_names:
                current_friendly = display_names[0]
                current_property = friendly_names[current_friendly]
                layer.metadata['active_property'] = current_property

            self.property_selector.value = current_friendly
            self.property_selector.enabled = True

        # Update colormap selector
        with self.colormap_selector.changed.blocked():
            self.colormap_selector.value = layer.colormap.name
            self.colormap_selector.enabled = True

        # Enable auto-apply
        self.auto_apply.enabled = True

        # Update statistics and preview
        self._update_statistics(layer)

        # Update contrast slider state
        self._update_contrast_slider_state(layer)


    
    def _on_ao_toggled(self, value):
        """Handle AO checkbox toggle — reapply current property with or without AO."""
        layer = self.viewer.layers.selection.active
        if not layer or not self._is_vtp_surface_layer(layer):
            for potential_layer in self.viewer.layers:
                if self._is_vtp_surface_layer(potential_layer):
                    layer = potential_layer
                    break
        if layer and self._is_vtp_surface_layer(layer):
            active = layer.metadata.get('active_property')
            if active and active != 'solid_color':
                self._update_layer_data(layer, active)

    def _on_property_changed(self, new_property: str):
        """Handle user selecting a new property from the dropdown."""
        # Try to find the active layer
        layer = self.viewer.layers.selection.active

        # If no active layer, try to find any VTP layer
        if not layer or not self._is_vtp_surface_layer(layer):
            for potential_layer in self.viewer.layers:
                if self._is_vtp_surface_layer(potential_layer):
                    layer = potential_layer
                    break

        if layer and self._is_vtp_surface_layer(layer):
            # Map the friendly name back to the original property name
            friendly_names = layer.metadata.get('friendly_names', {})
            original_property = friendly_names.get(new_property, new_property)

            self._update_layer_data(layer, original_property)
            self._update_ui_from_layer(layer)  # Refresh UI with new data

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
                # Re-assign data without scalar values
                layer.data = (vertices.copy(), faces.copy())
                if layer in self._lit_layers:
                    QTimer.singleShot(200, lambda l=layer: self._restore_lighting(l))
            layer.metadata['active_property'] = 'solid_color'
            layer.name = layer.name.split(' [')[0] # Reset name
            self._update_ui_from_layer(layer)
            return

        scalar_data = layer.metadata.get('vtp_scalar_data', {})
        new_values = scalar_data.get(scalar_array_name)

        if new_values is None:
            return

        # Get the current geometry, being robust to the layer's data structure
        if len(layer.data) == 3:
            vertices, faces, _ = layer.data
        else:
            vertices, faces = layer.data

        # Check if we need to convert cell data to vertex data
        n_vertices = len(vertices)
        n_values = len(new_values)

        # Check if this is vector data (3D vectors) or scalar data
        is_vector_data = len(new_values.shape) > 1 and new_values.shape[1] == 3

        if n_values != n_vertices:
            if is_vector_data:
                # Convert cell vector data to vertex vector data
                vertex_values = self._cell_to_vertex_interpolation_vector(faces, new_values, n_vertices)
            else:
                # Convert cell scalar data to vertex scalar data
                vertex_values = self._cell_to_vertex_interpolation(faces, new_values, n_vertices)
            new_values = vertex_values

        # If the values array is multi-dimensional, convert it to a 1D scalar
        # array for napari to use it for coloring by calculating the magnitude.
        if len(new_values.shape) > 1:
            new_values = np.linalg.norm(new_values, axis=1)

        # Apply ambient occlusion if available and enabled
        ao_factors = layer.metadata.get('ao_factors')
        if ao_factors is not None and self.ao_enabled.value:
            if len(new_values.shape) == 1 and len(ao_factors) == len(new_values):
                new_values = new_values * ao_factors

        # Re-assign the layer's data. Using .copy() for the geometry arrays
        # helps ensure that napari's change detection is triggered.
        layer.data = (vertices.copy(), faces.copy(), new_values)

        # Reassigning layer.data can rebuild the vispy visual, resetting
        # the shading filter. Defer lighting restoration for lit layers.
        if layer in self._lit_layers:
            QTimer.singleShot(200, lambda l=layer: self._restore_lighting(l))

        # Update contrast limits and metadata
        finite_values = new_values[np.isfinite(new_values)]
        if len(finite_values) > 0:
            layer.contrast_limits = (np.min(finite_values), np.max(finite_values))
        else:
            layer.contrast_limits = (0, 1)
        layer.metadata['active_property'] = scalar_array_name

        # Update layer name
        base_name = layer.name.split(' [')[0]
        layer.name = f'{base_name} [{scalar_array_name}]'

        # Safely ensure the layer remains selected after the update
        try:
            if layer not in self.viewer.layers.selection:
                self.viewer.layers.selection.add(layer)
        except Exception:
            pass

        # Automatically apply appropriate colormap
        if self.auto_apply.value:
            self._apply_auto_colormap(layer, scalar_array_name, new_values)

    def _cell_to_vertex_interpolation_vector(self, faces, cell_values, n_vertices):
        """Convert cell-based vector data to vertex-based vector data by averaging."""
        # Initialize vertex values array for 3D vectors
        vertex_values = np.zeros((n_vertices, 3))
        vertex_counts = np.zeros(n_vertices)

        # For each face, add its vector value to all its vertices
        for i, face in enumerate(faces):
            face_vector = cell_values[i]  # This is a 3D vector
            for vertex_idx in face:
                vertex_values[vertex_idx] += face_vector
                vertex_counts[vertex_idx] += 1

        # Average the vectors for each vertex
        # Avoid division by zero
        vertex_counts[vertex_counts == 0] = 1
        vertex_values = vertex_values / vertex_counts[:, np.newaxis]

        return vertex_values

    def _cell_to_vertex_interpolation(self, faces, cell_values, n_vertices):
        """Convert cell-based scalar data to vertex-based data by averaging."""
        # Initialize vertex values array
        vertex_values = np.zeros(n_vertices)
        vertex_counts = np.zeros(n_vertices)

        # For each face, add its value to all its vertices
        for i, face in enumerate(faces):
            face_value = cell_values[i]
            for vertex_idx in face:
                vertex_values[vertex_idx] += face_value
                vertex_counts[vertex_idx] += 1

        # Average the values for each vertex
        # Avoid division by zero
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

    def _hide_parent_ui_elements(self):
        """Hide all UI elements from parent VedoCutter class that we don't want to show."""
        # Hide the VTK widget (3D viewer)
        if hasattr(self, 'vtkWidget'):
            self.vtkWidget.hide()

        # Hide all buttons except load mesh
        for btn_name in [
            "pushButton_box_cutter",
            "pushButton_sphere_cutter",
            "pushButton_plane_cutter",
            "pushButton_send_back",
            "pushButton_get_from_napari"
        ]:
            btn = getattr(self, btn_name, None)
            if btn is not None:
                btn.hide()

        # Hide all labels, containers, frames and boxes
        for widget_name in [
            "label",
            "label_cutting_tools",
            "cutting_tools_container",
            "cutting_tools_label",
            "frame",
            "groupBox"
        ]:
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.hide()

    def send_to_napari(self):
        """Override the default send_to_napari to embed metadata."""
        if self.mesh is None:
            print("ERROR: No vedo mesh to send to napari.")
            return

        points = self.mesh.vertices
        faces = np.asarray(self.mesh.cells)
        # Include default values so AO can attenuate them
        values = np.ones(len(points))
        mesh_tuple = (points, faces, values)

        filepath = self.mesh.filename
        if filepath:
            name = os.path.splitext(os.path.basename(filepath))[0]
        else:
            name = "vedo_mesh"

        # --- CRITICAL: Embed the source path in the metadata ---
        metadata = {'source_vtp_path': filepath}

        # Add surface with metadata
        surface_layer = self.viewer.add_surface(mesh_tuple, name=name, metadata=metadata)

    def _apply_auto_colormap(self, layer, property_name, data):
        """Automatically apply appropriate colormap based on property type ."""
        property_lower = property_name.lower()

        # Check if data is diverging (crosses zero)
        is_diverging = np.nanmin(data) < 0 and np.nanmax(data) > 0


        if 'orientation' in property_lower:
            layer.colormap = 'hsv'  # Circular colormap for orientation
        elif 'shape_index' in property_lower:
            layer.colormap = 'Spectral' # Standard for shape index
        elif is_diverging:
            # Use coolwarm for any diverging data (e.g., curvature)
            layer.colormap = 'coolwarm'
        else:
            # Use viridis for sequential data (e.g., area, magnitude)
            layer.colormap = 'viridis'

        # Update colormap selector to reflect the change
        with self.colormap_selector.changed.blocked():
            self.colormap_selector.value = layer.colormap.name

    def _update_contrast_slider_state(self, layer):
        active_property = layer.metadata.get('active_property')
        if active_property == 'solid_color' or len(layer.data) != 3:
            self.contrast_container.visible = False
            return

        all_values = layer.metadata['vtp_scalar_data'][active_property]
        # Skip vector/multi-dimensional properties (e.g. normals with shape (N, 3))
        if hasattr(all_values, 'ndim') and all_values.ndim > 1:
            self.contrast_container.visible = False
            return
        finite_values = all_values[np.isfinite(all_values)] if hasattr(all_values, 'ravel') else all_values[np.isfinite(all_values)]
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

        # Update all widgets with new bounds and values
        with self.contrast_slider.changed.blocked(), self.contrast_min.changed.blocked(), self.contrast_max.changed.blocked():
            # Set bounds for all widgets
            self.contrast_slider.min = data_min
            self.contrast_slider.max = data_max
            self.contrast_min.min = data_min
            self.contrast_min.max = data_max
            self.contrast_max.min = data_min
            self.contrast_max.max = data_max

            # Clamp current values to data range
            clamped_min = max(min(current_min, data_max), data_min)
            clamped_max = max(min(current_max, data_max), data_min)

            # Get actual widget bounds
            actual_min = self.contrast_min.min
            actual_max = self.contrast_max.max

            # Clamp to actual widget bounds
            final_min = max(min(clamped_min, actual_max), actual_min)
            final_max = max(min(clamped_max, actual_max), actual_min)

            # Set values
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
            # Sync slider with bounds checking
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
            # Sync slider with bounds checking
            with self.contrast_slider.changed.blocked():
                clamped_min = max(min(min_val, self.contrast_slider.max), self.contrast_slider.min)
                clamped_max = max(min(max_val, self.contrast_slider.max), self.contrast_slider.min)
                self.contrast_slider.value = (clamped_min, clamped_max)

    def _initialize_automatic_lighting_ao(self):
        """Initialize camera-following lighting and ambient occlusion."""
        # Layers with smooth shading that need light direction updates
        self._lit_layers = []
        self._camera_connected = False

        # Track layers that have been processed
        self.processed_layers = set()

    def _get_vispy_visual(self, layer):
        """Get the vispy visual for a napari layer."""
        try:
            return self.viewer.window._qt_window._qt_viewer.layer_to_visual[layer]
        except Exception:
            return None

    def _compute_ao_factors(self, vertices, faces):
        """Compute per-vertex ambient occlusion using normal divergence.

        Measures how much neighboring vertex normals diverge from the vertex
        normal.  In concave regions (crevices/valleys), neighbor normals point
        away from each other → lower average dot product → more occlusion.
        On convex ridges, normals align → less occlusion.
        """
        normals = igl.per_vertex_normals(vertices, faces)
        adj = igl.adjacency_list(faces)
        n_verts = len(vertices)
        raw_ao = np.zeros(n_verts)

        for i in range(n_verts):
            neighbors = adj[i]
            if len(neighbors) < 2:
                raw_ao[i] = 1.0
                continue
            # Average dot product between this vertex's normal and neighbors'
            neighbor_normals = normals[neighbors]
            dots = neighbor_normals @ normals[i]
            raw_ao[i] = np.mean(dots)

        # raw_ao ranges roughly from -1 (deep crevice) to 1 (exposed peak)
        # Map to [0, 1] range: -1 → heavily occluded, 1 → no occlusion
        # Then remap to a useful visual range [ao_min, 1.0]
        ao_min = 0.25  # darkest occlusion factor
        ao_normalized = np.clip((raw_ao + 1.0) / 2.0, 0, 1)  # map [-1,1] to [0,1]
        ao_factors = ao_min + (1.0 - ao_min) * ao_normalized
        return ao_factors

    def _apply_automatic_lighting_ao(self, layer):
        """Apply ambient occlusion and camera-following lighting to a surface layer."""
        if not isinstance(layer, Surface):
            return

        # Skip if already processed
        if layer in self.processed_layers:
            return
        self.processed_layers.add(layer)

        # Compute and store AO factors synchronously (geometry-only, no vispy needed)
        if IGL_AVAILABLE:
            try:
                if len(layer.data) >= 2:
                    vertices, faces = layer.data[0], layer.data[1]
                    ao_factors = self._compute_ao_factors(
                        vertices, faces.astype(int)
                    )
                    layer.metadata['ao_factors'] = ao_factors
                    # Reapply current property with AO
                    active = layer.metadata.get('active_property')
                    if active and active != 'solid_color':
                        self._update_layer_data(layer, active)
            except Exception as e:
                print(f"Warning: AO computation failed for {layer.name}: {e}")

        # Defer lighting setup until the vispy visual node is fully created
        QTimer.singleShot(200, lambda l=layer: self._deferred_lighting_setup(l))

    def _deferred_lighting_setup(self, layer):
        """Set up smooth shading with camera-following light after vispy is ready."""
        try:
            if layer not in self.viewer.layers:
                return

            layer.shading = 'smooth'

            visual = self._get_vispy_visual(layer)
            if visual is None or visual.node.shading_filter is None:
                layer.shading = 'none'
                return

            self._lit_layers.append(layer)

            # Connect camera angle changes once
            if not self._camera_connected:
                self.viewer.camera.events.angles.connect(self._on_camera_angles_changed)
                self._camera_connected = True

            # Set initial light direction
            self._on_camera_angles_changed()
        except Exception as e:
            try:
                layer.shading = 'none'
            except Exception:
                pass
            print(f"Warning: Could not set up lighting for {layer.name}: {e}")

    def _restore_lighting(self, layer):
        """Restore smooth shading after vispy visual rebuild.

        Phase 1: set shading to 'smooth', then schedule phase 2 to
        configure the light direction once vispy has created the filter.
        """
        try:
            if layer not in self.viewer.layers:
                return
            layer.shading = 'smooth'
            # Give vispy time to create the shading_filter after the
            # shading property change, then configure light direction.
            QTimer.singleShot(100, lambda l=layer: self._apply_light_dir(l, retries=5))
        except Exception:
            pass

    def _apply_light_dir(self, layer, retries=5):
        """Phase 2: set light_dir on the shading filter once it exists."""
        try:
            if layer not in self.viewer.layers:
                return
            visual = self._get_vispy_visual(layer)
            if visual is None or visual.node.shading_filter is None:
                if retries > 0:
                    QTimer.singleShot(100, lambda l=layer, r=retries-1: self._apply_light_dir(l, r))
                return
            view_direction = np.asarray(self.viewer.camera.view_direction)
            layer_view_dir = np.asarray(layer._world_to_data_ray(view_direction))
            if hasattr(layer, '_slice_input'):
                dims = layer._slice_input.displayed
            elif hasattr(layer, '_dims_displayed'):
                dims = layer._dims_displayed
            else:
                dims = list(range(layer.ndim))
            layer_view_dir = layer_view_dir[dims]
            visual.node.shading_filter.light_dir = layer_view_dir[::-1]
        except Exception:
            pass

    def _on_camera_angles_changed(self, event=None):
        """Update light direction on all lit layers to follow the camera."""
        try:
            view_direction = np.asarray(self.viewer.camera.view_direction)
        except Exception:
            return

        for layer in list(self._lit_layers):
            try:
                if layer not in self.viewer.layers:
                    self._lit_layers.remove(layer)
                    continue
                visual = self._get_vispy_visual(layer)
                if visual is None:
                    continue
                if visual.node.shading_filter is None:
                    # Filter destroyed by visual rebuild; trigger restoration
                    QTimer.singleShot(200, lambda l=layer: self._restore_lighting(l))
                    continue
                # Transform view direction to layer data coordinates
                layer_view_dir = np.asarray(
                    layer._world_to_data_ray(view_direction)
                )
                # napari uses dims_displayed to pick the right 3 axes
                if hasattr(layer, '_slice_input'):
                    dims = layer._slice_input.displayed
                elif hasattr(layer, '_dims_displayed'):
                    dims = layer._dims_displayed
                else:
                    dims = list(range(layer.ndim))
                layer_view_dir = layer_view_dir[dims]
                visual.node.shading_filter.light_dir = layer_view_dir[::-1]
            except Exception:
                pass


