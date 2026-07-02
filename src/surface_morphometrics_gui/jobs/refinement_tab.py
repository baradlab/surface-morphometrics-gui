import copy
import os
import re
import subprocess
import threading
from pathlib import Path

from magicgui import widgets
from qtpy.QtCore import QTimer
from ruamel.yaml import YAML
from qtpy.QtWidgets import (
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
    REFINE_MESH,
    ACCEPT_REFINEMENT,
    resolve_work_dir,
    cli_work_dir,
)
from ..widgets.job_status import JobStatusWidget

# Refinement-only outputs. Archived before a re-run and never touch the
# canonical *.surface.vtp / *.AVV_rh*.gt graphs that pycurv produced.
REFINE_OUTPUT_PATTERNS = [
    '*_refined_iter*',
    '*_profile_iter*.png',
    '*_samples_iter*.png',
    '*_refinement_convergence.png',
    '*_refinement_stats.csv',
    '*_profile_evolution.png',
]


class RefinementWidget(QWidget):
    """Optional density-guided mesh refinement tab.

    Refinement is the optional step between curvature (pycurv) and distances.
    It nudges surface vertices toward the true membrane center using the
    tomogram density, in two CLI actions driven from this tab:

    1. ``morphometrics refine_mesh`` iterates over the pycurv ``.gt`` graphs in
       the work dir, sampling density from the tomograms in ``tomo_dir`` and
       writing ``*_refined_iter{N}.*`` surfaces plus convergence/profile plots.
       The user inspects those plots to choose the best iteration.
    2. ``morphometrics accept_refinement <step>`` promotes the chosen iteration
       to be the canonical surface (backing up the original) and removes the
       other refinement intermediates.

    Like thickness, refinement needs a ``tomo_dir`` (not held by the shared
    ExperimentManager) and the existing pycurv graphs, so this tab validates
    both before running.
    """

    def __init__(self, experiment_manager, mesh_viewer=None):
        super().__init__()
        self.experiment_manager = experiment_manager
        # Optional MeshViewer used to preview refined iterations in napari before
        # accepting one. None in headless/test paths — preview is then disabled.
        self.mesh_viewer = mesh_viewer
        # napari layers we created for the current preview: list of
        # (component, iter_n, layer) so visibility/clear needn't re-parse names.
        self._preview_layers = []
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

        inner_layout.addWidget(QLabel("<b>Density-Guided Mesh Refinement</b>"))
        inner_layout.addWidget(QLabel(
            "Optional. Run after curvature, before distances. Refine, inspect the\n"
            "convergence plots in the work dir, then accept the best iteration."))

        # --- Tomogram directory (not held by ExperimentManager) ---
        inner_layout.addWidget(QLabel("Tomogram Directory (raw MRCs for density sampling):"))
        self.tomo_dir_input = widgets.FileEdit(mode='d', label='Tomogram Dir')
        inner_layout.addWidget(self.tomo_dir_input.native)

        # --- Refinement settings ---
        settings = widgets.Container(layout='vertical', labels=True)
        settings.native.layout().setSpacing(5)
        settings.native.layout().setContentsMargins(3, 3, 3, 3)
        self.iterations_input = widgets.SpinBox(
            value=6, min=1, max=50, label='Iterations')
        self.iterations_input.tooltip = "Number of refinement iterations."
        self.damping_input = widgets.FloatSpinBox(
            value=0.9, min=0.0, max=1.0, step=0.05, label='Damping Factor')
        self.damping_input.tooltip = "Fraction of the computed impulse applied per iteration. Lower prevents oscillation."
        self.average_radius_input = widgets.FloatSpinBox(
            value=25.0, min=1.0, max=100.0, step=1.0, label='Average Radius (nm)')
        self.average_radius_input.tooltip = "Radius for local averaging of density profiles. Larger = more smoothing."
        self.max_offset_input = widgets.FloatSpinBox(
            value=8.0, min=0.5, max=50.0, step=0.5, label='Max Total Offset (nm)')
        self.max_offset_input.tooltip = "Maximum total displacement from the original surface. Prevents divergence."
        self.xcorr_iterations_input = widgets.SpinBox(
            value=3, min=0, max=50, label='Initial XCorr Iterations')
        self.xcorr_iterations_input.tooltip = (
            "Number of initial iterations using cross-correlation to sharpen the bilayer "
            "before switching to dual-Gaussian fitting. 0 = Gaussian fitting throughout.")
        self.monolayer_input = widgets.CheckBox(value=False, label='Monolayer (single Gaussian)')
        self.monolayer_input.tooltip = "For high-defocus data where the bilayer is not resolved."
        self.smooth_offsets_input = widgets.CheckBox(value=True, label='Smooth Offset Field')
        self.smooth_offsets_input.tooltip = "Spatially smooth the offset field before applying it. Reduces local noise."
        self.laplacian_input = widgets.SpinBox(
            value=5, min=0, max=20, label='Laplacian Iterations')
        self.laplacian_input.tooltip = "Laplacian smoothing iterations after displacement (0 = disabled)."
        self.laplacian_lambda_input = widgets.FloatSpinBox(
            value=0.5, min=0.0, max=1.0, step=0.05, label='Laplacian Lambda')
        self.laplacian_lambda_input.tooltip = "Laplacian smoothing strength. Higher = more smoothing but may lose detail."
        self.lowpass_input = widgets.FloatSpinBox(
            value=0.0, min=0.0, max=10.0, step=0.5, label='Low-pass Sigma (nm)')
        self.lowpass_input.tooltip = "3D Gaussian low-pass on the tomogram before sampling. 0 = disabled; try 1-3 nm for noisy data."
        settings.extend([
            self.iterations_input,
            self.damping_input,
            self.average_radius_input,
            self.max_offset_input,
            self.xcorr_iterations_input,
            self.monolayer_input,
            self.smooth_offsets_input,
            self.laplacian_input,
            self.laplacian_lambda_input,
            self.lowpass_input,
        ])
        inner_layout.addWidget(QLabel("<b>Settings</b>"))
        inner_layout.addWidget(settings.native)

        # --- Run refinement + status ---
        self.submit_btn = widgets.PushButton(text='Run Refinement')
        self.submit_btn.clicked.connect(self._run_refinement)
        inner_layout.addWidget(self.submit_btn.native)

        # --- Accept an iteration (destructive: promotes one, removes the rest) ---
        inner_layout.addWidget(QLabel("<b>Accept Iteration</b>"))
        inner_layout.addWidget(QLabel(
            "Promote one iteration per component to be the working surface (originals\n"
            "are backed up). Inspect *_refinement_convergence.png first; IMM and OMM\n"
            "converge differently, so you can accept a different iteration for each."))
        # One step spinbox per component, rebuilt from the *_refined_iter* files.
        self.accept_container = widgets.Container(layout='vertical', labels=True)
        self.accept_container.native.layout().setSpacing(5)
        self.accept_container.native.layout().setContentsMargins(3, 3, 3, 3)
        inner_layout.addWidget(self.accept_container.native)
        self._component_steps = {}

        self.refresh_btn = QPushButton('Refresh Components')
        self.refresh_btn.clicked.connect(self._refresh_accept_components)
        inner_layout.addWidget(self.refresh_btn)

        # Preview the refined iterations in napari before the destructive accept.
        # The per-component spinbox above is the scrubber: the iteration it shows
        # is the one Accept promotes. Only available when a MeshViewer was wired in.
        if self.mesh_viewer is not None:
            inner_layout.addWidget(QLabel(
                "Preview loads each iteration (plus iter0, the original) as napari\n"
                "surfaces; scrub with the spinbox above — the shown iteration is\n"
                "the one Accept promotes."))
            self.preview_btn = QPushButton('Preview Iterations')
            self.preview_btn.clicked.connect(self._preview_iterations)
            inner_layout.addWidget(self.preview_btn)
            self.clear_preview_btn = QPushButton('Clear Preview')
            self.clear_preview_btn.clicked.connect(self._clear_preview)
            inner_layout.addWidget(self.clear_preview_btn)
        else:
            self.preview_btn = None
            self.clear_preview_btn = None

        self.accept_btn = QPushButton('Accept Iterations')
        self.accept_btn.clicked.connect(self._accept_iteration)
        inner_layout.addWidget(self.accept_btn)

        self.status = JobStatusWidget()
        inner_layout.addWidget(self.status.native)
        inner_layout.addStretch(1)

        if hasattr(self.experiment_manager, 'config_loaded'):
            self.experiment_manager.config_loaded.connect(self._on_config_loaded)
            if self.experiment_manager.current_config:
                self._on_config_loaded()

    def _on_config_loaded(self):
        try:
            self.status.update_status('Ready')
            self.status.update_progress(0)
            config = self.experiment_manager.current_config or {}
            if config.get('tomo_dir'):
                self.tomo_dir_input.value = config['tomo_dir']
            refine = config.get('mesh_refinement', {}) or {}
            self.iterations_input.value = refine.get('iterations', 6)
            self.damping_input.value = refine.get('damping_factor', 0.9)
            density = config.get('density_sampling', config.get('thickness_measurements', {}))
            self.average_radius_input.value = refine.get(
                'average_radius', density.get('average_radius', 25))
            self.max_offset_input.value = refine.get('max_total_offset', 8)
            xcorr = refine.get('xcorr_iterations', 3)
            # Config may carry a list of iteration numbers; the GUI exposes the
            # "first N" form, so collapse a contiguous-from-1 list to its length.
            self.xcorr_iterations_input.value = (
                len(xcorr) if isinstance(xcorr, (list, tuple)) else (xcorr or 0))
            self.monolayer_input.value = refine.get('monolayer', False)
            self.smooth_offsets_input.value = refine.get('smooth_offsets', True)
            self.laplacian_input.value = refine.get('laplacian_iterations', 5)
            self.laplacian_lambda_input.value = refine.get('laplacian_lambda', 0.5)
            self.lowpass_input.value = refine.get('lowpass_sigma', 0)
            self._refresh_accept_components()
        except Exception as e:
            print(f"[RefinementWidget] Error in _on_config_loaded: {e}")

    def _config_path(self):
        exp_name = self.experiment_manager.experiment_name.currentText()
        exp_dir = Path(self.experiment_manager.work_dir.value) / exp_name
        preferred = exp_dir / f"{exp_name}_config.yml"
        fallback = exp_dir / 'config.yml'
        return (preferred if preferred.exists() else fallback), exp_dir

    def _radius_hit(self):
        config = self.experiment_manager.current_config or {}
        return config.get('curvature_measurements', {}).get('radius_hit', 9)

    def _update_config(self):
        """Write tomo_dir, work_dir and the mesh_refinement block into config.yml."""
        if not self.experiment_manager.current_config:
            raise ValueError("Experiment configuration not loaded.")

        config_path, exp_dir = self._config_path()

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
            existing = copy.deepcopy(self.experiment_manager.current_config)

        # Every step shares one output dir; the CLI concatenates work_dir +
        # basename, so it must end in a separator.
        out_dir = resolve_work_dir(exp_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        existing['work_dir'] = cli_work_dir(out_dir)
        existing['cores'] = self.experiment_manager.cores_input.value()

        tomo_dir = str(self.tomo_dir_input.value)
        existing['tomo_dir'] = tomo_dir + os.sep if not tomo_dir.endswith(os.sep) else tomo_dir

        existing.setdefault('mesh_refinement', {})
        existing['mesh_refinement'].update({
            'iterations': self.iterations_input.value,
            'damping_factor': self.damping_input.value,
            'average_radius': self.average_radius_input.value,
            'max_total_offset': self.max_offset_input.value,
            # Config accepts "first N iterations" as an int.
            'xcorr_iterations': self.xcorr_iterations_input.value,
            'monolayer': self.monolayer_input.value,
            'smooth_offsets': self.smooth_offsets_input.value,
            'laplacian_iterations': self.laplacian_input.value,
            'laplacian_lambda': self.laplacian_lambda_input.value,
            'lowpass_sigma': self.lowpass_input.value,
        })

        with open(config_path, 'w') as f:
            yaml.dump(existing, f)

        return config_path

    # ----- Run refinement -----

    def _run_refinement(self):
        if self.is_running:
            return

        tomo_dir = str(self.tomo_dir_input.value or '')
        if not tomo_dir or not Path(tomo_dir).is_dir():
            QMessageBox.warning(self, "No Tomogram Directory",
                                "Select the directory containing the raw tomogram MRC files.")
            return
        if not list(Path(tomo_dir).glob('*.mrc')):
            QMessageBox.warning(self, "No Tomograms", f"No .mrc files found in {tomo_dir}.")
            return

        config_path, exp_dir = self._config_path()
        work_dir = resolve_work_dir(exp_dir)
        radius_hit = self._radius_hit()
        if not list(work_dir.glob(f'*.AVV_rh{radius_hit}.gt')):
            QMessageBox.warning(
                self, "No Curvature Graphs",
                f"No pycurv graphs (*.AVV_rh{radius_hit}.gt) found in {work_dir}.\n"
                "Run the Curvature step before refining the mesh.")
            return

        try:
            config_path = self._update_config()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update config: {e}")
            return

        runner = resolve_cli_runner()
        if runner is None:
            QMessageBox.critical(self, "morphometrics CLI not found", CLI_MISSING_MESSAGE)
            print(f"[Error] {CLI_MISSING_MESSAGE}")
            return

        # Archive prior refinement outputs only; never touch the canonical
        # pycurv graphs/surfaces that refinement reads from.
        try:
            if not check_and_archive_outputs(
                self, work_dir, config_path=config_path,
                file_patterns=REFINE_OUTPUT_PATTERNS,
            ):
                print("User cancelled.")
                return
        except Exception as e:
            print(f"Archive check failed: {e}")

        job_data = {
            'runner': runner,
            'config_path': config_path,
            'iterations': self.iterations_input.value,
        }
        self.is_running = True
        self.submit_btn.enabled = False
        self.accept_btn.setEnabled(False)
        if self.preview_btn is not None:
            self.preview_btn.setEnabled(False)
        self.status.update_status('Starting...')
        self.status.update_progress(0)
        threading.Thread(target=self._run_refinement_worker, args=(job_data,), daemon=True).start()

    def _run_refinement_worker(self, job_data):
        try:
            runner = job_data['runner']
            config_path = job_data['config_path']
            iterations = max(1, job_data['iterations'])
            work_dir = resolve_work_dir(Path(config_path).parent).resolve()

            cmd = runner + [REFINE_MESH, str(config_path)]
            print(f"--- Refining mesh: {' '.join(map(str, cmd))} ---")
            self.status.update_status('Refining mesh...')
            self.status.update_progress(5)

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                cmd, cwd=work_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, universal_newlines=True, env=env,
            )
            if process.stdout is not None:
                for line in process.stdout:
                    line = line.rstrip()
                    if not line:
                        continue
                    print(line)
                    # refine_mesh prints "=== Iteration N/M ===" per iteration.
                    if "=== Iteration" in line:
                        try:
                            n = int(line.split("Iteration", 1)[1].split("/", 1)[0])
                            self.status.update_status(f'Iteration {n}/{iterations}...')
                            self.status.update_progress(min(95, int(95 * n / iterations)))
                        except (ValueError, IndexError):
                            pass
            return_code = process.wait()

            if return_code != 0:
                self.status.update_status('Error: refinement failed. See terminal.')
                print("[ERROR] refine_mesh failed. Check the terminal output.")
                return

            if not list(work_dir.glob('*_refined_iter*.surface.vtp')):
                self.status.update_status('Error: no refined surfaces produced.')
                print("[ERROR] refine_mesh produced no *_refined_iter*.surface.vtp. "
                      "Check that pycurv graphs (.gt) and tomogram basenames match.")
                return

            self.status.update_progress(100)
            self.status.update_status(
                'Refinement complete. Inspect *_refinement_convergence.png, then accept an iteration.')
            print("===== Mesh refinement complete. =====")
            QTimer.singleShot(0, self._refresh_accept_components)

        except Exception as e:
            self.status.update_status(f'Error: {e}')
            print(f"A critical error occurred in the refinement worker: {e}")
            import traceback
            traceback.print_exc()
        finally:
            QTimer.singleShot(0, self._job_cleanup)

    # ----- Accept an iteration -----

    def _discover_refined_components(self, work_dir):
        """Map component name -> sorted list of available iteration numbers.

        Refined surfaces are named ``{tomo}_..._{component}_refined_iter{N}.surface.vtp``;
        the component is the token immediately before ``_refined_iter``. Iterations
        are aggregated across tomograms so a component's spinbox covers every N seen.
        """
        pat = re.compile(r'^(?P<base>.+)_refined_iter(?P<n>\d+)\.surface\.vtp$')
        components = {}
        for p in work_dir.glob('*_refined_iter*.surface.vtp'):
            m = pat.match(p.name)
            if not m:
                continue
            component = m.group('base').rsplit('_', 1)[-1]
            components.setdefault(component, set()).add(int(m.group('n')))
        return {c: sorted(v) for c, v in sorted(components.items())}

    def _refresh_accept_components(self):
        """Rebuild the per-component step spinboxes from the refined files on disk."""
        # Preserve current selections across a refresh so a rescan doesn't reset them.
        prev = {c: sb.value for c, sb in self._component_steps.items()}
        # The file set is about to change (refine/accept just ran); drop stale
        # preview layers so they can't outlive the iterations they represent.
        self._clear_preview()
        self.accept_container.clear()
        self._component_steps = {}

        try:
            _, exp_dir = self._config_path()
            work_dir = resolve_work_dir(exp_dir)
        except Exception:
            work_dir = None

        found = self._discover_refined_components(work_dir) if work_dir else {}
        if not found:
            self.accept_container.append(widgets.Label(
                value='No refined iterations found. Run refinement, then Refresh.'))
            self.accept_btn.setEnabled(False)
            if self.preview_btn is not None:
                self.preview_btn.setEnabled(False)
            return

        for component, iters in found.items():
            lo, hi = iters[0], iters[-1]
            # Default to the final iteration (usually the converged one); keep the
            # user's prior pick if it's still in range.
            default = min(max(prev.get(component, hi), lo), hi)
            sb = widgets.SpinBox(value=default, min=lo, max=hi,
                                 label=f'{component}  (iters {lo}-{hi})')
            # Scrubber: when a preview is loaded, changing the step shows that
            # iteration's layer and hides the rest for this component.
            sb.changed.connect(lambda _=None, c=component: self._on_step_changed(c))
            self.accept_container.append(sb)
            self._component_steps[component] = sb
        self.accept_btn.setEnabled(not self.is_running)
        if self.preview_btn is not None:
            self.preview_btn.setEnabled(not self.is_running)

    # ----- Preview iterations in napari -----

    def _preview_iterations(self):
        """Load every refined iteration (plus iter0 = the original surface) into
        napari as surface layers, showing only the spinbox-selected iteration per
        component. The accept spinbox then scrubs iterations via visibility."""
        if self.mesh_viewer is None or not self._component_steps:
            return

        self._clear_preview()

        try:
            _, exp_dir = self._config_path()
            work_dir = resolve_work_dir(exp_dir)
        except Exception as e:
            QMessageBox.warning(self, "Preview Failed", f"Could not resolve work dir: {e}")
            return

        pat = re.compile(r'^(?P<base>.+)_refined_iter(?P<n>\d+)\.surface\.vtp$')
        loaded = 0
        for component in self._component_steps:
            # (base, iter_n, path) for this component across all tomogram basenames.
            files = []
            bases = set()
            for p in sorted(work_dir.glob(f'*_{component}_refined_iter*.surface.vtp')):
                m = pat.match(p.name)
                if not m:
                    continue
                files.append((m.group('base'), int(m.group('n')), p))
                bases.add(m.group('base'))
            # iter0 = the still-canonical original surface for each base.
            for base in sorted(bases):
                orig = work_dir / f'{base}.surface.vtp'
                if orig.exists():
                    files.append((base, 0, orig))

            multi_base = len(bases) > 1
            for base, n, path in files:
                suffix = f':{base}' if multi_base else ''
                name = f'refine-preview:{component}:iter{n}{suffix}'
                layer = self._add_preview_layer(str(path), name)
                if layer is not None:
                    self._preview_layers.append((component, n, layer))
                    loaded += 1

        if not loaded:
            QMessageBox.information(
                self, "Nothing to Preview",
                "No refined iteration surfaces were found for the current components.")
            return

        for component, sb in self._component_steps.items():
            self._on_step_changed(component)
        self.mesh_viewer.viewer.reset_view()

    def _add_preview_layer(self, path, name):
        """Load a .vtp as a flat gray preview surface and return the layer.

        Loaded flat (no per-vertex scalar coloring) so previews show shape, not
        the noisy scalar arrays some refined surfaces carry."""
        try:
            return self.mesh_viewer._load_mesh_file(path, name=name, flat=True)
        except Exception as e:
            print(f"[RefinementWidget] Failed to preview {path}: {e}")
            return None

    def _on_step_changed(self, component):
        """Show only the selected iteration's layer(s) for this component."""
        sb = self._component_steps.get(component)
        if sb is None or not self._preview_layers:
            return
        target = sb.value
        for comp, n, layer in self._preview_layers:
            if comp == component:
                try:
                    layer.visible = (n == target)
                except Exception:
                    pass

    def _clear_preview(self):
        """Remove all preview layers we created from the napari viewer."""
        if self.mesh_viewer is None:
            self._preview_layers = []
            return
        layers = self.mesh_viewer.viewer.layers
        for _comp, _n, layer in self._preview_layers:
            try:
                if layer in layers:
                    layers.remove(layer)
            except Exception:
                pass
        self._preview_layers = []

    def _accept_iteration(self):
        if self.is_running:
            return

        if not self.experiment_manager.current_config:
            QMessageBox.warning(self, "No Experiment", "Load an experiment first.")
            return

        config_path, exp_dir = self._config_path()
        if not config_path.exists():
            QMessageBox.warning(self, "No Config", f"Config not found: {config_path}")
            return

        if not self._component_steps:
            QMessageBox.warning(self, "No Components",
                                "No refined components found. Run refinement, then Refresh.")
            return

        work_dir = resolve_work_dir(exp_dir)
        choices = {c: sb.value for c, sb in self._component_steps.items()}
        # Validate each chosen iteration exists for its component before touching files.
        missing = [f"{c}: iteration {s}" for c, s in choices.items()
                   if not list(work_dir.glob(f'*_{c}_refined_iter{s}.surface.vtp'))]
        if missing:
            QMessageBox.warning(
                self, "No Such Iteration",
                "These selections have no refined surface:\n  " + "\n  ".join(missing))
            return

        summary = "\n".join(f"  {c}: iteration {s}" for c, s in choices.items())
        confirm = QMessageBox.question(
            self, "Accept Iterations",
            f"Promote these iterations to be the working surfaces?\n\n{summary}\n\n"
            "Originals are backed up (*.orig.bak), but the other refinement "
            "iterations and intermediates will be removed. This cannot be undone "
            "from the GUI.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return

        runner = resolve_cli_runner()
        if runner is None:
            QMessageBox.critical(self, "morphometrics CLI not found", CLI_MISSING_MESSAGE)
            return

        job_data = {'runner': runner, 'config_path': config_path, 'choices': choices}
        self.is_running = True
        self.submit_btn.enabled = False
        self.accept_btn.setEnabled(False)
        if self.preview_btn is not None:
            self.preview_btn.setEnabled(False)
        self.status.update_status('Accepting iterations...')
        threading.Thread(target=self._accept_worker, args=(job_data,), daemon=True).start()

    def _accept_worker(self, job_data):
        try:
            runner = job_data['runner']
            config_path = job_data['config_path']
            choices = job_data['choices']
            work_dir = resolve_work_dir(Path(config_path).parent).resolve()

            # One accept_refinement call per component. accept_one's cleanup globs
            # {basename}_refined_iter*, scoped to the accepted basename, so accepting
            # one component never deletes another's iterations — order is irrelevant.
            failed = []
            for component, step in choices.items():
                cmd = runner + [ACCEPT_REFINEMENT, str(config_path), str(step),
                                '--component', component]
                print(f"--- Accepting refinement: {' '.join(map(str, cmd))} ---")
                try:
                    subprocess.run(cmd, cwd=work_dir, check=True, text=True)
                except subprocess.CalledProcessError:
                    failed.append(component)
                    print(f"[ERROR] accept_refinement failed for {component}.")

            if failed:
                self.status.update_status(
                    f"Error accepting: {', '.join(failed)}. See terminal.")
            else:
                accepted = ", ".join(f"{c}={s}" for c, s in choices.items())
                self.status.update_status(
                    f'Accepted {accepted}. If any was a lightweight (xcorr) iteration, '
                    're-run Curvature before distances.')
                print(f"===== Accepted refinement: {accepted}. =====")

        except Exception as e:
            self.status.update_status(f'Error: {e}')
            print(f"A critical error occurred while accepting refinement: {e}")
            import traceback
            traceback.print_exc()
        finally:
            QTimer.singleShot(0, self._refresh_accept_components)
            QTimer.singleShot(0, self._job_cleanup)

    def _job_cleanup(self):
        self.submit_btn.enabled = True
        self.accept_btn.setEnabled(bool(self._component_steps))
        if self.preview_btn is not None:
            self.preview_btn.setEnabled(bool(self._component_steps))
        self.is_running = False
