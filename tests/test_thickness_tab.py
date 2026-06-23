"""Tests for ThicknessWidget."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from ruamel.yaml import YAML


@pytest.mark.gui
class TestThicknessWidget:
    def _make_widget(self, qapp, mock_experiment_manager):
        from jobs.thickness_tab import ThicknessWidget
        # Prevent _on_config_loaded from running during init.
        mock_experiment_manager.config_loaded = MagicMock()
        mock_experiment_manager.current_config = None
        return ThicknessWidget(mock_experiment_manager)

    def test_creation_defaults(self, qapp, mock_experiment_manager):
        w = self._make_widget(qapp, mock_experiment_manager)
        assert w.sample_spacing_input.value == 0.25
        assert w.scan_range_input.value == 10.0
        assert w.average_radius_input.value == 12.0
        assert w.fit_curve_input.value is True

    def test_components_from_segmentation_values(self, qapp, mock_experiment_manager):
        w = self._make_widget(qapp, mock_experiment_manager)
        mock_experiment_manager.current_config = {"segmentation_values": {"ER": 1, "PM": 2}}
        w._populate_components()
        # All components pre-checked when nothing is saved yet.
        assert sorted(w._selected_components()) == ["ER", "PM"]

    def test_components_preselect_from_saved(self, qapp, mock_experiment_manager):
        w = self._make_widget(qapp, mock_experiment_manager)
        mock_experiment_manager.current_config = {
            "segmentation_values": {"ER": 1, "PM": 2},
            "thickness_measurements": {"components": ["ER"]},
        }
        w._populate_components()
        assert w._selected_components() == ["ER"]

    def test_update_config_writes_thickness_keys(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        mock_experiment_manager.current_config = {
            "segmentation_values": {"ER": 1, "PM": 2},
            "curvature_measurements": {"radius_hit": 9},
        }
        mock_experiment_manager.work_dir.value = str(tmp_path)
        mock_experiment_manager.experiment_name.currentText.return_value = "exp"
        mock_experiment_manager.cores_input.value.return_value = 4
        (tmp_path / "exp").mkdir()
        w.tomo_dir_input.value = str(tmp_path / "tomos")

        config_path = w._update_config(["ER", "PM"])

        yaml = YAML()
        with open(config_path) as f:
            cfg = yaml.load(f)
        assert cfg["density_sampling"]["sample_spacing"] == 0.25
        assert cfg["density_sampling"]["scan_range"] == 10.0
        assert cfg["thickness_measurements"]["average_radius"] == 12.0
        assert cfg["thickness_measurements"]["components"] == ["ER", "PM"]
        assert cfg["tomo_dir"].endswith("/")
        # work_dir must end in a separator for the CLI's string concatenation.
        assert cfg["work_dir"].endswith("/")
