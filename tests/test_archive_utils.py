"""Tests for check_and_archive_outputs utility."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestCheckAndArchiveOutputs:
    def test_empty_dir_returns_true(self, tmp_path):
        """Empty results dir should return True (safe to proceed)."""
        from utils.archive_utils import check_and_archive_outputs
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        assert check_and_archive_outputs(None, results_dir, config_path=None) is True

    def test_nonexistent_dir_returns_true(self, tmp_path):
        """Non-existent results dir should return True."""
        from utils.archive_utils import check_and_archive_outputs
        results_dir = tmp_path / "nonexistent"
        assert check_and_archive_outputs(None, results_dir, config_path=None) is True

    def test_hidden_files_ignored(self, tmp_path):
        """Files starting with . should be ignored."""
        from utils.archive_utils import check_and_archive_outputs
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / ".hidden").write_text("hidden")
        assert check_and_archive_outputs(None, results_dir, config_path=None) is True

    def test_pattern_matching(self, tmp_path):
        """Only files matching specified patterns should trigger prompt."""
        from utils.archive_utils import check_and_archive_outputs
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "data.csv").write_text("data")
        (results_dir / "image.png").write_text("data")

        # Mock the QMessageBox to simulate cancel
        with patch("utils.archive_utils.QMessageBox") as mock_mb:
            instance = MagicMock()
            mock_mb.return_value = instance
            mock_mb.Cancel = "cancel"
            cancel_btn = MagicMock()
            instance.addButton.side_effect = [MagicMock(), MagicMock(), cancel_btn]
            instance.clickedButton.return_value = cancel_btn
            result = check_and_archive_outputs(
                MagicMock(), results_dir, config_path=None, file_patterns=["*.csv"]
            )
            assert result is False  # cancelled

    def test_exclude_patterns(self, tmp_path):
        """Files matching exclude patterns should not trigger prompt."""
        from utils.archive_utils import check_and_archive_outputs
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "data_AVV_results.csv").write_text("data")
        # Only AVV file, which is excluded
        assert check_and_archive_outputs(
            None, results_dir, config_path=None,
            file_patterns=["*.csv"], exclude_patterns=["*AVV*"]
        ) is True

    def test_distance_excludes_refinement_artifacts(self, tmp_path):
        """The distance step must not treat mesh-refinement outputs (which
        share the results/ dir) as prior distance results."""
        from utils.archive_utils import check_and_archive_outputs
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        # Artifacts left in results/ by the refinement step
        for name in [
            "T_IMM_refinement_convergence.png",
            "T_OMM_refinement_convergence.png",
            "T_IMM_profile_evolution.png",
            "T_IMM_refinement_stats.csv",
            "T_OMM_refinement_stats.csv",
            "T_IMM_profile_iter3.png",
            "T_IMM_samples_iter3.png",
            "T_IMM_refined_iter1.lightweight_sampling.csv",
        ]:
            (results_dir / name).write_text("x")

        # Same patterns/excludes as distance_tab.py
        refinement_excludes = [
            "*_refinement_*", "*_profile_evolution*",
            "*_profile_iter*", "*_samples_iter*", "*lightweight*",
        ]
        assert check_and_archive_outputs(
            None, results_dir, config_path=None,
            file_patterns=["*.csv", "*.svg", "*.png"],
            exclude_patterns=["*AVV*", "*VV*", "*.gt", "*_runtimes.csv"] + refinement_excludes,
        ) is True

    def test_distance_still_detects_real_outputs(self, tmp_path):
        """A genuine distance-measurement CSV must still trigger the prompt."""
        from utils.archive_utils import check_and_archive_outputs
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "T_refinement_stats.csv").write_text("x")  # excluded
        (results_dir / "T_IMM_OMM_distances.csv").write_text("x")  # real output

        refinement_excludes = [
            "*_refinement_*", "*_profile_evolution*",
            "*_profile_iter*", "*_samples_iter*", "*lightweight*",
        ]
        with patch("utils.archive_utils.QMessageBox") as mock_mb:
            instance = MagicMock()
            mock_mb.return_value = instance
            mock_mb.Cancel = "cancel"
            cancel_btn = MagicMock()
            instance.addButton.side_effect = [MagicMock(), MagicMock(), cancel_btn]
            instance.clickedButton.return_value = cancel_btn
            result = check_and_archive_outputs(
                MagicMock(), results_dir, config_path=None,
                file_patterns=["*.csv", "*.svg", "*.png"],
                exclude_patterns=["*AVV*", "*VV*", "*.gt", "*_runtimes.csv"] + refinement_excludes,
            )
            assert result is False  # prompt shown, user cancelled
