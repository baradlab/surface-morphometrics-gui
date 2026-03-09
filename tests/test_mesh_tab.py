"""Tests for MeshGenerationWidget."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.gui
class TestMeshGenerationWidget:
    def _make_widget(self, qapp, mock_experiment_manager):
        from jobs.mesh_tab import MeshGenerationWidget
        w = MeshGenerationWidget(mock_experiment_manager)
        return w

    def test_creation(self, qapp, mock_experiment_manager):
        w = self._make_widget(qapp, mock_experiment_manager)
        assert w.ultrafine.value is True
        assert w.simplify.value is False
        assert w.max_triangles.value == 300000

    def test_default_consistency_with_config_loaded(self, qapp, mock_experiment_manager):
        """Bug #3 regression: widget init defaults must match _on_config_loaded fallbacks."""
        w = self._make_widget(qapp, mock_experiment_manager)

        # Defaults from __init__
        init_ultrafine = w.ultrafine.value
        init_simplify = w.simplify.value
        init_max_triangles = w.max_triangles.value
        init_octree_depth = w.octree_depth.value
        init_neighbor_count = w.neighbor_count.value

        # Now simulate _on_config_loaded with empty config (uses .get() fallbacks)
        mock_experiment_manager.current_config = {"surface_generation": {}}
        w._on_config_loaded()

        # After bug fix, these should match
        assert w.ultrafine.value == init_ultrafine, \
            f"ultrafine mismatch: init={init_ultrafine}, after_load={w.ultrafine.value}"
        assert w.simplify.value == init_simplify, \
            f"simplify mismatch: init={init_simplify}, after_load={w.simplify.value}"
        assert w.max_triangles.value == init_max_triangles, \
            f"max_triangles mismatch: init={init_max_triangles}, after_load={w.max_triangles.value}"
        assert w.octree_depth.value == init_octree_depth, \
            f"octree_depth mismatch: init={init_octree_depth}, after_load={w.octree_depth.value}"
        assert w.neighbor_count.value == init_neighbor_count, \
            f"neighbor_count mismatch: init={init_neighbor_count}, after_load={w.neighbor_count.value}"

    def test_update_config(self, qapp, mock_experiment_manager, tmp_path):
        """Bug #4 regression: config path should use exp_dir / name / name_config.yml."""
        from ruamel.yaml import YAML

        # Setup experiment directory with config
        exp_name = "test_experiment"
        exp_dir = tmp_path / exp_name
        exp_dir.mkdir()
        config_path = exp_dir / f"{exp_name}_config.yml"
        yaml = YAML()
        yaml.dump({"surface_generation": {}}, config_path.open("w"))

        mock_experiment_manager.work_dir.value = str(tmp_path)
        mock_experiment_manager.experiment_name.currentText.return_value = exp_name

        w = self._make_widget(qapp, mock_experiment_manager)
        result_path, _ = w._update_config()
        assert result_path == config_path
