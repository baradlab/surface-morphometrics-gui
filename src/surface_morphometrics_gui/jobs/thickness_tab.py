import copy
import os
import subprocess
import threading
from pathlib import Path

from magicgui import widgets
from qtpy.QtCore import QTimer
from ruamel.yaml import YAML
from qtpy.QtWidgets import (
    QCheckBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..utils.archive_utils import check_and_archive_outputs
from ..utils.script_resolver import (
    resolve_cli_runner,
    CLI_MISSING_MESSAGE,
    SAMPLE_DENSITY,
    MEASURE_THICKNESS,
    resolve_work_dir,
    cli_work_dir,
)
from ..widgets.job_status import JobStatusWidget


class ThicknessWidget(QWidget):
    """Membrane thickness measurement tab.

    Thickness is a two-step CLI flow run sequentially from one button:

    1. ``morphometrics sample_density`` samples tomogram density along surface
       normals, reading the pycurv ``.gt`` graphs in the work dir and the
       tomograms in ``tomo_dir``, writing ``*_sampling.csv`` per surface.
    2. ``morphometrics measure_thickness`` fits a dual Gaussian to each profile
       and writes ``component_list.csv`` plus per-surface plots.

    The shared ExperimentManager has no ``tomo_dir`` field, so this tab captures
    it (sample_density requires it) and writes it into the experiment config.
    """

    def __init__(self, experiment_manager):
        super().__init__()
        self.experiment_manager = experiment_manager
        self.component_checkboxes = []
        self.is_running = False

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        self.setLayout(main_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout()
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner.setLayout(inner_layout)
        scroll.setWidget(inner)
        main_layout.addWidget(scroll)

        inner_layout.addWidget(QLabel("<b>Membrane Thickness Measurement</b>"))

        # --- Tomogram directory (not held by ExperimentManager) ---
        inner_layout.addWidget(QLabel("Tomogram Directory (raw MRCs for density sampling):"))
        self.tomo_dir_input = widgets.FileEdit(mode='d', label='Tomogram Dir')
        inner_layout.addWidget(self.tomo_dir_input.native)

        # --- Sampling + fitting settings ---
        settings = widgets.Container(layout='vertical', labels=True)
        settings.native.layout().setSpacing(5)
        settings.native.layout().setContentsMargins(3, 3, 3, 3)
        self.sample_spacing_input = widgets.FloatSpinBox(
            value=0.25, min=0.01, max=10.0, step=0.05, label='Sample Spacing (nm)')
        self.sample_spacing_input.tooltip = "Distance between samples along the normal. Should divide evenly into scan range."
        self.scan_range_input = widgets.FloatSpinBox(
            value=10.0, min=1.0, max=100.0, step=1.0, label='Scan Range (nm)')
        self.scan_range_input.tooltip = "Half-range scanned along the normal (-range to +range)."
        self.average_radius_input = widgets.FloatSpinBox(
            value=12.0, min=1.0, max=100.0, step=1.0, label='Average Radius (nm)')
        self.average_radius_input.tooltip = "Radius for local averaging of density profiles in the fit."
        self.fit_curve_input = widgets.CheckBox(value=True, label='Fit Dual Gaussian')
        settings.extend([
            self.sample_spacing_input,
            self.scan_range_input,
            self.average_radius_input,
            self.fit_curve_input,
        ])
        inner_layout.addWidget(QLabel("<b>Settings</b>"))
        inner_layout.addWidget(settings.native)

        # --- Components to process (from segmentation_values) ---
        inner_layout.addWidget(QLabel("<b>Components to Measure:</b>"))
        self.refresh_btn = QPushButton('Refresh Components')
        self.refresh_btn.clicked.connect(self._populate_components)
        inner_layout.addWidget(self.refresh_btn)
        self.components_container = QWidget()
        self.components_layout = QVBoxLayout()
        self.components_layout.setContentsMargins(0, 0, 0, 0)
        self.components_container.setLayout(self.components_layout)
        inner_layout.addWidget(self.components_container)

        # --- Run + status ---
        self.submit_btn = widgets.PushButton(text='Run Thickness Analysis')
        self.submit_btn.clicked.connect(self._run_job)
        self.status = JobStatusWidget()
        inner_layout.addWidget(self.submit_btn.native)
        inner_layout.addWidget(self.status.native)
        inner_layout.addStretch(1)

        if hasattr(self.experiment_manager, 'config_loaded'):
            self.experiment_manager.config_loaded.connect(self._on_config_loaded)
            if self.experiment_manager.current_config:
                self._on_config_loaded()

    def _segmentation_components(self):
        """Component names available to measure, taken from segmentation_values."""
        config = self.experiment_manager.current_config or {}
        seg = config.get('segmentation_values', {}) or {}
        return list(seg.keys())

    def _populate_components(self):
        for i in reversed(range(self.components_layout.count())):
            w = self.components_layout.itemAt(i).widget()
            if w is not None:
                w.setParent(None)
        self.component_checkboxes.clear()

        names = self._segmentation_components()
        if not names:
            self.components_layout.addWidget(
                QLabel("No segmentation labels found. Configure the experiment first."))
            return

        # Pre-check whatever the saved config already targets for thickness;
        # default to all components when nothing is saved yet.
        config = self.experiment_manager.current_config or {}
        saved = config.get('thickness_measurements', {}).get('components')
        preselect = set(saved) if saved else set(names)

        for name in names:
            cb = QCheckBox(name)
            cb.setChecked(name in preselect)
            self.component_checkboxes.append(cb)
            self.components_layout.addWidget(cb)

    def _selected_components(self):
        return [cb.text() for cb in self.component_checkboxes if cb.isChecked()]

    def _on_config_loaded(self):
        try:
            self.status.update_status('Ready')
            self.status.update_progress(0)
            self._populate_components()
            config = self.experiment_manager.current_config or {}
            if config.get('tomo_dir'):
                self.tomo_dir_input.value = config['tomo_dir']
            density = config.get('density_sampling',
                                 config.get('thickness_measurements', {}))
            self.sample_spacing_input.value = density.get('sample_spacing', 0.25)
            self.scan_range_input.value = density.get('scan_range', 10)
            thickness = config.get('thickness_measurements', {})
            self.average_radius_input.value = thickness.get('average_radius', 12)
            self.fit_curve_input.value = thickness.get('fit_curve', True)
        except Exception as e:
            print(f"[ThicknessWidget] Error in _on_config_loaded: {e}")

    def _update_config(self, components):
        """Write current widget values into the experiment config.yml."""
        if not self.experiment_manager.current_config:
            raise ValueError("Experiment configuration not loaded.")

        exp_name = self.experiment_manager.experiment_name.currentText()
        exp_dir = Path(self.experiment_manager.work_dir.value) / exp_name
        preferred_config_path = exp_dir / f"{exp_name}_config.yml"
        fallback_config_path = exp_dir / 'config.yml'
        config_path = preferred_config_path if preferred_config_path.exists() else fallback_config_path

        yaml = YAML()
        yaml.preserve_quotes = True
        existing = {}
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    existing = yaml.load(f) or {}
            except Exception:
                existing = {}
        else:
            config_path = preferred_config_path
            existing = copy.deepcopy(self.experiment_manager.current_config)

        # Every step shares one output dir; the CLI concatenates work_dir +
        # basename, so it must end in a separator.
        out_dir = resolve_work_dir(exp_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        existing['work_dir'] = cli_work_dir(out_dir)
        existing['cores'] = self.experiment_manager.cores_input.value()

        # sample_density globs tomo_dir for *.mrc; the CLI appends a separator
        # itself but we normalize here so the saved config is unambiguous.
        tomo_dir = str(self.tomo_dir_input.value)
        existing['tomo_dir'] = tomo_dir + os.sep if not tomo_dir.endswith(os.sep) else tomo_dir

        existing.setdefault('density_sampling', {})
        existing['density_sampling'].update({
            'sample_spacing': self.sample_spacing_input.value,
            'scan_range': self.scan_range_input.value,
        })

        existing.setdefault('thickness_measurements', {})
        existing['thickness_measurements'].update({
            'average_radius': self.average_radius_input.value,
            'fit_curve': self.fit_curve_input.value,
            'components': components,
        })

        with open(config_path, 'w') as f:
            yaml.dump(existing, f)

        return config_path

    def _run_job(self):
        if self.is_running:
            return

        components = self._selected_components()
        if not components:
            QMessageBox.warning(self, "No Components", "Select at least one component to measure.")
            return

        tomo_dir = str(self.tomo_dir_input.value or '')
        if not tomo_dir or not Path(tomo_dir).is_dir():
            QMessageBox.warning(self, "No Tomogram Directory",
                                "Select the directory containing the raw tomogram MRC files.")
            return
        if not list(Path(tomo_dir).glob('*.mrc')):
            QMessageBox.warning(self, "No Tomograms",
                                f"No .mrc files found in {tomo_dir}.")
            return

        try:
            config_path = self._update_config(components)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update config: {e}")
            return

        runner = resolve_cli_runner()
        if runner is None:
            QMessageBox.critical(self, "morphometrics CLI not found", CLI_MISSING_MESSAGE)
            print(f"[Error] {CLI_MISSING_MESSAGE}")
            return

        # Thickness outputs only; never touch the pycurv graphs/curvature CSVs.
        try:
            exp_name = self.experiment_manager.experiment_name.currentText()
            exp_dir = Path(self.experiment_manager.work_dir.value) / exp_name
            archive_dir = resolve_work_dir(exp_dir)
            if not check_and_archive_outputs(
                self, archive_dir, config_path=config_path,
                file_patterns=['*_sampling.csv', 'component_list.csv', '*_thickness*.svg', '*_thickness*.png'],
            ):
                print("User cancelled.")
                return
        except Exception as e:
            print(f"Archive check failed: {e}")

        job_data = {'runner': runner, 'config_path': config_path}
        self.is_running = True
        self.submit_btn.enabled = False
        self.status.update_status('Starting...')
        self.status.update_progress(0)
        threading.Thread(target=self._run_job_worker, args=(job_data,), daemon=True).start()

    def _run_job_worker(self, job_data):
        try:
            runner = job_data['runner']
            config_path = job_data['config_path']
            work_dir = resolve_work_dir(Path(config_path).parent).resolve()

            # Step 1: sample density (processes every tomogram in tomo_dir).
            self.status.update_status('Step 1/2: Sampling tomogram density...')
            self.status.update_progress(10)
            cmd = runner + [SAMPLE_DENSITY, str(config_path)]
            print(f"--- Sampling density: {' '.join(cmd)} ---")
            try:
                subprocess.run(cmd, cwd=work_dir, check=True, text=True)
            except subprocess.CalledProcessError:
                self.status.update_status('Error: density sampling failed. See terminal.')
                print("[ERROR] sample_density failed. Check the terminal output.")
                return

            # sample_density catches per-surface errors and still exits 0, so
            # confirm sampling CSVs were actually written before fitting.
            if not list(work_dir.glob('*_sampling.csv')):
                self.status.update_status('Error: no sampling output produced.')
                print("[ERROR] sample_density produced no *_sampling.csv. "
                      "Check that pycurv graphs (.gt) and tomogram basenames match.")
                return

            # Step 2: fit thickness.
            self.status.update_status('Step 2/2: Measuring thickness...')
            self.status.update_progress(60)
            cmd = runner + [MEASURE_THICKNESS, str(config_path)]
            print(f"--- Measuring thickness: {' '.join(cmd)} ---")
            try:
                subprocess.run(cmd, cwd=work_dir, check=True, text=True)
            except subprocess.CalledProcessError:
                self.status.update_status('Error: thickness measurement failed. See terminal.')
                print("[ERROR] measure_thickness failed. Check the terminal output.")
                return

            if not (work_dir / 'component_list.csv').exists():
                self.status.update_status('Error: no thickness output produced.')
                print("[ERROR] measure_thickness produced no component_list.csv.")
                return

            self.status.update_progress(100)
            self.status.update_status('Completed. See component_list.csv and plots in the work dir.')
            print("===== Thickness analysis complete. =====")

        except Exception as e:
            self.status.update_status(f'Error: {e}')
            print(f"A critical error occurred in the thickness worker: {e}")
            import traceback
            traceback.print_exc()
        finally:
            QTimer.singleShot(0, self._job_cleanup)

    def _job_cleanup(self):
        self.submit_btn.enabled = True
        self.is_running = False
