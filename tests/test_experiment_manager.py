"""Tests for ExperimentManager."""
import os
import stat
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


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


# ---------------------------------------------------------------------------
# Import-CLI-project tests
# ---------------------------------------------------------------------------

# A minimal but realistic morphometrics config for fixture use.
_VALID_CONFIG_YAML = textwrap.dedent("""
    data_dir: {data_dir}
    work_dir: /tmp/old_work
    segmentation_values:
      ER: 1
      PM: 2
    surface_generation:
      angstroms: false
      ultrafine: true
      target_area: 1.0
      simplify: false
      max_triangles: 300000
      extrapolation_distance: 1.5
      octree_depth: 7
      point_weight: 0.7
      neighbor_count: 400
      smoothing_iterations: 1
    curvature_measurements:
      radius_hit: 9
      min_component: 30
      exclude_borders: 1.0
    distance_and_orientation_measurements:
      mindist: 3.0
      maxdist: 400.0
      tolerance: 0.1
      verticality: true
      relative_orientation: true
      intra: [ER]
      inter:
        PM: [ER]
    cores: 4
    script_location: /tmp/scripts
""").strip()


def _make_cli_dir(root: Path, with_config: bool = True, nested: bool = False,
                  data_dir_path: str = None) -> Path:
    """Build a synthetic CLI output directory at `root` and return it."""
    root.mkdir(parents=True, exist_ok=True)
    if nested:
        sub = root / "results"
        sub.mkdir()
        (sub / "tomo1.vtp").write_text("vtp-data-1")
        (sub / "tomo1.csv").write_text("x,y,z\n1,2,3\n")
    else:
        (root / "tomo1.vtp").write_text("vtp-data-1")
        (root / "tomo1.csv").write_text("x,y,z\n1,2,3\n")
    if with_config:
        cfg = root / "tomo1_config.yml"
        cfg.write_text(_VALID_CONFIG_YAML.format(
            data_dir=data_dir_path or str(root / "data")
        ))
        if data_dir_path is None:
            (root / "data").mkdir(exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# Pure planner tests — exercise utils.cli_import without Qt.
# In-place adoption: source dir IS the experiment dir, no copies.
# ---------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict:
    from ruamel.yaml import YAML
    return YAML().load(path.read_text())


class TestCliImportPlanner:
    """Pure-function tests of in-place adoption."""

    def _inputs(self, source_dir, **overrides):
        from utils.cli_import import CliImportInputs
        kw = dict(
            source_dir=Path(source_dir),
            config_data={"data_dir": str(source_dir), "segmentation_values": {"ER": 1}},
            config_source_label="file: x",
            data_dir_override=None,
            overwrite_existing_config=False,
            cores=4,
        )
        kw.update(overrides)
        return CliImportInputs(**kw)

    def test_scan_splits_flat_and_results_files(self, tmp_path):
        from utils.cli_import import scan_cli_dir
        (tmp_path / "a.vtp").write_text("a")
        (tmp_path / "b.csv").write_text("b")
        (tmp_path / "ignored.txt").write_text("z")
        results = tmp_path / "results"
        results.mkdir()
        (results / "c.gt").write_text("c")
        scan = scan_cli_dir(tmp_path)
        assert {p.name for p in scan.flat_files} == {"a.vtp", "b.csv"}
        assert {p.name for p in scan.results_files} == {"c.gt"}
        assert scan.has_existing_config is False

    def test_scan_detects_existing_config(self, tmp_path):
        from utils.cli_import import scan_cli_dir
        (tmp_path / "x.vtp").write_text("x")
        (tmp_path / "myexp_config.yml").write_text("data_dir: /x")
        scan = scan_cli_dir(tmp_path)
        assert scan.has_existing_config is True

    def test_scan_ignores_symlinks(self, tmp_path):
        from utils.cli_import import scan_cli_dir
        outside = tmp_path.parent / "outside.vtp"
        outside.write_text("o")
        (tmp_path / "link.vtp").symlink_to(outside)
        (tmp_path / "real.vtp").write_text("r")
        scan = scan_cli_dir(tmp_path)
        assert {p.name for p in scan.flat_files} == {"real.vtp"}

    def test_empty_source_yields_empty_source_error(self, tmp_path):
        from utils.cli_import import build_plan, PlanError, ScanResult
        inp = self._inputs(tmp_path)
        plan, err = build_plan(inp, ScanResult([], [], False))
        assert plan is None and err.code == PlanError.EMPTY_SOURCE

    def test_no_config_yields_no_config_error(self, tmp_path):
        from utils.cli_import import build_plan, PlanError, ScanResult
        inp = self._inputs(tmp_path, config_data=None)
        scan = ScanResult([tmp_path / "a.vtp"], [], False)
        plan, err = build_plan(inp, scan)
        assert plan is None and err.code == PlanError.NO_CONFIG

    def test_data_dir_missing_yields_specific_error(self, tmp_path):
        from utils.cli_import import build_plan, PlanError, ScanResult
        inp = self._inputs(tmp_path, config_data={"data_dir": "/nonexistent/zzz"})
        scan = ScanResult([tmp_path / "a.vtp"], [], False)
        plan, err = build_plan(inp, scan)
        assert plan is None and err.code == PlanError.DATA_DIR_MISSING

    def test_data_dir_override_resolves(self, tmp_path):
        from utils.cli_import import build_plan, ScanResult
        replacement = tmp_path.parent / "real_data"
        replacement.mkdir()
        inp = self._inputs(
            tmp_path,
            config_data={"data_dir": "/nonexistent/zzz"},
            data_dir_override=replacement,
        )
        scan = ScanResult([tmp_path / "a.vtp"], [], False)
        plan, err = build_plan(inp, scan)
        assert err is None
        assert plan.config_to_write["data_dir"] == str(replacement)

    def test_existing_config_needs_confirm(self, tmp_path):
        from utils.cli_import import build_plan, PlanError, ScanResult
        (tmp_path / f"{tmp_path.name}_config.yml").write_text("data_dir: /x")
        inp = self._inputs(tmp_path)
        scan = ScanResult([tmp_path / "a.vtp"], [], True)
        plan, err = build_plan(inp, scan)
        assert plan is None and err.code == PlanError.EXISTING_CONFIG_NEEDS_CONFIRM

    def test_existing_config_with_overwrite_allowed(self, tmp_path):
        from utils.cli_import import build_plan, ScanResult
        (tmp_path / f"{tmp_path.name}_config.yml").write_text("data_dir: /x")
        inp = self._inputs(tmp_path, overwrite_existing_config=True)
        scan = ScanResult([tmp_path / "a.vtp"], [], True)
        plan, err = build_plan(inp, scan)
        assert err is None
        assert plan.existing_config_overwrite is True

    def test_exp_name_is_always_source_basename(self, tmp_path):
        from utils.cli_import import build_plan, ScanResult
        src = tmp_path / "my_run_42"
        src.mkdir()
        inp = self._inputs(src)
        scan = ScanResult([src / "a.vtp"], [], False)
        plan, err = build_plan(inp, scan)
        assert err is None
        assert plan.exp_name == "my_run_42"
        assert plan.exp_dir == src
        assert plan.dest_config_path == src / "my_run_42_config.yml"

    def test_overlays_applied_to_saved_config(self, tmp_path):
        from utils.cli_import import build_plan, ScanResult
        inp = self._inputs(tmp_path, cores=8)
        scan = ScanResult([tmp_path / "a.vtp"], [], False)
        plan, err = build_plan(inp, scan)
        assert err is None
        assert plan.config_to_write["work_dir"] == str(plan.exp_dir)
        assert plan.config_to_write["exp_name"] == plan.exp_name
        assert plan.config_to_write["cores"] == 8

    def test_already_organized_yields_no_moves(self, tmp_path):
        from utils.cli_import import build_plan, ScanResult
        results_file = tmp_path / "results" / "a.vtp"
        results_file.parent.mkdir()
        results_file.write_text("a")
        inp = self._inputs(tmp_path)
        scan = ScanResult([], [results_file], False)
        plan, err = build_plan(inp, scan)
        assert err is None
        assert plan.moves == []

    def test_flat_files_planned_for_move_into_results(self, tmp_path):
        from utils.cli_import import build_plan, ScanResult
        a = tmp_path / "a.vtp"
        a.write_text("a")
        inp = self._inputs(tmp_path)
        scan = ScanResult([a], [], False)
        plan, err = build_plan(inp, scan)
        assert err is None
        assert plan.moves == [(a, tmp_path / "results" / "a.vtp")]

    def test_flat_collision_with_results_is_skipped(self, tmp_path):
        from utils.cli_import import build_plan, ScanResult
        flat = tmp_path / "a.vtp"
        flat.write_text("flat")
        results = tmp_path / "results"
        results.mkdir()
        existing = results / "a.vtp"
        existing.write_text("existing")
        inp = self._inputs(tmp_path)
        scan = ScanResult([flat], [existing], False)
        plan, err = build_plan(inp, scan)
        assert err is None
        assert plan.moves == []
        assert plan.move_collisions == [flat]

    def test_execute_moves_flat_files_and_writes_config(self, tmp_path):
        from utils.cli_import import build_plan, execute_plan, ScanResult
        flat = tmp_path / "tomo.vtp"
        flat.write_text("vtp")
        inp = self._inputs(tmp_path)
        scan = ScanResult([flat], [], False)
        plan, _ = build_plan(inp, scan)
        result = execute_plan(plan)
        assert result.success
        assert result.moved == 1
        assert not flat.exists(), "flat file should have been moved"
        assert (tmp_path / "results" / "tomo.vtp").is_file()
        assert plan.dest_config_path.is_file()

    def test_execute_skips_moves_when_already_organized(self, tmp_path):
        from utils.cli_import import build_plan, execute_plan, ScanResult
        rf = tmp_path / "results" / "tomo.vtp"
        rf.parent.mkdir()
        rf.write_text("vtp")
        inp = self._inputs(tmp_path)
        scan = ScanResult([], [rf], False)
        plan, _ = build_plan(inp, scan)
        result = execute_plan(plan)
        assert result.success and result.moved == 0
        assert rf.is_file()
        assert plan.dest_config_path.is_file()

    def test_execute_does_not_delete_source_on_config_write_failure(self, tmp_path, monkeypatch):
        from utils.cli_import import build_plan, execute_plan, ScanResult
        flat = tmp_path / "tomo.vtp"
        flat.write_text("vtp")
        inp = self._inputs(tmp_path)
        scan = ScanResult([flat], [], False)
        plan, _ = build_plan(inp, scan)
        import utils.cli_import as ci
        monkeypatch.setattr(ci, "write_yaml_atomic",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
        with pytest.raises(OSError):
            execute_plan(plan)
        # Source dir must still exist; the file may have been moved into results/
        assert tmp_path.exists()
        assert (tmp_path / "results" / "tomo.vtp").is_file()


# ---------------------------------------------------------------------------
# Wrapper integration tests — drive the dialog by injecting a plan.
# ---------------------------------------------------------------------------


@pytest.mark.gui
class TestImportCliProjectFlow:
    def _make_manager(self, qapp, tmp_path, work_dir=None, template_path=None):
        with patch("experiment_manager.napari"):
            with patch("experiment_manager.plt"):
                from experiment_manager import ExperimentManager
                viewer = MagicMock()
                viewer.layers = MagicMock()
                viewer.layers.selection = MagicMock()
                em = ExperimentManager(viewer)
                em.work_dir.value = str(work_dir) if work_dir else str(tmp_path / "work")
                Path(em.work_dir.value).mkdir(parents=True, exist_ok=True)
                if template_path:
                    em.config_template.value = str(template_path)
                em.segmentation_container = MagicMock()
                em.segmentation_container.get_values.return_value = {}
                em.segmentation_container._set_values = MagicMock()
                return em

    def _build_plan_from_dir(self, source_dir):
        """Synthesize a real plan as if the dialog produced it."""
        from utils.cli_import import build_plan, scan_cli_dir, CliImportInputs
        scan = scan_cli_dir(source_dir)
        cfg_path = next(source_dir.glob("*_config.yml"), None) or (source_dir / "config.yml")
        cfg_data = _read_yaml(cfg_path)
        inp = CliImportInputs(
            source_dir=source_dir,
            config_data=cfg_data,
            config_source_label=f"file: {cfg_path}",
            cores=4,
        )
        plan, err = build_plan(inp, scan)
        assert err is None, err
        return plan

    def _patch_dialog(self, monkeypatch, plan, *, accepted=True):
        from qtpy.QtWidgets import QDialog
        import widgets.cli_import_dialog as mod

        class _Stub:
            def __init__(self, *a, **k):
                self.plan = plan if accepted else None

            def exec_(self):
                return QDialog.Accepted if accepted else QDialog.Rejected

        monkeypatch.setattr(mod, "CliImportDialog", _Stub)
        import experiment_manager as em_mod
        seen = {"warning": [], "critical": [], "information": []}
        monkeypatch.setattr(em_mod.QMessageBox, "warning",
                            lambda *a, **k: seen["warning"].append(a))
        monkeypatch.setattr(em_mod.QMessageBox, "critical",
                            lambda *a, **k: seen["critical"].append(a))
        monkeypatch.setattr(em_mod.QMessageBox, "information",
                            lambda *a, **k: seen["information"].append(a))
        return seen

    def test_happy_path_adopts_in_place_and_sets_work_dir(self, qapp, tmp_path, monkeypatch):
        cli = _make_cli_dir(tmp_path / "cli_run")
        em = self._make_manager(qapp, tmp_path)
        plan = self._build_plan_from_dir(cli)
        self._patch_dialog(monkeypatch, plan)
        em._import_cli_project()
        # work_dir should be flipped to source's parent
        assert Path(em.work_dir.value) == cli.parent
        # Source IS the experiment dir; files moved into results/
        assert (cli / "results" / "tomo1.vtp").is_file()
        cfg = _read_yaml(cli / f"{cli.name}_config.yml")
        assert cfg["work_dir"] == str(cli)
        assert cfg["exp_name"] == cli.name

    def test_dialog_rejected_makes_no_changes(self, qapp, tmp_path, monkeypatch):
        cli = _make_cli_dir(tmp_path / "cli_run")
        em = self._make_manager(qapp, tmp_path)
        plan = self._build_plan_from_dir(cli)
        self._patch_dialog(monkeypatch, plan, accepted=False)
        em._import_cli_project()
        # No reorganization happened; flat file still at top
        assert (cli / "tomo1.vtp").is_file()
        assert not (cli / "results").exists()

    def test_permission_error_surfaces_critical_dialog(self, qapp, tmp_path, monkeypatch):
        cli = _make_cli_dir(tmp_path / "cli_run")
        em = self._make_manager(qapp, tmp_path)
        plan = self._build_plan_from_dir(cli)
        seen = self._patch_dialog(monkeypatch, plan)
        import utils.cli_import as ci
        monkeypatch.setattr(ci, "execute_plan",
                            lambda p: (_ for _ in ()).throw(PermissionError("denied")))
        em._import_cli_project()
        assert any("Permission Denied" in args[1] for args in seen["critical"])

    def test_partial_move_failure_surfaces_warning(self, qapp, tmp_path, monkeypatch):
        from utils.cli_import import ExecutionResult
        cli = _make_cli_dir(tmp_path / "cli_run")
        em = self._make_manager(qapp, tmp_path)
        plan = self._build_plan_from_dir(cli)
        seen = self._patch_dialog(monkeypatch, plan)
        import utils.cli_import as ci
        fake_result = ExecutionResult(
            moved=1,
            failed_moves=[(Path("/x/bad.vtp"), "locked")],
            dest_config_path=plan.dest_config_path,
            success=True,
        )
        monkeypatch.setattr(ci, "execute_plan", lambda p: fake_result)
        em._import_cli_project()
        assert any("Adopted With Errors" in args[1] for args in seen["warning"])
