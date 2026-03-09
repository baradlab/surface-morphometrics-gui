"""Tests for DistanceOrientationWidget."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock


@pytest.mark.gui
class TestDistanceOrientationWidget:
    def _make_widget(self, qapp, mock_experiment_manager):
        from jobs.distance_tab import DistanceOrientationWidget
        mock_experiment_manager.config_loaded = MagicMock()
        mock_experiment_manager.current_config = None
        w = DistanceOrientationWidget(mock_experiment_manager)
        return w

    def test_creation(self, qapp, mock_experiment_manager):
        w = self._make_widget(qapp, mock_experiment_manager)
        assert w.min_dist.value == 3.0
        assert w.max_dist.value == 400.0
        assert w.tolerance.value == 0.1

    def test_update_config(self, qapp, mock_experiment_manager, tmp_path):
        """Bug #5: config_path from _update_config() should be used consistently."""
        from ruamel.yaml import YAML

        exp_name = "test_experiment"
        exp_dir = tmp_path / exp_name
        exp_dir.mkdir()
        config_path = exp_dir / f"{exp_name}_config.yml"
        yaml = YAML()
        yaml.dump({"distance_and_orientation_measurements": {}, "data_dir": "/tmp"}, config_path.open("w"))

        mock_experiment_manager.work_dir.value = str(tmp_path)
        mock_experiment_manager.experiment_name.currentText.return_value = exp_name
        # Set current_config before creating widget so _update_config doesn't raise
        mock_experiment_manager.current_config = {"data_dir": "/tmp", "work_dir": str(tmp_path)}

        w = self._make_widget(qapp, mock_experiment_manager)
        # Re-set current_config since _make_widget sets it to None
        mock_experiment_manager.current_config = {"data_dir": "/tmp", "work_dir": str(tmp_path)}
        result_path = w._update_config()
        assert result_path == config_path

    def test_on_config_loaded(self, qapp, mock_experiment_manager):
        w = self._make_widget(qapp, mock_experiment_manager)
        mock_experiment_manager.current_config = {
            "distance_and_orientation_measurements": {
                "mindist": 5.0,
                "maxdist": 200.0,
                "tolerance": 0.5,
            }
        }
        w._on_config_loaded()
        assert w.min_dist.value == 5.0
        assert w.max_dist.value == 200.0
        assert w.tolerance.value == 0.5
