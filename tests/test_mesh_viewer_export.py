from pathlib import Path

from surface_morphometrics_gui.plugins.mesh_viewer import export_feature_name, resolve_config_path


def test_export_feature_name_strips_prefixes():
    assert export_feature_name("Cell_curvedness_VV") == "curvedness_VV"
    assert export_feature_name("Point_thickness") == "thickness"
    assert export_feature_name("gauss_curvature") == "gauss_curvature"


def test_resolve_config_path_prefers_named_config(tmp_path):
    vtp = tmp_path / "results" / "surface.AVV_rh9.vtp"
    vtp.parent.mkdir(parents=True)
    vtp.write_text("stub")
    cfg = tmp_path / "myexp_config.yml"
    cfg.write_text("work_dir: results/\n")

    assert resolve_config_path(vtp).resolve() == cfg.resolve()


def test_resolve_config_path_falls_back_to_config_yml(tmp_path):
    vtp = tmp_path / "surface.vtp"
    vtp.write_text("stub")
    cfg = tmp_path / "config.yml"
    cfg.write_text("work_dir: ./\n")

    assert resolve_config_path(vtp).resolve() == cfg.resolve()


def test_resolve_config_path_uses_experiment_manager(tmp_path):
    vtp = tmp_path / "elsewhere" / "surface.vtp"
    vtp.parent.mkdir(parents=True)
    vtp.write_text("stub")

    exp_dir = tmp_path / "exp1"
    exp_dir.mkdir()
    cfg = exp_dir / "exp1_config.yml"
    cfg.write_text("work_dir: results/\n")

    class EM:
        work_dir = type("W", (), {"value": str(tmp_path)})()
        experiment_name = type("N", (), {"currentText": lambda self: "exp1"})()

    assert resolve_config_path(vtp, EM()).resolve() == cfg.resolve()
