"""Single-form wizard for "Import CLI Project" (in-place adoption).

Pick a source CLI output directory, a config, and click OK. The source
directory becomes the GUI experiment in place — files are NOT copied.
If files are flat at the top of the source, they're moved into a
results/ subdir on accept (lossless rename, same filesystem).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from qtpy.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QRadioButton, QTextEdit, QVBoxLayout, QWidget,
)

from utils.cli_import import (
    CliImportInputs, CliImportPlan, PlanError, ScanResult,
    build_plan, looks_like_morphometrics_config, read_yaml, scan_cli_dir,
)


class CliImportDialog(QDialog):
    """Collect inputs and resolve the in-place adoption plan in one modal."""

    def __init__(
        self,
        parent: Optional[QWidget],
        *,
        template_data: Optional[dict],
        template_path: Optional[Path],
        cores: int,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import CLI Project (adopt in place)")
        self.setMinimumWidth(640)

        self._template_data = template_data
        self._template_path = template_path
        self._cores = cores

        self._scan: Optional[ScanResult] = None
        self._picked_config_data: Optional[dict] = None
        self._picked_config_path: Optional[Path] = None
        self._data_dir_override: Optional[Path] = None
        self.plan: Optional[CliImportPlan] = None

        self._build_ui()
        self._wire_signals()
        self._revalidate()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        intro = QLabel(
            "<b>Adopt an existing CLI output directory as a GUI experiment.</b><br>"
            "Files are <i>not</i> copied. The source directory becomes the "
            "experiment. If files are at the top level, they'll be moved into "
            "a <code>results/</code> subdir."
        )
        intro.setWordWrap(True)
        outer.addWidget(intro)

        # Source directory
        src_box = QGroupBox("Source CLI output directory")
        src_form = QFormLayout(src_box)
        self.src_label = QLineEdit()
        self.src_label.setReadOnly(True)
        self.src_label.setPlaceholderText("(no directory selected)")
        src_browse = QPushButton("Browse…")
        src_browse.clicked.connect(self._pick_source_dir)
        src_row = QHBoxLayout()
        src_row.addWidget(self.src_label, 1)
        src_row.addWidget(src_browse)
        src_row_widget = QWidget()
        src_row_widget.setLayout(src_row)
        src_form.addRow("Source:", src_row_widget)
        outer.addWidget(src_box)

        # Config source
        cfg_box = QGroupBox("Config")
        cfg_layout = QVBoxLayout(cfg_box)
        self.cfg_group = QButtonGroup(self)
        self.cfg_file_radio = QRadioButton("Use config file from disk")
        self.cfg_tmpl_radio = QRadioButton("Use the configured Config Template")
        self.cfg_group.addButton(self.cfg_file_radio, 0)
        self.cfg_group.addButton(self.cfg_tmpl_radio, 1)
        cfg_layout.addWidget(self.cfg_file_radio)

        file_row = QHBoxLayout()
        file_row.addSpacing(24)
        self.cfg_file_label = QLineEdit()
        self.cfg_file_label.setReadOnly(True)
        self.cfg_file_label.setPlaceholderText("(no file selected)")
        self.cfg_file_browse = QPushButton("Browse…")
        self.cfg_file_browse.clicked.connect(self._pick_config_file)
        file_row.addWidget(self.cfg_file_label, 1)
        file_row.addWidget(self.cfg_file_browse)
        file_row_widget = QWidget()
        file_row_widget.setLayout(file_row)
        cfg_layout.addWidget(file_row_widget)

        cfg_layout.addWidget(self.cfg_tmpl_radio)
        tmpl_note = QLabel(
            f"    {self._template_path}" if self._template_path
            else "    (no template configured)"
        )
        tmpl_note.setStyleSheet("color: gray;")
        cfg_layout.addWidget(tmpl_note)
        if self._template_data is None:
            self.cfg_tmpl_radio.setEnabled(False)

        # Default: prefer template if available, else file
        if self._template_data is not None:
            self.cfg_tmpl_radio.setChecked(True)
        else:
            self.cfg_file_radio.setChecked(True)
        outer.addWidget(cfg_box)

        # Options
        opts_box = QGroupBox("Options")
        opts_layout = QVBoxLayout(opts_box)
        self.overwrite_cfg = QCheckBox("Overwrite existing config in source dir (if present)")
        opts_layout.addWidget(self.overwrite_cfg)
        outer.addWidget(opts_box)

        # data_dir override
        self.dd_box = QGroupBox("data_dir replacement")
        dd_layout = QHBoxLayout(self.dd_box)
        self.dd_label = QLineEdit()
        self.dd_label.setReadOnly(True)
        self.dd_label.setPlaceholderText("(config's data_dir is missing — pick a replacement)")
        dd_browse = QPushButton("Pick…")
        dd_browse.clicked.connect(self._pick_data_dir_replacement)
        dd_layout.addWidget(self.dd_label, 1)
        dd_layout.addWidget(dd_browse)
        self.dd_box.setVisible(False)
        outer.addWidget(self.dd_box)

        # Preview
        preview_box = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_box)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(220)
        preview_layout.addWidget(self.preview)
        outer.addWidget(preview_box, 1)

        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

    def _wire_signals(self) -> None:
        self.cfg_group.buttonClicked.connect(lambda *_: self._revalidate())
        self.overwrite_cfg.stateChanged.connect(lambda *_: self._revalidate())

    # ---------- Pickers ----------

    def _pick_source_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Select CLI Output Directory", "", QFileDialog.ShowDirsOnly
        )
        if not chosen:
            return
        self.src_label.setText(chosen)
        self._data_dir_override = None
        self.dd_label.setText("")
        try:
            self._scan = scan_cli_dir(Path(chosen))
        except OSError as e:
            self._scan = None
            self._show_error_preview(f"Could not scan directory:\n  {e}")
            return
        self._revalidate()

    def _pick_config_file(self) -> None:
        start_dir = self.src_label.text() or ""
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Select Config File", start_dir, "YAML files (*.yml *.yaml)"
        )
        if not chosen:
            return
        data, err = read_yaml(Path(chosen))
        if err is not None:
            self._picked_config_data = None
            self._picked_config_path = None
            self.cfg_file_label.setText("")
            self._show_error_preview(f"Could not read config:\n  {err}")
            return
        if not looks_like_morphometrics_config(data):
            self._picked_config_data = None
            self._picked_config_path = None
            self.cfg_file_label.setText("")
            self._show_error_preview(
                "The selected YAML doesn't look like a morphometrics config."
            )
            return
        self._picked_config_data = data
        self._picked_config_path = Path(chosen)
        self.cfg_file_label.setText(chosen)
        self.cfg_file_radio.setChecked(True)
        self._revalidate()

    def _pick_data_dir_replacement(self) -> None:
        start = self.src_label.text() or ""
        chosen = QFileDialog.getExistingDirectory(
            self, "Select Replacement data_dir", start, QFileDialog.ShowDirsOnly
        )
        if not chosen:
            return
        self._data_dir_override = Path(chosen)
        self.dd_label.setText(chosen)
        self._revalidate()

    # ---------- Plan-building & preview ----------

    def _selected_config(self) -> tuple[Optional[dict], str]:
        bid = self.cfg_group.checkedId()
        if bid == 0:
            if self._picked_config_data is not None:
                return self._picked_config_data, f"file: {self._picked_config_path}"
            return None, "file (none selected)"
        if bid == 1:
            if self._template_data is not None:
                return self._template_data, f"template: {self._template_path}"
            return None, "template (not configured)"
        return None, "(none)"

    def _build_inputs(self) -> Optional[CliImportInputs]:
        src_text = self.src_label.text().strip()
        if not src_text:
            return None
        cfg_data, cfg_label = self._selected_config()
        return CliImportInputs(
            source_dir=Path(src_text),
            config_data=cfg_data,
            config_source_label=cfg_label,
            data_dir_override=self._data_dir_override,
            overwrite_existing_config=self.overwrite_cfg.isChecked(),
            cores=self._cores,
        )

    def _revalidate(self) -> None:
        self.plan = None
        ok_btn = self.buttons.button(QDialogButtonBox.Ok)
        ok_btn.setEnabled(False)

        inputs = self._build_inputs()
        if inputs is None or self._scan is None:
            self._show_status_preview("Pick a CLI output directory to begin.")
            self.dd_box.setVisible(False)
            return

        plan, err = build_plan(inputs, self._scan)
        if err is not None:
            self.dd_box.setVisible(err.code == PlanError.DATA_DIR_MISSING)
            self._show_error_preview(err.message)
            return

        self.dd_box.setVisible(False)
        self.plan = plan
        self._show_plan_preview(plan)
        ok_btn.setEnabled(True)

    def _show_status_preview(self, msg: str) -> None:
        self.preview.setHtml(f"<p style='color: gray;'>{msg}</p>")

    def _show_error_preview(self, msg: str) -> None:
        self.preview.setHtml(
            f"<p style='color: #c0392b;'><b>Cannot import:</b></p><pre>{msg}</pre>"
        )

    def _show_plan_preview(self, plan: CliImportPlan) -> None:
        scan = self._scan
        lines = []
        lines.append("<b>Ready to adopt this directory as an experiment.</b>")
        lines.append("")
        lines.append(f"Experiment dir: <code>{plan.exp_dir}</code>")
        lines.append(f"Experiment name: <code>{plan.exp_name}</code> "
                     f"<span style='color: gray;'>(= source dir name)</span>")
        lines.append(f"work_dir will be set to: <code>{plan.exp_dir.parent}</code>")
        lines.append("")

        if scan and scan.results_files and not plan.moves:
            lines.append(f"Layout: <b>already organized</b> — "
                         f"{len(scan.results_files)} file(s) in <code>results/</code>. "
                         f"No file moves needed.")
        elif plan.moves:
            lines.append(f"Layout: will <b>move {len(plan.moves)}</b> flat file(s) into "
                         f"<code>results/</code> (lossless rename, same filesystem).")
            if scan and scan.results_files:
                lines.append(f"  ({len(scan.results_files)} file(s) already in results/ untouched.)")
        if plan.move_collisions:
            names = ", ".join(p.name for p in plan.move_collisions[:5])
            more = f" (+{len(plan.move_collisions)-5} more)" if len(plan.move_collisions) > 5 else ""
            lines.append(
                f"<span style='color: #c0392b;'>Skipping {len(plan.move_collisions)} flat "
                f"file(s) — a file of the same name already exists in results/: {names}{more}</span>"
            )

        lines.append("")
        lines.append(f"Config source: {plan.inputs.config_source_label}")
        lines.append(f"Saved config: <code>{plan.dest_config_path}</code>")
        if plan.existing_config_overwrite:
            lines.append(
                "<span style='color: #c0392b;'>"
                "<b>Note:</b> an existing config at this path will be overwritten.</span>"
            )

        lines.append("")
        lines.append("<b>The saved config will set these keys from GUI values:</b>")
        for k, v in plan.overlays.items():
            lines.append(f"  <code>{k}</code> = <code>{v}</code>")
        self.preview.setHtml("<br>".join(lines))
