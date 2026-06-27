"""Resolving how to invoke the packaged surface_morphometrics pipeline.

The pipeline used to ship as loose scripts run with ``python run_pycurv.py
config.yml``. It is now an installed package exposing a single ``morphometrics``
CLI (``morphometrics pycurv config.yml ...``). This module resolves the command
prefix for that CLI and maps each GUI pipeline step to its subcommand name.
"""
import importlib.util
import os
import shutil
import sys
from pathlib import Path

# `morphometrics` subcommand names for each GUI pipeline step.
MAKE_MESHES = "make_meshes"
PYCURV = "pycurv"
DISTANCES_ORIENTATIONS = "distances_orientations"
# Thickness is two steps: sample tomogram density along normals, then fit it.
SAMPLE_DENSITY = "sample_density"
MEASURE_THICKNESS = "measure_thickness"
# Optional density-guided mesh refinement (after pycurv, before distances):
# refine_mesh iterates, then accept_refinement commits a chosen iteration.
REFINE_MESH = "refine_mesh"
ACCEPT_REFINEMENT = "accept_refinement"


def results_dir(work_dir_field, exp_name):
    """Canonical output directory for an experiment: ``<work_dir>/<exp_name>/results``.

    Every pipeline step reads and writes here. Keeping it in one place stops
    the three job tabs from drifting into disagreeing locations.
    """
    return Path(work_dir_field) / str(exp_name) / "results"


def cli_work_dir(results_directory):
    """The ``work_dir`` value to write into config.yml for the CLI.

    The packaged pipeline builds output paths by string concatenation
    (``work_dir + basename``), so ``work_dir`` MUST end in a path separator and
    point at the single directory shared by every step.
    """
    return str(results_directory) + os.sep


# Filenames the pipeline produces at any stage — used to detect whether a
# directory already holds pipeline outputs.
_OUTPUT_MARKERS = ("*.surface.vtp", "*.AVV_rh*.gt", "*.AVV_rh*.vtp",
                   "*.AVV_rh*.csv", "*.ply", "*.xyz")


def _has_pipeline_outputs(directory):
    directory = Path(directory)
    if not directory.is_dir():
        return False
    return any(next(directory.glob(pattern), None) is not None
               for pattern in _OUTPUT_MARKERS)


def resolve_work_dir(exp_dir):
    """The directory the pipeline reads from and writes to for an experiment.

    The GUI organizes outputs under ``<exp_dir>/results``, but a CLI user runs
    the pipeline with everything flat in the experiment directory itself. To
    drive the CLI for either layout without moving files, pick whichever
    directory already holds outputs:

    - ``results/`` when it contains pipeline outputs (GUI-organized, or a
      project adopted via "Import CLI Project");
    - ``exp_dir`` when outputs sit flat there (a raw CLI project being resumed);
    - ``results/`` otherwise (a fresh experiment — keep GUI output organized).
    """
    exp_dir = Path(exp_dir)
    organized = exp_dir / "results"
    if _has_pipeline_outputs(organized):
        return organized
    if _has_pipeline_outputs(exp_dir):
        return exp_dir
    return organized


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
