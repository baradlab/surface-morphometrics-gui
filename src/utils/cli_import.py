"""Pure CLI-import planning and execution (in-place adoption).

"Import CLI Project" registers an existing CLI output directory as a GUI
experiment WITHOUT copying. The source directory becomes the experiment
directory; the experiment name is the source dir's basename. If the source
has files flat at the top level, they're moved into a `results/` subdir
(lossless rename, same filesystem) so the rest of the GUI's tabs find them
where they expect.

This module owns: the scan, the validation, the plan dataclass, the
execute step (move + atomic config write). No Qt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Optional

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

logger = logging.getLogger(__name__)


CONFIG_REQUIRED_ANY = (
    'seg_dir', 'data_dir', 'segmentation_values', 'surface_generation',
    'curvature_measurements', 'distance_and_orientation_measurements',
)
OUTPUT_EXTENSIONS = {'.vtp', '.ply', '.xyz', '.csv', '.gt', '.log', '.svg', '.png'}


@dataclass
class ScanResult:
    """What's in the source directory, split by current location."""
    flat_files: list[Path]              # known-extension files at the top of source/
    results_files: list[Path]           # known-extension files inside source/results/
    has_existing_config: bool           # True if a *_config.yml or config.yml exists at top

    @property
    def total(self) -> int:
        return len(self.flat_files) + len(self.results_files)


def scan_cli_dir(source_dir: Path) -> ScanResult:
    """Inspect source_dir. Symlinks are ignored entirely."""
    source_dir = Path(source_dir)
    flat: list[Path] = []
    in_results: list[Path] = []

    for entry in source_dir.iterdir():
        if entry.is_symlink():
            continue
        if entry.is_file() and entry.suffix in OUTPUT_EXTENSIONS:
            flat.append(entry)

    results_dir = source_dir / 'results'
    if results_dir.is_dir():
        for entry in results_dir.iterdir():
            if entry.is_symlink():
                continue
            if entry.is_file() and entry.suffix in OUTPUT_EXTENSIONS:
                in_results.append(entry)

    has_cfg = (
        any(source_dir.glob('*_config.yml')) or
        (source_dir / 'config.yml').is_file()
    )

    return ScanResult(flat_files=flat, results_files=in_results, has_existing_config=has_cfg)


def looks_like_morphometrics_config(data: Any) -> bool:
    """Heuristic shape check on a parsed YAML."""
    if not isinstance(data, dict):
        return False
    return any(k in data for k in CONFIG_REQUIRED_ANY)


def read_yaml(path: Path) -> tuple[Optional[dict], Optional[str]]:
    """Read a YAML file. Returns (data, error_message). Either may be None."""
    yaml = YAML()
    yaml.preserve_quotes = True
    try:
        with open(path, 'r') as f:
            return yaml.load(f) or {}, None
    except (OSError, YAMLError) as e:
        return None, f"{type(e).__name__}: {e}"


def write_yaml_atomic(dest_path: Path, data: dict) -> None:
    """Write YAML via tempfile + os.replace so dest is never partially written."""
    yaml = YAML()
    yaml.preserve_quotes = True
    dest_path = Path(dest_path)
    fd, tmp_name = tempfile.mkstemp(
        prefix=dest_path.name + '.', suffix='.tmp', dir=str(dest_path.parent)
    )
    try:
        with os.fdopen(fd, 'w') as f:
            yaml.dump(data, f)
        os.replace(tmp_name, str(dest_path))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


@dataclass
class CliImportInputs:
    """Raw inputs from the user. Pure data."""
    source_dir: Path
    config_data: Optional[dict]
    config_source_label: str
    data_dir_override: Optional[Path] = None
    overwrite_existing_config: bool = False
    cores: int = 1


@dataclass
class CliImportPlan:
    """Validated, ready to execute. source_dir IS the experiment dir."""
    inputs: CliImportInputs
    exp_name: str                                  # always source_dir.name
    exp_dir: Path                                  # always source_dir
    results_dir: Path
    dest_config_path: Path
    moves: list[tuple[Path, Path]] = field(default_factory=list)   # (src, dst) for flat → results/
    move_collisions: list[Path] = field(default_factory=list)       # flat files skipped because results/ has same name
    config_to_write: dict = field(default_factory=dict)
    existing_config_overwrite: bool = False

    @property
    def overlays(self) -> dict[str, Any]:
        return {
            'work_dir': str(self.exp_dir),
            'exp_name': self.exp_name,
            'cores': self.inputs.cores,
        }


