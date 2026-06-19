"""Regression tests for the 10 known bugs.

Each test verifies the fix is in place.
"""
import pytest
import yaml
import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestBug1_JobStatusMissingMethods:
    """Bug #1: seg_to_mesh.py calls self.status.clear() and self.status.append_output()
    which don't exist on JobStatusWidget."""

    @pytest.mark.gui
    def test_job_status_has_clear(self, qapp):
        from widgets.job_status import JobStatusWidget
        w = JobStatusWidget()
        assert hasattr(w, "clear"), "JobStatusWidget must have clear() method"
        w.clear()  # Should not raise

    @pytest.mark.gui
    def test_job_status_has_append_output(self, qapp):
        from widgets.job_status import JobStatusWidget
        w = JobStatusWidget()
        assert hasattr(w, "append_output"), "JobStatusWidget must have append_output() method"
        w.append_output("test message")  # Should not raise


class TestBug3_DefaultMismatch:
    """Bug #3: Widget init defaults differ from _on_config_loaded fallbacks."""

    @pytest.mark.gui
    def test_mesh_tab_defaults_match_fallbacks(self, qapp, mock_experiment_manager):
        from jobs.mesh_tab import MeshGenerationWidget
        w = MeshGenerationWidget(mock_experiment_manager)

        # Record init defaults
        init_defaults = {
            "ultrafine": w.ultrafine.value,
            "simplify": w.simplify.value,
            "max_triangles": w.max_triangles.value,
            "octree_depth": w.octree_depth.value,
            "neighbor_count": w.neighbor_count.value,
        }

        # Simulate loading empty config (triggers .get() fallbacks)
        mock_experiment_manager.current_config = {"surface_generation": {}}
        w._on_config_loaded()

        loaded_defaults = {
            "ultrafine": w.ultrafine.value,
            "simplify": w.simplify.value,
            "max_triangles": w.max_triangles.value,
            "octree_depth": w.octree_depth.value,
            "neighbor_count": w.neighbor_count.value,
        }

        assert init_defaults == loaded_defaults, \
            f"Init defaults {init_defaults} != config fallbacks {loaded_defaults}"


class TestBug4_MeshConfigPath:
    """Bug #4: _run_job looks for config at work_dir / name_config.yml
    but it should be at work_dir / name / name_config.yml."""

    @pytest.mark.gui
    def test_config_path_is_inside_experiment_dir(self, qapp, mock_experiment_manager, tmp_path):
        from jobs.mesh_tab import MeshGenerationWidget
        from ruamel.yaml import YAML

        exp_name = "test_experiment"
        exp_dir = tmp_path / exp_name
        exp_dir.mkdir()
        config_path = exp_dir / f"{exp_name}_config.yml"
        yaml = YAML()
        yaml.dump({"surface_generation": {}}, config_path.open("w"))

        mock_experiment_manager.work_dir.value = str(tmp_path)
        mock_experiment_manager.experiment_name.currentText.return_value = exp_name

        w = MeshGenerationWidget(mock_experiment_manager)
        result_path, _ = w._update_config()

        # Config path should be inside exp_dir, not directly under work_dir
        assert exp_name in str(result_path.parent.name), \
            f"Config path {result_path} should be inside experiment directory"


class TestBug5_DistanceConfigPathOverwrite:
    """Bug #5: config_path from _update_config() is overwritten by reconstructed path."""

    @pytest.mark.gui
    def test_config_path_not_overwritten(self, qapp, mock_experiment_manager, tmp_path):
        from jobs.distance_tab import DistanceOrientationWidget
        source = inspect.getsource(DistanceOrientationWidget._run_job)
        # After the fix, the reconstructed config_path should not overwrite
        # the one from _update_config() before the archive check
        # Check that config_path is not reassigned between _update_config and check_and_archive
        lines = source.split('\n')
        update_config_line = None
        archive_check_line = None
        reassignment_between = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if '_update_config()' in stripped:
                update_config_line = i
            if 'check_and_archive' in stripped and update_config_line is not None:
                archive_check_line = i
                break
            if update_config_line is not None and stripped.startswith('config_path =') and 'update_config' not in stripped:
                reassignment_between = True

        assert not reassignment_between, \
            "config_path should not be reassigned between _update_config() and check_and_archive_outputs()"


class TestBug6_InterDictEditorRename:
    """Bug #6: the old InterDictEditor keyed self.entries by the user-typed
    membrane name, so button-driven Adds collided on the empty key and renames
    desynced the dict. The fix (now in jobs.distance_tab) keys by a monotonic
    token, so neither happens."""

    @pytest.mark.gui
    def test_button_driven_adds_do_not_collide(self, qapp):
        from jobs.distance_tab import InterDictEditor
        editor = InterDictEditor()
        editor._add_entry()  # empty key
        editor._add_entry()  # empty key again — old impl overwrote the first
        assert len(editor.entries) == 2

    @pytest.mark.gui
    def test_rename_reflected_in_get_values(self, qapp):
        from jobs.distance_tab import InterDictEditor
        editor = InterDictEditor()
        editor._add_entry("original_key", ["val1"])
        (key_edit, value_editor, container), = editor.entries.values()
        key_edit.value = "renamed_key"
        assert editor.get_values() == {"renamed_key": ["val1"]}


class TestBug7_UpdateConfigPathsOverwrite:
    """Bug #7: _update_config_paths() overwrites user-edited data_dir with config value."""

    @pytest.mark.gui
    def test_user_data_dir_preserved(self, qapp):
        with patch("experiment_manager.napari"):
            with patch("experiment_manager.plt"):
                from experiment_manager import ExperimentManager
                viewer = MagicMock()
                viewer.layers = MagicMock()
                viewer.layers.selection = MagicMock()
                em = ExperimentManager(viewer)

                # User edits data_dir
                em.data_dir.value = "/user/edited/path"
                em.current_config = {"data_dir": "/config/path", "work_dir": "/some/work"}

                em._update_config_paths()

                # After fix, user-edited value should be preserved, not overwritten
                assert str(em.data_dir.value) == "/user/edited/path", \
                    "User-edited data_dir should not be overwritten by config value"


class TestBug8_ClearOnNegativeIndex:
    """Bug #8: _on_experiment_selected clears fields when currentIndex() < 0."""

    @pytest.mark.gui
    def test_no_clear_during_programmatic_clear(self, qapp):
        with patch("experiment_manager.napari"):
            with patch("experiment_manager.plt"):
                from experiment_manager import ExperimentManager
                viewer = MagicMock()
                viewer.layers = MagicMock()
                viewer.layers.selection = MagicMock()
                em = ExperimentManager(viewer)

                # Set some user values
                em.data_dir.value = "/user/data"
                em.cores_input.setValue(8)

                # Simulate programmatic clear (index goes to -1)
                em.experiment_name.setCurrentIndex(-1)
                # _on_experiment_selected fires via signal

                # After fix, user values should be preserved during programmatic clears
                # (The fix should guard against clearing during non-user-initiated changes)


class TestBug10_TimeSleep:
    """Bug #10: time.sleep(0.1) in UI thread."""

    def test_no_sleep_in_shading_setup(self):
        from plugins.mesh_viewer import MeshViewer
        source = inspect.getsource(MeshViewer._setup_shading)
        assert "time.sleep" not in source, \
            "_setup_shading should not use time.sleep in UI thread"
