import napari
from pathlib import Path
import mrcfile
import numpy as np
from magicgui import widgets
from qtpy.QtWidgets import QFileDialog
import logging
import starfile
import pandas as pd
import difflib
from skimage.measure import marching_cubes


logging.basicConfig(level=logging.WARNING)


class ProteinLoaderPlugin:
    def __init__(self, viewer: napari.Viewer):
        self.viewer = viewer
        self.structure_layer = None
        self.star_data = None
        self.protein_locations = None
        self.protein_orientations = None
        self.protein_origins = None
        self.coord_columns = None
        self.tomo_column = None
        self.orientation_columns = None
        self.origin_columns = None
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
        # Add coordinate extraction button
        self.extract_coords_btn = widgets.PushButton(text='Extract Coordinates')
        self.extract_coords_btn.clicked.connect(self._extract_coordinates)
        self.extract_coords_btn.enabled = False  # Disabled until STAR file is loaded
        self.status_label = widgets.Label(value='Status: Ready')
        # Add button to visualize structure copies at coordinates
        self.visualize_copies_btn = widgets.PushButton(text='Show Structure at Coordinates')
        self.visualize_copies_btn.clicked.connect(lambda: self._show_structure_at_coordinates(self.protein_locations))

        self.container.extend([
            header,
            self.load_mrc_btn,
            self.load_star_btn,
            self.extract_coords_btn,
            self.visualize_copies_btn,
            self.status_label
        ])

        # Automatically extract coordinates on layer selection
        self.viewer.layers.selection.events.active.connect(self._on_layer_selected)

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
        """Basic STAR file loading and parsing with column detection."""
        try:
            # Read the STAR file
            star_data = starfile.read(file_path)
            self.logger.info(f"Loaded STAR file: {file_path}")
            self.logger.info(f"Type of star_data: {type(star_data)}")
            # If dict, prefer a block with particle data
            if isinstance(star_data, dict):
                self.logger.info(f"Multi-block STAR file with keys: {list(star_data.keys())}")
                # Try to find a block with all coordinate columns
                coord_block = None
                for key, df in star_data.items():
                    if isinstance(df, pd.DataFrame):
                        cols = [col.strip() for col in df.columns]
                        if any(x in cols for x in ['_rlnCoordinateX', 'rlnCoordinateX', 'x', 'X']) and \
                           any(y in cols for y in ['_rlnCoordinateY', 'rlnCoordinateY', 'y', 'Y']) and \
                           any(z in cols for z in ['_rlnCoordinateZ', 'rlnCoordinateZ', 'z', 'Z']):
                            coord_block = key
                            break
                if coord_block:
                    self.star_data = star_data[coord_block]
                    self.logger.info(f"Using block with coordinates: {coord_block}")
                else:
                    first_key = list(star_data.keys())[0]
                    self.star_data = star_data[first_key]
                    self.logger.warning(f"No block with all coordinate columns found, using first block: {first_key}")
            else:
                self.star_data = star_data

            # Log DataFrame columns and shape
            if isinstance(self.star_data, pd.DataFrame):
                self.logger.info(f"STAR data shape: {self.star_data.shape}")
                self.logger.info(f"STAR data columns: {[repr(col) for col in self.star_data.columns]}")
                self.status_label.value = f'Status: STAR file loaded - {self.star_data.shape[0]} rows, {self.star_data.shape[1]} columns'

                # Column detection
                self.coord_columns = self._detect_coordinate_columns(self.star_data)
                self.tomo_column = self._detect_tomogram_column(self.star_data)
                self.orientation_columns = self._detect_orientation_columns(self.star_data)
                self.origin_columns = self._detect_origin_columns(self.star_data)

                # Log detected columns
                self.logger.info(f"Detected coordinate columns: {self.coord_columns}")
                self.logger.info(f"Detected tomogram column: {self.tomo_column}")
                self.logger.info(f"Detected orientation columns: {self.orientation_columns}")
                self.logger.info(f"Detected origin columns: {self.origin_columns}")

                if not self.coord_columns or not self.tomo_column:
                    self.logger.info(f"First 5 rows:\n{self.star_data.head()}\n")
            else:
                self.logger.warning(f"Unexpected STAR data type: {type(self.star_data)}")
                self.status_label.value = 'Status: Error - unexpected STAR file format'

            self.extract_coords_btn.enabled = True

        except Exception as e:
            self.logger.error(f"Error loading STAR file {file_path}: {str(e)}")
            self.status_label.value = f'Status: Error loading STAR file - {str(e)}'

    def _detect_coordinate_columns(self, df):
        """Detect X, Y, Z coordinate columns from a DataFrame."""
        possible_x = ['_rlnCoordinateX', 'rlnCoordinateX', 'x', 'X']
        possible_y = ['_rlnCoordinateY', 'rlnCoordinateY', 'y', 'Y']
        possible_z = ['_rlnCoordinateZ', 'rlnCoordinateZ', 'z', 'Z']
        x_col = next((col for col in possible_x if col in df.columns), None)
        y_col = next((col for col in possible_y if col in df.columns), None)
        z_col = next((col for col in possible_z if col in df.columns), None)
        if x_col and y_col and z_col:
            return [x_col, y_col, z_col]
        self.logger.warning(f"Could not detect all coordinate columns. Found: X={x_col}, Y={y_col}, Z={z_col}")
        return None

    def _detect_tomogram_column(self, df):
        """Detect tomogram/micrograph column from a DataFrame."""
        possible_tomo = ['_rlnMicrographName', 'rlnMicrographName', '_rlnImageName', 'rlnImageName', '_rlnTomoName', 'rlnTomoName', 'tomo', 'Tomo', 'TOMO']
        for col in possible_tomo:
            if col in df.columns:
                return col
        self.logger.warning("Could not detect tomogram/micrograph column.")
        return None

    def _detect_orientation_columns(self, df):
        """Detect rotation angle columns from a DataFrame."""
        possible_rot = ['_rlnAngleRot', 'rlnAngleRot', 'rot', 'Rot', 'ROT']
        possible_tilt = ['_rlnAngleTilt', 'rlnAngleTilt', 'tilt', 'Tilt', 'TILT']
        possible_psi = ['_rlnAnglePsi', 'rlnAnglePsi', 'psi', 'Psi', 'PSI']

        rot_col = next((col for col in possible_rot if col in df.columns), None)
        tilt_col = next((col for col in possible_tilt if col in df.columns), None)
        psi_col = next((col for col in possible_psi if col in df.columns), None)

        if rot_col and tilt_col and psi_col:
            return [rot_col, tilt_col, psi_col]
        self.logger.warning(f"Could not detect all orientation columns. Found: Rot={rot_col}, Tilt={tilt_col}, Psi={psi_col}")
        return None

    def _detect_origin_columns(self, df):
        """Detect origin shift columns from a DataFrame."""
        possible_origin_x = ['_rlnOriginX', 'rlnOriginX', 'originX', 'OriginX']
        possible_origin_y = ['_rlnOriginY', 'rlnOriginY', 'originY', 'OriginY']
        possible_origin_z = ['_rlnOriginZ', 'rlnOriginZ', 'originZ', 'OriginZ']

        origin_x_col = next((col for col in possible_origin_x if col in df.columns), None)
        origin_y_col = next((col for col in possible_origin_y if col in df.columns), None)
        origin_z_col = next((col for col in possible_origin_z if col in df.columns), None)

        if origin_x_col and origin_y_col and origin_z_col:
            return [origin_x_col, origin_y_col, origin_z_col]
        self.logger.warning(f"Could not detect all origin columns. Found: OriginX={origin_x_col}, OriginY={origin_y_col}, OriginZ={origin_z_col}")
        return None

    def _euler_to_rotation_matrix(self, rot_deg, tilt_deg, psi_deg):
        """Convert Euler angles (in degrees) to 3x3 rotation matrix."""
        # Convert to radians
        rot_rad = np.radians(rot_deg)
        tilt_rad = np.radians(tilt_deg)
        psi_rad = np.radians(psi_deg)

        # Rotation matrices for each axis
        cos_rot, sin_rot = np.cos(rot_rad), np.sin(rot_rad)
        cos_tilt, sin_tilt = np.cos(tilt_rad), np.sin(tilt_rad)
        cos_psi, sin_psi = np.cos(psi_rad), np.sin(psi_rad)

        # ZYZ rotation matrix
        R = np.array([
            [cos_rot*cos_tilt*cos_psi - sin_rot*sin_psi, -cos_rot*cos_tilt*sin_psi - sin_rot*cos_psi, cos_rot*sin_tilt],
            [sin_rot*cos_tilt*cos_psi + cos_rot*sin_psi, -sin_rot*cos_tilt*sin_psi + cos_rot*cos_psi, sin_rot*sin_tilt],
            [-sin_tilt*cos_psi, sin_tilt*sin_psi, cos_tilt]
        ])

        # Invert the rotation matrix since STAR angles rotate particle to reference,
        # but we want to rotate reference to match particle orientation
        R_inv = R.T  # For rotation matrices, transpose = inverse

        return R_inv

    def _apply_rotation_to_vertices(self, vertices, rotation_matrix):
        """Apply rotation matrix to vertices."""
        return vertices @ rotation_matrix.T

    # Method handles the logic of loading the data from a file path and adding it to napari
    def _load_structure(self, file_path: Path):
        """
        Load the structure MRC file and store its file path in the layer metadata for later pixel size reading.
        """
        with mrcfile.open(file_path, permissive=True) as mrc:
            data = mrc.data.copy()
        # Add the structure as an image layer and store the file path in metadata
        self.structure_layer = self.viewer.add_image(data, name='structure', colormap='gray', opacity=0.5)
        self.structure_layer.metadata['source_path'] = str(file_path)
        self.status_label.value = f'Status: Structure loaded from {file_path.name}'

    def _get_selected_tomogram_name(self):
        """
        Get the base name of the currently selected tomogram/segmentation/mesh layer for matching with STAR data.
        Strips common suffixes, extensions, and property names.
        """
        selected_layer = self.viewer.layers.selection.active
        if selected_layer is not None:
            name = selected_layer.name
            # Remove property name in brackets
            if '[' in name:
                name = name.split('[')[0].strip()
            # Remove file extension
            for ext in ['.mrc', '.map', '.nii', '.nii.gz', '.tomostar']:
                if name.endswith(ext):
                    name = name[: -len(ext)]
            # Remove common suffixes
            for suffix in ['_labels', '_segmentation', '_mask', '_label', '_seg']:
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
            # Remove trailing underscores or dots
            name = name.rstrip('_. ')
            # Lowercase for case-insensitive matching
            name = name.lower()
            return name
        return None

    def _filter_star_by_tomogram(self):
        if self.star_data is None or self.tomo_column is None:
            print("No STAR data or tomogram column detected.")
            return None
        def process_name(name):
            # Remove property name in brackets
            if '[' in name:
                name = name.split('[')[0].strip()
            # Remove file extension
            for ext in ['.mrc', '.map', '.nii', '.nii.gz', '.tomostar']:
                if name.endswith(ext):
                    name = name[: -len(ext)]
            name = name.rstrip('_. ')
            name = name.lower()
            return name
        selected_name = process_name(self._get_selected_tomogram_name() or "")
        if not selected_name:
            print("No selected tomogram name.")
            return None
        star_names_raw = self.star_data[self.tomo_column].astype(str)
        star_names_processed = star_names_raw.apply(process_name)
        # Fuzzy matching using difflib
        best_match = None
        best_score = 0.0
        for star_name in star_names_processed.unique():
            score = difflib.SequenceMatcher(None, selected_name, star_name).ratio()
            if score > best_score:
                best_score = score
                best_match = star_name
        print(f"[DEBUG] Best fuzzy match: '{best_match}' (similarity: {best_score:.2f}) vs selected: '{selected_name}'")
        threshold = 0.6
        if best_match and best_score > threshold:
            mask = star_names_processed == best_match
            filtered = self.star_data[mask]
            print(f"[INFO] Fuzzy matched tomogram: '{best_match}' (similarity: {best_score:.2f})")
            return filtered
        print(f"[WARNING] No sufficiently similar tomogram match found for '{selected_name}'. No coordinates will be extracted.")
        return None

    def _extract_coordinates(self):
        """Extract X, Y, Z coordinates from the STAR data for the selected tomogram."""
        if self.star_data is None:
            self.logger.warning("No STAR data loaded")
            self.status_label.value = 'Status: No STAR data to extract coordinates from'
            return

        if not self.coord_columns:
            self.logger.warning("Coordinate columns not detected")
            self.status_label.value = 'Status: Error - coordinate columns not detected'
            return

        try:
            filtered_df = self._filter_star_by_tomogram()
            if filtered_df is None or len(filtered_df) == 0:
                self.logger.warning("No coordinates found for selected tomogram.")
                self.status_label.value = 'Status: No coordinates found for selected tomogram'
                self.protein_locations = None
                return

            self.protein_locations = filtered_df[self.coord_columns].values
            self.logger.info(f"Extracted {len(self.protein_locations)} protein locations for selected tomogram")
            self.logger.info(f"Coordinate columns used: {self.coord_columns}")
            self.logger.info(f"Coordinate range: X[{np.min(self.protein_locations[:, 0]):.1f}, {np.max(self.protein_locations[:, 0]):.1f}], "
                             f"Y[{np.min(self.protein_locations[:, 1]):.1f}, {np.max(self.protein_locations[:, 1]):.1f}], "
                             f"Z[{np.min(self.protein_locations[:, 2]):.1f}, {np.max(self.protein_locations[:, 2]):.1f}]")

            # Extract orientation data if available
            if self.orientation_columns:
                self.protein_orientations = filtered_df[self.orientation_columns].values
                self.logger.info(f"Extracted orientation data using columns: {self.orientation_columns}")
                self.logger.info(f"Orientation range: Rot[{np.min(self.protein_orientations[:, 0]):.1f}, {np.max(self.protein_orientations[:, 0]):.1f}], "
                                 f"Tilt[{np.min(self.protein_orientations[:, 1]):.1f}, {np.max(self.protein_orientations[:, 1]):.1f}], "
                                 f"Psi[{np.min(self.protein_orientations[:, 2]):.1f}, {np.max(self.protein_orientations[:, 2]):.1f}]")
            else:
                self.protein_orientations = None
                self.logger.info("No orientation data found in STAR file")

            # Extract origin data if available
            if self.origin_columns:
                self.protein_origins = filtered_df[self.origin_columns].values
                self.logger.info(f"Extracted origin data using columns: {self.origin_columns}")
            else:
                self.protein_origins = None
                self.logger.info("No origin data found in STAR file")

            self.status_label.value = f'Status: Extracted {len(self.protein_locations)} coordinates for selected tomogram'
        except Exception as e:
            self.logger.error(f"Error extracting coordinates: {str(e)}")
            self.status_label.value = f'Status: Error extracting coordinates - {str(e)}'

    def _on_layer_selected(self, event=None):
        """Automatically extract coordinates when a new layer is selected."""
        if self.star_data is not None and self.coord_columns and self.tomo_column:
            self._extract_coordinates()

    def _find_mesh_layer(self):
        """Find the first mesh layer in the viewer."""
        for layer in self.viewer.layers:
            if hasattr(layer, 'data') and len(layer.data) >= 2:
                # Check if it's a surface layer
                if isinstance(layer.data[0], np.ndarray) and isinstance(layer.data[1], np.ndarray):
                    return layer
        return None
        
    def _show_structure_at_coordinates(self, coords=None):
        if coords is None or isinstance(coords, bool):
            coords = self.protein_locations
        if coords is None or len(coords) == 0:
            self.logger.warning("No coordinates available for structure placement.")
            self.status_label.value = "Status: No coordinates available for structure placement."
            return
            
        # --- STAR coordinates conversion: pixels to nm using optics group pixel size ---
        pixel_size_nm = None
        if hasattr(self, 'star_data') and self.star_data is not None:
            if hasattr(self, 'starfile') and hasattr(self.starfile, 'optics'):
                optics = getattr(self.starfile, 'optics', None)
                if optics is not None and '_rlnImagePixelSize' in optics.columns:
                    pixel_size_nm = float(optics['_rlnImagePixelSize'].iloc[0]) * 0.1
            elif isinstance(self.star_data, dict) and 'optics' in self.star_data:
                optics = self.star_data['optics']
                if '_rlnImagePixelSize' in optics.columns:
                    pixel_size_nm = float(optics['_rlnImagePixelSize'].iloc[0]) * 0.1
            elif isinstance(self.star_data, dict) and 'particles' in self.star_data:
                particles = self.star_data['particles']
                if 'rlnPixelSize' in particles.columns:
                    pixel_size_nm = float(particles['rlnPixelSize'].iloc[0]) * 0.1

        if pixel_size_nm is None:
            pixel_size_nm = 3.33 * 0.1
            self.logger.warning("Could not find pixel size in STAR file. Using default 0.333 nm/pixel.")

        coords_nm = coords * pixel_size_nm
        all_vertices = []
        all_faces = []
        n_structures = len(coords_nm)
        
        structure_pixel_size = None
        mrc_path = self.structure_layer.metadata.get('source_path', None) if hasattr(self.structure_layer, 'metadata') else None
        
        if mrc_path is not None:
            try:
                with mrcfile.open(mrc_path, permissive=True) as mrc:
                    if hasattr(mrc.header, 'cella') and hasattr(mrc.header, 'nx'):
                        px_size_x = mrc.header.cella.x / mrc.header.nx
                        px_size_y = mrc.header.cella.y / mrc.header.ny
                        px_size_z = mrc.header.cella.z / mrc.header.nz
                        structure_pixel_size = (px_size_x + px_size_y + px_size_z) / 3.0
            except Exception as e:
                error_msg = f"Could not read pixel size from MRC header: {e}"
                self.logger.error(f"[ERROR] {error_msg}")
                self.status_label.value = f"Status: Error - {error_msg}"
                return
                
        if structure_pixel_size is None:
            error_msg = "Structure pixel size not found in MRC header. Please ensure it has correct header info."
            self.logger.error(f"[ERROR] {error_msg}")
            self.status_label.value = f"Status: Error - {error_msg}"
            return

        structure_pixel_size_nm = structure_pixel_size / 10.0
        structure_data = self.structure_layer.data
        verts, faces, _, _ = marching_cubes(structure_data, level=0.5)
        centroid = verts.mean(axis=0)
        verts_centered = verts - centroid
        verts_centered_nm = verts_centered * structure_pixel_size_nm
        
        for i, center in enumerate(coords_nm):
            verts_transformed = verts_centered_nm.copy()

            # Apply rotation if orientation data is available
            if hasattr(self, 'protein_orientations') and self.protein_orientations is not None:
                rot, tilt, psi = self.protein_orientations[i]
                rotation_matrix = self._euler_to_rotation_matrix(rot, tilt, psi)
                verts_transformed = self._apply_rotation_to_vertices(verts_transformed, rotation_matrix)

            # Apply origin shift if available
            if hasattr(self, 'protein_origins') and self.protein_origins is not None:
                origin_shift = self.protein_origins[i] * pixel_size_nm
                verts_transformed += origin_shift

            # Translate to final position
            verts_trans = verts_transformed + center
            
            all_vertices.append(verts_trans)
            all_faces.append(faces + i * verts.shape[0])
            
        if all_vertices:
            all_vertices = np.vstack(all_vertices)
            all_faces = np.vstack(all_faces)
            mesh_layer = self._find_mesh_layer()
            layer_name = f"structure_at_{mesh_layer.name if mesh_layer is not None else 'mesh'}"
            self.viewer.add_surface((all_vertices, all_faces), name=layer_name, opacity=0.8)

        orientation_info = ""
        if hasattr(self, 'protein_orientations') and self.protein_orientations is not None:
            orientation_info = " with orientations"
        origin_info = ""
        if hasattr(self, 'protein_origins') and self.protein_origins is not None:
            origin_info = " and origin shifts"
        
        self.status_label.value = f"Status: Placed {n_structures} structures{orientation_info}{origin_info}."
