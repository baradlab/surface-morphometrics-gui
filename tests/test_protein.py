"""Tests for protein.py column detection and Euler rotation."""
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock
import logging


class TestColumnDetection:
    def _make_plugin(self):
        from plugins.protein import ProteinLoaderPlugin
        viewer = MagicMock()
        viewer.layers = MagicMock()
        viewer.layers.selection = MagicMock()
        viewer.layers.selection.events = MagicMock()
        plugin = ProteinLoaderPlugin.__new__(ProteinLoaderPlugin)
        plugin.viewer = viewer
        plugin.logger = logging.getLogger("test")
        return plugin

    def test_detect_coordinate_columns_relion(self):
        plugin = self._make_plugin()
        df = pd.DataFrame({
            "_rlnCoordinateX": [1.0],
            "_rlnCoordinateY": [2.0],
            "_rlnCoordinateZ": [3.0],
        })
        cols = plugin._detect_coordinate_columns(df)
        assert cols == ["_rlnCoordinateX", "_rlnCoordinateY", "_rlnCoordinateZ"]

    def test_detect_coordinate_columns_simple(self):
        plugin = self._make_plugin()
        df = pd.DataFrame({"x": [1], "y": [2], "z": [3]})
        cols = plugin._detect_coordinate_columns(df)
        assert cols == ["x", "y", "z"]

    def test_detect_coordinate_columns_missing(self):
        plugin = self._make_plugin()
        df = pd.DataFrame({"a": [1], "b": [2]})
        cols = plugin._detect_coordinate_columns(df)
        assert cols is None

    def test_detect_orientation_columns(self):
        plugin = self._make_plugin()
        df = pd.DataFrame({
            "_rlnAngleRot": [0],
            "_rlnAngleTilt": [0],
            "_rlnAnglePsi": [0],
        })
        cols = plugin._detect_orientation_columns(df)
        assert cols == ["_rlnAngleRot", "_rlnAngleTilt", "_rlnAnglePsi"]

    def test_detect_orientation_columns_missing(self):
        plugin = self._make_plugin()
        df = pd.DataFrame({"a": [1]})
        cols = plugin._detect_orientation_columns(df)
        assert cols is None


class TestEulerRotation:
    def _make_plugin(self):
        from plugins.protein import ProteinLoaderPlugin
        plugin = ProteinLoaderPlugin.__new__(ProteinLoaderPlugin)
        plugin.logger = logging.getLogger("test")
        return plugin

    def test_identity_rotation(self):
        plugin = self._make_plugin()
        R = plugin._euler_to_rotation_matrix(0, 0, 0)
        np.testing.assert_array_almost_equal(R, np.eye(3))

    def test_rotation_is_orthogonal(self):
        plugin = self._make_plugin()
        R = plugin._euler_to_rotation_matrix(45, 30, 60)
        # R @ R.T should be identity
        np.testing.assert_array_almost_equal(R @ R.T, np.eye(3), decimal=10)

    def test_determinant_is_one(self):
        plugin = self._make_plugin()
        R = plugin._euler_to_rotation_matrix(90, 45, 180)
        assert abs(np.linalg.det(R) - 1.0) < 1e-10

    def test_apply_rotation_preserves_shape(self):
        plugin = self._make_plugin()
        verts = np.random.rand(100, 3)
        R = plugin._euler_to_rotation_matrix(30, 60, 90)
        rotated = plugin._apply_rotation_to_vertices(verts, R)
        assert rotated.shape == (100, 3)
