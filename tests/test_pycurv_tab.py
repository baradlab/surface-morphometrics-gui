"""Tests for PyCurvWidget."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock


@pytest.mark.gui
class TestPyCurvWidget:
    def _make_widget(self, qapp, mock_experiment_manager):
        from jobs.pycurv_tab import PyCurvWidget
        # Prevent _on_config_loaded from running during init
        mock_experiment_manager.config_loaded = MagicMock()
        mock_experiment_manager.current_config = None
        w = PyCurvWidget(mock_experiment_manager)
        return w

    def test_creation(self, qapp, mock_experiment_manager):
        w = self._make_widget(qapp, mock_experiment_manager)
        assert w.radius_hit_input.value == 9
        assert w.min_component_input.value == 30

    def test_find_script_with_config(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        # Create a script in script_location
        script_dir = tmp_path / "scripts"
        script_dir.mkdir()
        (script_dir / "run_pycurv.py").write_text("# script")
        mock_experiment_manager.current_config = {"script_location": str(script_dir)}
        result = w._find_pycurv_script(tmp_path)
        assert result is not None
        assert result.name == "run_pycurv.py"

    def test_find_script_not_found(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        mock_experiment_manager.current_config = {}
        result = w._find_pycurv_script(tmp_path)
        assert result is None

    def test_populate_vtp_list_no_config(self, qapp, mock_experiment_manager):
        w = self._make_widget(qapp, mock_experiment_manager)
        mock_experiment_manager.current_config = None
        w._populate_vtp_file_list()
        assert len(w.vtp_checkboxes) == 0

    def test_populate_vtp_list_with_files(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        exp_dir = tmp_path / "test_experiment"
        exp_dir.mkdir()
        (exp_dir / "membrane.surface.vtp").write_text("")
        mock_experiment_manager.current_config = {"work_dir": str(tmp_path)}
        mock_experiment_manager.work_dir.value = str(tmp_path)
        mock_experiment_manager.experiment_name.currentText.return_value = "test_experiment"
        w._populate_vtp_file_list()
        assert len(w.vtp_checkboxes) == 1