@dataclass
class PlanError:
    code: str
    message: str

    EMPTY_SOURCE = 'empty_source'
    NO_CONFIG = 'no_config'
    DATA_DIR_MISSING = 'data_dir_missing'
    EXISTING_CONFIG_NEEDS_CONFIRM = 'existing_config_needs_confirm'


@dataclass
class ExecutionResult:
    moved: int
    failed_moves: list[tuple[Path, str]]
    dest_config_path: Path
    success: bool


def build_plan(
    inputs: CliImportInputs,
    scan: ScanResult,
) -> tuple[Optional[CliImportPlan], Optional[PlanError]]:
    """Build a validated plan from inputs + scan. Pure: no disk mutation."""
    if scan.total == 0:
        return None, PlanError(PlanError.EMPTY_SOURCE,
            "No recognizable CLI output files found in the selected directory.\n"
            "Expected .vtp, .csv, .ply, .gt, .xyz, .svg, .png, or .log files\n"
            "either at the top level or inside a results/ subdirectory.")

    if inputs.config_data is None:
        return None, PlanError(PlanError.NO_CONFIG,
            "No config supplied and no template configured. Pick a config "
            "file or set a Config Template before adopting.")

    source_dir = Path(inputs.source_dir)
    exp_name = source_dir.name
    exp_dir = source_dir
    results_dir = source_dir / 'results'
    dest_config_path = exp_dir / f"{exp_name}_config.yml"

    # Existing config at the dest path needs explicit confirmation.
    if dest_config_path.is_file() and not inputs.overwrite_existing_config:
        return None, PlanError(PlanError.EXISTING_CONFIG_NEEDS_CONFIRM,
            f"A config already exists at:\n  {dest_config_path}\n"
            "Enable 'Overwrite existing config' to replace it.")

    # Resolve the segmentation dir from the config. Relative paths are
    # interpreted against the source directory. Accept the legacy ``data_dir``
    # alias but always write the packaged-CLI key ``seg_dir``.
    config_data = dict(inputs.config_data)
    if inputs.data_dir_override is not None:
        config_data['seg_dir'] = str(inputs.data_dir_override)
        config_data.pop('data_dir', None)
    else:
        raw = config_data.get('seg_dir') or config_data.get('data_dir')
        if raw:
            candidate = Path(str(raw))
            if not candidate.is_absolute():
                candidate = (source_dir / candidate).resolve()
            if not candidate.is_dir():
                return None, PlanError(PlanError.DATA_DIR_MISSING,
                    f"The config's seg_dir does not exist:\n  {raw}\n"
                    "Pick a replacement directory.")
            config_data['seg_dir'] = str(candidate)
            config_data.pop('data_dir', None)

    # Plan moves: flat files → results/<name>. Skip names that already
    # exist in results/ — we never overwrite an existing result file.
    existing_in_results = {p.name for p in scan.results_files}
    moves: list[tuple[Path, Path]] = []
    move_collisions: list[Path] = []
    for src in scan.flat_files:
        if src.name in existing_in_results:
            move_collisions.append(src)
            continue
        moves.append((src, results_dir / src.name))

    config_data['work_dir'] = str(exp_dir)
    config_data['exp_name'] = exp_name
    config_data['cores'] = inputs.cores

    plan = CliImportPlan(
        inputs=inputs,
        exp_name=exp_name,
        exp_dir=exp_dir,
        results_dir=results_dir,
        dest_config_path=dest_config_path,
        moves=moves,
        move_collisions=move_collisions,
        config_to_write=config_data,
        existing_config_overwrite=dest_config_path.is_file(),
    )
    return plan, None


def execute_plan(plan: CliImportPlan) -> ExecutionResult:
    """Move flat files into results/, then write the config atomically.

    Moves are lossless renames (same filesystem). On per-file move failure,
    we continue with the rest — the source dir's data is never destroyed,
    only relocated. If the config write fails, already-moved files stay in
    results/ (the GUI can still find them); we never try to undo moves.
    """
    plan.results_dir.mkdir(parents=True, exist_ok=True)

    failed: list[tuple[Path, str]] = []
    moved = 0
    for src, dst in plan.moves:
        try:
            os.replace(str(src), str(dst))
            moved += 1
        except OSError as e:
            failed.append((src, str(e)))

    write_yaml_atomic(plan.dest_config_path, plan.config_to_write)
    return ExecutionResult(
        moved=moved,
        failed_moves=failed,
        dest_config_path=plan.dest_config_path,
        success=True,
    )
