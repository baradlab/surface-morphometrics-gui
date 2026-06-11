"""Resolving how to invoke the packaged surface_morphometrics pipeline.

The pipeline used to ship as loose scripts run with ``python run_pycurv.py
config.yml``. It is now an installed package exposing a single ``morphometrics``
CLI (``morphometrics pycurv config.yml ...``). This module resolves the command
prefix for that CLI and maps each GUI pipeline step to its subcommand name.
"""
import importlib.util
import shutil
import sys

# `morphometrics` subcommand names for each GUI pipeline step.
MAKE_MESHES = "make_meshes"
PYCURV = "pycurv"
DISTANCES_ORIENTATIONS = "distances_orientations"


def resolve_cli_runner():
    """Return the command prefix that runs the morphometrics CLI, or None.

    Prefers the installed ``morphometrics`` console script. Falls back to
    ``python -m surface_morphometrics.cli`` when the package is importable but
    its console script isn't on PATH (e.g. a scripts dir that isn't exported).
    Returns ``None`` when surface_morphometrics isn't installed in the current
    environment, so callers can show a clear "install the package" message.
    """
    exe = shutil.which("morphometrics")
    if exe:
        return [exe]
    if importlib.util.find_spec("surface_morphometrics") is not None:
        return [sys.executable, "-m", "surface_morphometrics.cli"]
    return None


CLI_MISSING_MESSAGE = (
    "The 'morphometrics' command was not found.\n\n"
    "This GUI now drives the packaged surface_morphometrics pipeline. Install it "
    "into the same environment as the GUI, e.g.:\n\n"
    "    pip install -e /path/to/surface_morphometrics   (packaging branch)\n\n"
    "then verify with:  morphometrics --help"
)


def get_seg_dir(config):
    """Segmentation directory from a config.

    Accepts the packaged-CLI key ``seg_dir`` and the legacy ``data_dir`` alias
    used by experiments created before the migration, so old experiments still
    resume cleanly.
    """
    if not config:
        return None
    return config.get("seg_dir") or config.get("data_dir")
