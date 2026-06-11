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

    def test_cli_runner_prefers_console_script(self, monkeypatch):
        import utils.script_resolver as sr
        monkeypatch.setattr(sr.shutil, "which", lambda name: "/usr/bin/morphometrics")
        assert sr.resolve_cli_runner() == ["/usr/bin/morphometrics"]

    def test_cli_runner_falls_back_to_module(self, monkeypatch):
        import utils.script_resolver as sr
        monkeypatch.setattr(sr.shutil, "which", lambda name: None)
        monkeypatch.setattr(sr.importlib.util, "find_spec", lambda name: object())
        runner = sr.resolve_cli_runner()
        assert runner[1:] == ["-m", "surface_morphometrics.cli"]

    def test_cli_runner_none_when_not_installed(self, monkeypatch):
        import utils.script_resolver as sr
        monkeypatch.setattr(sr.shutil, "which", lambda name: None)
        monkeypatch.setattr(sr.importlib.util, "find_spec", lambda name: None)
        assert sr.resolve_cli_runner() is None

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
