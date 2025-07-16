from napari_vedo_bridge._cutter_widget import VedoCutter
from napari_vedo_bridge._cutter_widget import is_ragged
import threading
import vtk
from vtk.util import numpy_support
import numpy as np
from napari.layers import Surface
import os
import glob
from magicgui import widgets
from qtpy.QtCore import QTimer
from magicgui.widgets import FloatRangeSlider, FloatSpinBox


class CustomVedoCutter(VedoCutter):
    def __init__(self, *args, **kwargs):
        self.viewer = args[0]
        super().__init__(*args, **kwargs)

        # Configure better lighting for more even illumination
        self._configure_lighting()

        # Configure lighting for all existing surface layers
        self._configure_all_surface_lighting()

        # Hide all UI elements from parent class
        self._hide_parent_ui_elements()

        # Extract the load mesh button from parent class
        self.load_mesh_button = None
        if hasattr(self, 'pushButton_load_mesh'):
            self.load_mesh_button = self.pushButton_load_mesh

        # Create a completely new layout with just the essential controls
        self.controls_container = widgets.Container(layout='vertical', labels=True)

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

        # Container for slider and spinboxes
        self.contrast_container = widgets.Container(layout='horizontal', labels=False)

        # Set minimum widths for the spinboxes to make them smaller
        self.contrast_min.min_width = 80
        self.contrast_max.min_width = 80

        # Set the slider to take up more space
        self.contrast_slider.min_width = 200

        self.contrast_container.append(self.contrast_min)
        self.contrast_container.append(self.contrast_slider)
        self.contrast_container.append(self.contrast_max)
        self.contrast_container.visible = False

        self.stats_label = widgets.Label(value="No data loaded")

        # Create a clean container for the load mesh button with a Mesh Display label beside it
        if self.load_mesh_button:

            mesh_row_container = widgets.Container(layout='horizontal')

            mesh_display_label = widgets.Label(value="Mesh Display")

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
                self.stats_label,
                self.contrast_container,  
            ])
        else:
            self.controls_container.extend([
                self.property_selector,
                self.colormap_selector,
                self.auto_apply,
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

        # Add our clean container
        layout.addWidget(self.controls_container.native)

        # --- Connect Signals ---
        self.viewer.layers.events.inserted.connect(self._on_layer_inserted)
        self.viewer.layers.selection.events.active.connect(self._on_active_layer_changed)
        self.property_selector.changed.connect(self._on_property_changed)
        self.colormap_selector.changed.connect(self._on_colormap_changed)
        self.auto_apply.changed.connect(self._on_auto_apply_changed)
        self.contrast_slider.changed.connect(self._on_contrast_slider_changed)
        self.contrast_min.changed.connect(self._on_contrast_min_changed)
        self.contrast_max.changed.connect(self._on_contrast_max_changed)

        # --- Auto-send to napari functionality ---
        self.last_mesh_filename = None
        self._start_auto_send_monitor()

    def _configure_lighting(self):
        
        # Change from "shiny" to "ambient" for more even lighting
        self.mesh_lighting = "ambient"
        
        # If mesh is already loaded, apply the new lighting
        if hasattr(self, 'mesh') and self.mesh is not None:
            self.mesh.lighting(self.mesh_lighting)

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
            # Try to initialize it as a VTP layer
            self._initialize_vtp_layer(layer)
            
            # Configure lighting for the new layer
            self._configure_napari_lighting(layer)

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
                
                # Configure better lighting
                self._configure_napari_lighting(layer)
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
            
            # Configure better lighting
            self._configure_napari_lighting(layer)

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

    def _configure_napari_lighting(self, layer):
        """Configure better lighting for napari surface layers."""
        if not isinstance(layer, Surface):
            return
            
        # Try to set shading to 'none' for most even appearance
        if hasattr(layer, 'shading'):
            try:
                layer.shading = 'none'
                return  # Success, no need to try other approaches
            except (AttributeError, ValueError) as e:
                # Only catch specific exceptions, not all exceptions
                pass
            
        # Fallback to flat shading if 'none' doesn't work
        if hasattr(layer, 'shading'):
            try:
                layer.shading = 'flat'
                return
            except (AttributeError, ValueError) as e:
                pass
                
        # Final fallback to smooth shading
        if hasattr(layer, 'shading'):
            try:
                layer.shading = 'smooth'
            except (AttributeError, ValueError) as e:
                pass

    def _configure_all_surface_lighting(self):
        """Configure lighting for all existing surface layers in the viewer."""
        for layer in self.viewer.layers:
            if isinstance(layer, Surface):
                self._configure_napari_lighting(layer)

    def fix_current_layer_lighting(self):
        """Manually fix lighting for the currently selected layer."""
        layer = self.viewer.layers.selection.active
        if layer and isinstance(layer, Surface):
            self._configure_napari_lighting(layer)
        else:
            print("No surface layer currently selected")

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

        # Re-assign the layer's data. Using .copy() for the geometry arrays
        # helps ensure that napari's change detection is triggered.
        layer.data = (vertices.copy(), faces.copy(), new_values)

        # Update contrast limits and metadata
        layer.contrast_limits = (np.min(new_values), np.max(new_values))
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
        mesh_tuple = (points, faces)

        filepath = self.mesh.filename
        if filepath:
            name = os.path.splitext(os.path.basename(filepath))[0]
        else:
            name = "vedo_mesh"

        # --- CRITICAL: Embed the source path in the metadata ---
        metadata = {'source_vtp_path': filepath}

        # Add surface with better lighting configuration
        surface_layer = self.viewer.add_surface(mesh_tuple, name=name, metadata=metadata)
        
        # Configure better lighting for napari surface using comprehensive approach
        self._configure_napari_lighting(surface_layer)

    def _apply_auto_colormap(self, layer, property_name, data):
        """Automatically apply appropriate colormap based on property type ."""
        property_lower = property_name.lower()

        # Check if data is diverging (crosses zero)
        is_diverging = np.min(data) < 0 and np.max(data) > 0


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
        data_min, data_max = float(np.min(all_values)), float(np.max(all_values))

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

    def get_from_napari(self):
        """Override to ensure proper lighting is applied when loading meshes."""
        # Call parent method first
        super().get_from_napari()
        
        # Apply our custom lighting
        if hasattr(self, 'mesh') and self.mesh is not None:
            self.mesh.lighting(self.mesh_lighting)

    def _load_mesh(self):
        """Override to ensure proper lighting is applied when loading meshes from files."""
        # Call parent method first
        super()._load_mesh()
        
        # Apply our custom lighting
        if hasattr(self, 'mesh') and self.mesh is not None:
            self.mesh.lighting(self.mesh_lighting)
