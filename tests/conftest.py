import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication for Qt tests."""
    from qtpy.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def tmp_yaml(tmp_path):
    """Create a temporary YAML config file with realistic content."""
    content = """data_dir: /tmp/data
work_dir: /tmp/work
segmentation_values:
  ER: 1
  PM: 2
surface_generation:
  angstroms: false
  ultrafine: true
  target_area: 1.0
  simplify: false
  max_triangles: 300000
  extrapolation_distance: 1.5
  octree_depth: 7
  point_weight: 0.7
  neighbor_count: 400
  smoothing_iterations: 1
curvature_measurements:
  radius_hit: 9
  min_component: 30
  exclude_borders: 1.0
distance_and_orientation_measurements:
  mindist: 3.0
  maxdist: 400.0
  tolerance: 0.1
  verticality: true
  relative_orientation: true
  intra:
    - ER
  inter:
    PM:
      - ER
cores: 4
script_location: /tmp/scripts
"""
    yaml_path = tmp_path / "test_config.yml"
    yaml_path.write_text(content)
    return yaml_path


@pytest.fixture
def mock_viewer():
    """MagicMock napari viewer."""
    viewer = MagicMock()
    viewer.layers = MagicMock()
    viewer.layers.selection = MagicMock()
    viewer.layers.selection.active = None
    return viewer


@pytest.fixture
def mock_experiment_manager(tmp_path):
    """MagicMock experiment manager with required attributes."""
    em = MagicMock()
    em.work_dir = MagicMock()
    em.work_dir.value = str(tmp_path)
    em.experiment_name = MagicMock()
    em.experiment_name.currentText.return_value = "test_experiment"
    em.current_config = {
        "data_dir": str(tmp_path / "data"),
        "work_dir": str(tmp_path),
        "segmentation_values": {"ER": 1, "PM": 2},
        "surface_generation": {
            "angstroms": False,
            "ultrafine": True,
            "target_area": 1.0,
            "simplify": False,
            "max_triangles": 300000,
            "extrapolation_distance": 1.5,
            "octree_depth": 7,
            "point_weight": 0.7,
            "neighbor_count": 400,
            "smoothing_iterations": 1,
        },
        "curvature_measurements": {
            "radius_hit": 9,
            "min_component": 30,
            "exclude_borders": 1.0,
        },
        "cores": 4,
        "script_location": "/tmp/scripts",
    }
    em.config_loaded = MagicMock()
    em.viewer = MagicMock()
    return em
