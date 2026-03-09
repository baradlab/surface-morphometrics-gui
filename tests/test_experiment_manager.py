"""Tests for ExperimentManager."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


@pytest.mark.gui
class TestExperimentManager:
    def _make_manager(self, qapp):
        with patch("experiment_manager.napari"):
            with patch("experiment_manager.plt"):
                from experiment_manager import ExperimentManager
                viewer = MagicMock()
                viewer.layers = MagicMock()
                viewer.layers.selection = MagicMock()
                em = ExperimentManager(viewer)
                return em

    def test_creation(self, qapp):
        em = self._make_manager(qapp)
        assert em.current_config == {}
        assert em.submit_button.text() == "New Experiment"

    def test_button_disabled_initially(self, qapp):
        em = self._make_manager(qapp)
        assert not em.submit_button.isEnabled()

    def test_update_experiment_names_empty_dir(self, qapp, tmp_path):
        em = self._make_manager(qapp)
        em.work_dir.value = str(tmp_path)
        em._update_experiment_names()
        assert em.experiment_name.count() == 0

    def test_update_experiment_names_with_experiments(self, qapp, tmp_path):
        em = self._make_manager(qapp)
        # Create experiment directory with config
        exp_dir = tmp_path / "exp1"
        exp_dir.mkdir()
        (exp_dir / "exp1_config.yml").write_text("key: value")
        em.work_dir.value = str(tmp_path)
        em._update_experiment_names()
        assert em.experiment_name.count() == 1

    def test_clear_experiment_fields(self, qapp):
        em = self._make_manager(qapp)
        em._clear_experiment_fields()
        assert em.submit_button.text() == "Start New Experiment"
