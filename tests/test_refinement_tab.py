"""Tests for RefinementWidget."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def _setup_refined(self, w, mock_experiment_manager, tmp_path, files):
        """Create refined_iter surfaces under the experiment's work dir."""
        mock_experiment_manager.work_dir.value = str(tmp_path)
        mock_experiment_manager.experiment_name.currentText.return_value = "exp"
        from utils.script_resolver import resolve_work_dir
        work_dir = resolve_work_dir(tmp_path / "exp")
        work_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            (work_dir / name).write_text("")
        return work_dir

    def test_refresh_discovers_per_component_iterations(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        self._setup_refined(w, mock_experiment_manager, tmp_path, [
            "tomo1_labels_IMM_refined_iter1.surface.vtp",
            "tomo1_labels_IMM_refined_iter6.surface.vtp",
            "tomo1_labels_OMM_refined_iter1.surface.vtp",
            "tomo1_labels_OMM_refined_iter4.surface.vtp",
            "tomo1_labels_OMM_refined_iter5.surface.vtp",
        ])

        w._refresh_accept_components()

        assert set(w._component_steps) == {"IMM", "OMM"}
        imm, omm = w._component_steps["IMM"], w._component_steps["OMM"]
        # Range spans the available iterations; default is the final (converged) one.
        assert (imm.min, imm.max, imm.value) == (1, 6, 6)
        assert (omm.min, omm.max, omm.value) == (1, 5, 5)
        assert w.accept_btn.isEnabled()

    def test_refresh_preserves_prior_selection(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        self._setup_refined(w, mock_experiment_manager, tmp_path, [
            "t_IMM_refined_iter1.surface.vtp",
            "t_IMM_refined_iter6.surface.vtp",
        ])
        w._refresh_accept_components()
        w._component_steps["IMM"].value = 3
        w._refresh_accept_components()
        assert w._component_steps["IMM"].value == 3

    def test_refresh_no_files_disables_accept(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        self._setup_refined(w, mock_experiment_manager, tmp_path, [])
        w._refresh_accept_components()
        assert w._component_steps == {}
        assert not w.accept_btn.isEnabled()

    def test_accept_worker_runs_one_call_per_component(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        work_dir = self._setup_refined(w, mock_experiment_manager, tmp_path, [])
        config_path = work_dir / "exp_config.yml"
        config_path.write_text("work_dir: x\n")

        job_data = {
            "runner": ["morphometrics"],
            "config_path": config_path,
            "choices": {"IMM": 6, "OMM": 5},
        }
        with patch("jobs.refinement_tab.subprocess.run") as run:
            w._accept_worker(job_data)

        cmds = [c.args[0] for c in run.call_args_list]
        assert len(cmds) == 2
        for cmd, comp, step in [(cmds[0], "IMM", "6"), (cmds[1], "OMM", "5")]:
            assert cmd[-3:] == [step, "--component", comp]


class _FakeLayer:
    def __init__(self, path):
        self.path = path
        self.name = path
        self.visible = True


class _FakeLayerViewer:
    def __init__(self):
        self.layers = []
        self.reset_view_called = 0

    def reset_view(self):
        self.reset_view_called += 1


class _FakeMeshViewer:
    """Minimal stand-in: _load_mesh_file appends a surface layer to the viewer."""
    def __init__(self):
        self.viewer = _FakeLayerViewer()
        self.loaded = []

    def _load_mesh_file(self, path):
        self.loaded.append(path)
        self.viewer.layers.append(_FakeLayer(path))


@pytest.mark.gui
class TestRefinementPreview:
    def _make_widget(self, mock_experiment_manager, mesh_viewer):
        from jobs.refinement_tab import RefinementWidget
        mock_experiment_manager.config_loaded = MagicMock()
        mock_experiment_manager.current_config = None
        return RefinementWidget(mock_experiment_manager, mesh_viewer=mesh_viewer)

    def _setup_refined(self, mock_experiment_manager, tmp_path, files):
        mock_experiment_manager.work_dir.value = str(tmp_path)
        mock_experiment_manager.experiment_name.currentText.return_value = "exp"
        from utils.script_resolver import resolve_work_dir
        work_dir = resolve_work_dir(tmp_path / "exp")
        work_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            (work_dir / name).write_text("")
        return work_dir

    def test_preview_builds_layers_including_iter0(self, qapp, mock_experiment_manager, tmp_path):
        mv = _FakeMeshViewer()
        w = self._make_widget(mock_experiment_manager, mv)
        self._setup_refined(mock_experiment_manager, tmp_path, [
            "t_IMM.surface.vtp",  # iter0 = original
            "t_IMM_refined_iter1.surface.vtp",
            "t_IMM_refined_iter6.surface.vtp",
        ])
        w._refresh_accept_components()
        w._preview_iterations()

        names = {l.name for _c, _n, l in w._preview_layers}
        assert names == {
            "refine-preview:IMM:iter0",
            "refine-preview:IMM:iter1",
            "refine-preview:IMM:iter6",
        }
        # Default spinbox value (final iter) is the only visible layer.
        visible = {n for _c, n, l in w._preview_layers if l.visible}
        assert visible == {6}
        assert mv.viewer.reset_view_called == 1

    def test_spinbox_scrubs_visibility(self, qapp, mock_experiment_manager, tmp_path):
        mv = _FakeMeshViewer()
        w = self._make_widget(mock_experiment_manager, mv)
        self._setup_refined(mock_experiment_manager, tmp_path, [
            "t_IMM.surface.vtp",
            "t_IMM_refined_iter1.surface.vtp",
            "t_IMM_refined_iter6.surface.vtp",
        ])
        w._refresh_accept_components()
        w._preview_iterations()

        w._component_steps["IMM"].value = 1  # emits changed -> _on_step_changed
        visible = {n for _c, n, l in w._preview_layers if l.visible}
        assert visible == {1}

    def test_clear_preview_removes_layers(self, qapp, mock_experiment_manager, tmp_path):
        mv = _FakeMeshViewer()
        w = self._make_widget(mock_experiment_manager, mv)
        self._setup_refined(mock_experiment_manager, tmp_path, [
            "t_IMM_refined_iter1.surface.vtp",
        ])
        w._refresh_accept_components()
        w._preview_iterations()
        assert mv.viewer.layers
        w._clear_preview()
        assert w._preview_layers == []
        assert mv.viewer.layers == []

    def test_refresh_clears_stale_preview(self, qapp, mock_experiment_manager, tmp_path):
        mv = _FakeMeshViewer()
        w = self._make_widget(mock_experiment_manager, mv)
        self._setup_refined(mock_experiment_manager, tmp_path, [
            "t_IMM_refined_iter1.surface.vtp",
        ])
        w._refresh_accept_components()
        w._preview_iterations()
        assert w._preview_layers
        w._refresh_accept_components()
        assert w._preview_layers == []
        assert mv.viewer.layers == []

    def test_no_viewer_disables_preview(self, qapp, mock_experiment_manager):
        w = self._make_widget(mock_experiment_manager, None)
        assert w.preview_btn is None
        assert w.clear_preview_btn is None
