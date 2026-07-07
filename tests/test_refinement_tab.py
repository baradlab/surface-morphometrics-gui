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

    def test_refresh_discovers_per_surface_iterations(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        self._setup_refined(w, mock_experiment_manager, tmp_path, [
            "tomo1_labels_IMM_refined_iter1.surface.vtp",
            "tomo1_labels_IMM_refined_iter6.surface.vtp",
            "tomo1_labels_OMM_refined_iter1.surface.vtp",
            "tomo1_labels_OMM_refined_iter4.surface.vtp",
            "tomo1_labels_OMM_refined_iter5.surface.vtp",
        ])

        w._refresh_accept_components()

        assert set(w._surface_steps) == {"tomo1_labels_IMM", "tomo1_labels_OMM"}
        imm, omm = w._surface_steps["tomo1_labels_IMM"], w._surface_steps["tomo1_labels_OMM"]
        assert (imm.min, imm.max, imm.value) == (1, 6, 6)
        assert (omm.min, omm.max, omm.value) == (1, 5, 5)
        assert w.accept_btn.isEnabled()

    def test_refresh_discovers_all_tomograms_separately(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        self._setup_refined(w, mock_experiment_manager, tmp_path, [
            "TE1_IMM_refined_iter1.surface.vtp",
            "TE1_IMM_refined_iter6.surface.vtp",
            "TE2_IMM_refined_iter1.surface.vtp",
            "TE2_IMM_refined_iter4.surface.vtp",
        ])
        w._refresh_accept_components()

        assert set(w._surface_steps) == {"TE1_IMM", "TE2_IMM"}
        assert w._surface_steps["TE1_IMM"].value == 6
        assert w._surface_steps["TE2_IMM"].value == 4

    def test_refresh_preserves_prior_selection(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        self._setup_refined(w, mock_experiment_manager, tmp_path, [
            "t_IMM_refined_iter1.surface.vtp",
            "t_IMM_refined_iter6.surface.vtp",
        ])
        w._refresh_accept_components()
        w._surface_steps["t_IMM"].value = 3
        w._refresh_accept_components()
        assert w._surface_steps["t_IMM"].value == 3

    def test_refresh_no_files_disables_accept(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        self._setup_refined(w, mock_experiment_manager, tmp_path, [])
        w._refresh_accept_components()
        assert w._surface_steps == {}
        assert not w.accept_btn.isEnabled()

    def test_refresh_uses_saved_config_work_dir(self, qapp, mock_experiment_manager, tmp_path):
        """After resume, discovery must honor config work_dir, not re-guess paths."""
        import os
        w = self._make_widget(qapp, mock_experiment_manager)
        exp_parent = tmp_path / "projects"
        exp_parent.mkdir()
        exp_dir = exp_parent / "exp"
        exp_dir.mkdir()
        work_dir = exp_dir / "results"
        work_dir.mkdir()
        for name in [
            "t_IMM_refined_iter1.surface.vtp",
            "t_IMM_refined_iter6.surface.vtp",
        ]:
            (work_dir / name).write_text("")
        (exp_dir / "exp_config.yml").write_text("work_dir: placeholder\n")

        mock_experiment_manager.work_dir.value = str(exp_parent)
        mock_experiment_manager.experiment_name.currentText.return_value = "exp"
        mock_experiment_manager.current_config = {
            "work_dir": str(work_dir) + os.sep,
        }

        w._refresh_accept_components()
        assert set(w._surface_steps) == {"t_IMM"}
        assert w._surface_steps["t_IMM"].value == 6

    def test_refresh_finds_relative_config_work_dir(self, qapp, mock_experiment_manager, tmp_path):
        """Config work_dir like results/ must resolve against exp_dir, not cwd."""
        w = self._make_widget(qapp, mock_experiment_manager)
        exp_parent = tmp_path / "projects"
        exp_dir = exp_parent / "exp"
        work_dir = exp_dir / "results"
        work_dir.mkdir(parents=True)
        (work_dir / "t_IMM_refined_iter6.surface.vtp").write_text("")
        (exp_dir / "exp_config.yml").write_text("work_dir: results/\n")

        mock_experiment_manager.work_dir.value = str(exp_parent)
        mock_experiment_manager.experiment_name.currentText.return_value = "exp"
        mock_experiment_manager.current_config = {"work_dir": "results/"}

        w._refresh_accept_components()
        assert "t_IMM" in w._surface_steps

    def test_refresh_when_work_dir_field_is_experiment_dir(self, qapp, mock_experiment_manager, tmp_path):
        """Work-dir field may point at the experiment folder, not its parent."""
        w = self._make_widget(qapp, mock_experiment_manager)
        exp_dir = tmp_path / "myexp"
        work_dir = exp_dir / "results"
        work_dir.mkdir(parents=True)
        (work_dir / "TE1_OMM_refined_iter3.surface.vtp").write_text("")
        (exp_dir / "config.yml").write_text("work_dir: results/\n")

        mock_experiment_manager.work_dir.value = str(exp_dir)
        mock_experiment_manager.experiment_name.currentText.return_value = "myexp"
        mock_experiment_manager.current_config = {"work_dir": "results/"}

        w._refresh_accept_components()
        assert set(w._surface_steps) == {"TE1_OMM"}

    def test_accept_worker_runs_one_call_per_surface(self, qapp, mock_experiment_manager, tmp_path):
        w = self._make_widget(qapp, mock_experiment_manager)
        work_dir = self._setup_refined(w, mock_experiment_manager, tmp_path, [])
        config_path = work_dir / "exp_config.yml"
        config_path.write_text("work_dir: x\n")

        job_data = {
            "runner": ["morphometrics"],
            "config_path": config_path,
            "choices": {"TE1_IMM": 6, "TE1_OMM": 5, "TE2_IMM": 4},
        }
        with patch("jobs.refinement_tab.subprocess.run") as run:
            w._accept_worker(job_data)

        cmds = [c.args[0] for c in run.call_args_list]
        assert len(cmds) == 3
        expected = [
            (["6", "--tomogram", "TE1", "--component", "IMM"]),
            (["5", "--tomogram", "TE1", "--component", "OMM"]),
            (["4", "--tomogram", "TE2", "--component", "IMM"]),
        ]
        for cmd, exp_tail in zip(cmds, expected):
            assert cmd[-5:] == exp_tail


class _FakeLayer:
    def __init__(self, path):
        self.path = path
        self.name = path
        self.visible = True
        self.data = None


class _FakeLayerViewer:
    def __init__(self):
        self.layers = []
        self.reset_view_called = 0

    def reset_view(self):
        self.reset_view_called += 1


class _FakeMeshViewer:
    """Minimal stand-in for MeshViewer used by the lazy preview path.

    ``_load_mesh_file`` appends a surface layer to the viewer (layer creation).
    ``read_mesh_tuple`` records disk reads separately so tests can assert the
    mesh cache prevents re-reads while scrubbing.
    """
    def __init__(self):
        self.viewer = _FakeLayerViewer()
        self.loaded = []   # _load_mesh_file calls (layer creation)
        self.reads = []    # read_mesh_tuple calls (disk parses used for scrubbing)

    def read_mesh_tuple(self, path):
        self.reads.append(path)
        # Distinct tuple per path so layer.data swaps are observable.
        return ("verts", "faces", path)

    def _load_mesh_file(self, path, name=None, flat=False, reset_view=True):
        self.loaded.append((path, name, flat, reset_view))
        layer = _FakeLayer(path)
        if name is not None:
            layer.name = name
        # Layer creation carries its own data; not counted as a scrub read.
        layer.data = ("loaded", path)
        self.viewer.layers.append(layer)
        return layer

    def update_surface_layer(self, layer, filepath, flat=True):
        mesh_tuple = self.read_mesh_tuple(filepath)
        layer.data = mesh_tuple
        return mesh_tuple


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

    def test_preview_loads_only_current_iteration(self, qapp, mock_experiment_manager, tmp_path):
        mv = _FakeMeshViewer()
        w = self._make_widget(mock_experiment_manager, mv)
        self._setup_refined(mock_experiment_manager, tmp_path, [
            "t_IMM.surface.vtp",  # iter0 = original
            "t_IMM_refined_iter1.surface.vtp",
            "t_IMM_refined_iter6.surface.vtp",
            "t_OMM.surface.vtp",
            "t_OMM_refined_iter1.surface.vtp",
            "t_OMM_refined_iter5.surface.vtp",
        ])
        w._refresh_accept_components()
        w._preview_iterations()

        # One layer per surface, each at its current (default = final) iteration.
        # No eager loading of iter0/iter1 layers.
        assert set(w._preview_layers) == {"t_IMM", "t_OMM"}
        assert w._preview_layers["t_IMM"].name == "refine-preview:t_IMM:iter6"
        assert w._preview_layers["t_OMM"].name == "refine-preview:t_OMM:iter5"
        assert len(mv.viewer.layers) == 2
        # Only the current iteration was read from disk (via _load_mesh_file).
        assert len(mv.loaded) == 2
        # Preview surfaces load flat and skip the per-load camera reset.
        assert all(flat for _p, _n, flat, _rv in mv.loaded)
        assert all(rv is False for _p, _n, _f, rv in mv.loaded)
        # Single camera reset for the whole preview, not one per layer.
        assert mv.viewer.reset_view_called == 1
        # Small dataset: the large-mode picker stays hidden.
        assert w.preview_surface_combo.isHidden()

    def test_scrub_updates_layer_data_without_new_layer(self, qapp, mock_experiment_manager, tmp_path):
        mv = _FakeMeshViewer()
        w = self._make_widget(mock_experiment_manager, mv)
        self._setup_refined(mock_experiment_manager, tmp_path, [
            "t_IMM_refined_iter1.surface.vtp",
            "t_IMM_refined_iter6.surface.vtp",
        ])
        w._refresh_accept_components()
        w._preview_iterations()
        layer = w._preview_layers["t_IMM"]
        assert len(mv.viewer.layers) == 1

        w._surface_steps["t_IMM"].value = 1  # emits changed -> _on_step_changed

        # No new layer created; the same layer's data/name reflects iter1.
        assert len(mv.viewer.layers) == 1
        assert w._preview_layers["t_IMM"] is layer
        assert layer.name == "refine-preview:t_IMM:iter1"
        iter1_path = str(w._preview_catalog["t_IMM"][1])
        assert layer.data == ("verts", "faces", iter1_path)

    def test_scrub_cache_hit_avoids_reread(self, qapp, mock_experiment_manager, tmp_path):
        mv = _FakeMeshViewer()
        w = self._make_widget(mock_experiment_manager, mv)
        self._setup_refined(mock_experiment_manager, tmp_path, [
            "t_IMM_refined_iter1.surface.vtp",
            "t_IMM_refined_iter6.surface.vtp",
        ])
        w._refresh_accept_components()
        w._preview_iterations()

        iter1_path = str(w._preview_catalog["t_IMM"][1])
        w._surface_steps["t_IMM"].value = 1  # first scrub to iter1 -> disk read
        assert mv.reads.count(iter1_path) == 1
        w._surface_steps["t_IMM"].value = 6  # scrub away
        w._surface_steps["t_IMM"].value = 1  # scrub back -> served from cache
        assert mv.reads.count(iter1_path) == 1

    def test_clear_preview_removes_layers_and_cache(self, qapp, mock_experiment_manager, tmp_path):
        mv = _FakeMeshViewer()
        w = self._make_widget(mock_experiment_manager, mv)
        self._setup_refined(mock_experiment_manager, tmp_path, [
            "t_IMM_refined_iter1.surface.vtp",
        ])
        w._refresh_accept_components()
        w._preview_iterations()
        assert mv.viewer.layers
        w._clear_preview()
        assert w._preview_layers == {}
        assert w._preview_catalog == {}
        assert len(w._preview_mesh_cache) == 0
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
        assert w._preview_layers == {}
        assert w._preview_catalog == {}
        assert mv.viewer.layers == []

    def test_large_mode_single_layer_and_combo_swap(self, qapp, mock_experiment_manager, tmp_path):
        mv = _FakeMeshViewer()
        w = self._make_widget(mock_experiment_manager, mv)
        # 9 surfaces > PREVIEW_ALL_THRESHOLD (8) triggers single-surface mode.
        files = []
        for i in range(9):
            files.append(f"t{i}_IMM_refined_iter1.surface.vtp")
            files.append(f"t{i}_IMM_refined_iter6.surface.vtp")
        self._setup_refined(mock_experiment_manager, tmp_path, files)
        w._refresh_accept_components()

        assert len(w._surface_steps) == 9
        # Large mode shows the surface picker.
        assert not w.preview_surface_combo.isHidden()
        assert w.preview_surface_combo.count() == 9

        w._preview_iterations()
        # Only one layer exists even though there are 9 surfaces.
        assert len(mv.viewer.layers) == 1
        assert len(w._preview_layers) == 1
        first = w.preview_surface_combo.itemText(0)
        assert set(w._preview_layers) == {first}
        assert w._preview_active_basename == first

        # Switching the combo swaps to the other surface, still one layer.
        other = w.preview_surface_combo.itemText(1)
        w.preview_surface_combo.setCurrentText(other)
        assert len(mv.viewer.layers) == 1
        assert set(w._preview_layers) == {other}
        assert w._preview_active_basename == other

    def test_no_viewer_disables_preview(self, qapp, mock_experiment_manager):
        w = self._make_widget(mock_experiment_manager, None)
        assert w.preview_btn is None
        assert w.clear_preview_btn is None
        assert w.preview_surface_combo is None
