"""Tests for RefinementWidget."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from ruamel.yaml import YAML


@pytest.mark.gui
class TestRefinementWidget:
    def _make_widget(self, qapp, mock_experiment_manager):
        from jobs.refinement_tab import RefinementWidget
        # Prevent _on_config_loaded from running during init.
        mock_experiment_manager.config_loaded = MagicMock()
        mock_experiment_manager.current_config = None
        return RefinementWidget(mock_experiment_manager)

    def test_creation_defaults(self, qapp, mock_experiment_manager):
        w = self._make_widget(qapp, mock_experiment_manager)
        assert w.iterations_input.value == 6
        assert w.damping_input.value == 0.9
        assert w.average_radius_input.value == 25.0
        assert w.max_offset_input.value == 8.0
        assert w.xcorr_iterations_input.value == 3
        assert w.monolayer_input.value is False
        assert w.smooth_offsets_input.value is True

    def test_on_config_loaded_collapses_xcorr_list(self, qapp, mock_experiment_manager):
        w = self._make_widget(qapp, mock_experiment_manager)
        mock_experiment_manager.current_config = {
            "mesh_refinement": {"iterations": 8, "xcorr_iterations": [1, 2, 3, 4]},
        }
        w._on_config_loaded()
        assert w.iterations_input.value == 8
        # A list of iteration numbers collapses to the "first N" form.
        assert w.xcorr_iterations_input.value == 4

    def test_update_config_writes_refinement_keys(self, qapp, mock_experiment_manager, tmp_path):
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
        w.iterations_input.value = 5
        w.xcorr_iterations_input.value = 2

        config_path = w._update_config()

        yaml = YAML()
        with open(config_path) as f:
            cfg = yaml.load(f)
        ref = cfg["mesh_refinement"]
        assert ref["iterations"] == 5
        assert ref["damping_factor"] == 0.9
        assert ref["average_radius"] == 25.0
        assert ref["max_total_offset"] == 8.0
        # Written as an int ("first N iterations"), which the CLI accepts.
        assert ref["xcorr_iterations"] == 2
        assert ref["monolayer"] is False
        assert cfg["tomo_dir"].endswith("/")
        # work_dir must end in a separator for the CLI's string concatenation.
        assert cfg["work_dir"].endswith("/")
