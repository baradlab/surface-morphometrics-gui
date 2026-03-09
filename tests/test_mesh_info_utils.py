"""Tests for get_mesh_info pure logic."""
import numpy as np
from unittest.mock import MagicMock
from plugins.mesh_info_utils import get_mesh_info


def _make_layer(vertices=None, metadata=None):
    layer = MagicMock()
    if vertices is not None:
        faces = np.array([[0, 1, 2]])
        layer.data = (vertices, faces)
    else:
        layer.data = ()
    layer.metadata = metadata or {}
    return layer


class TestGetMeshInfo:
    def test_basic_vertices(self):
        verts = np.array([[0, 0, 0], [10, 20, 30], [5, 5, 5]], dtype=float)
        layer = _make_layer(verts)
        info = get_mesh_info(layer)
        np.testing.assert_array_equal(info["min"], [0, 0, 0])
        np.testing.assert_array_equal(info["max"], [10, 20, 30])
        np.testing.assert_array_equal(info["spread"], [10, 20, 30])

    def test_metadata_pixel_size(self):
        verts = np.array([[0, 0, 0], [1, 1, 1]], dtype=float)
        layer = _make_layer(verts, metadata={"pixel_size": 0.5, "units": "nm"})
        info = get_mesh_info(layer)
        assert info["pixel_size"] == 0.5
        assert info["units"] == "nm"
        assert len(info["warnings"]) == 0

    def test_guessed_units_large_spread(self):
        verts = np.array([[0, 0, 0], [2000, 2000, 2000]], dtype=float)
        layer = _make_layer(verts)
        info = get_mesh_info(layer)
        assert "pixels" in info.get("guessed_units", "")

    def test_guessed_units_small_spread(self):
        verts = np.array([[0, 0, 0], [5, 5, 5]], dtype=float)
        layer = _make_layer(verts)
        info = get_mesh_info(layer)
        assert "nm" in info.get("guessed_units", "")

    def test_no_data_warnings(self):
        layer = MagicMock()
        layer.data = ()
        layer.metadata = {}
        info = get_mesh_info(layer)
        assert any("No vertices" in w for w in info["warnings"])
        assert any("No pixel size" in w for w in info["warnings"])
        assert any("No units" in w for w in info["warnings"])
