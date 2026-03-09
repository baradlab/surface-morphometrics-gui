"""Tests for JobStatusWidget."""
import pytest
from widgets.job_status import JobStatusWidget


@pytest.mark.gui
class TestJobStatusWidget:
    def test_creation(self, qapp):
        w = JobStatusWidget()
        assert w.status_label.value == "Status: Not Started"
        assert w.progress.value() == 0

    def test_update_status(self, qapp):
        w = JobStatusWidget()
        w._update_status_safe("Running")
        assert "Running" in w.status_label.value

    def test_update_progress(self, qapp):
        w = JobStatusWidget()
        w._update_progress_safe(50)
        assert w.progress.value() == 50

    def test_progress_bounds_low(self, qapp):
        w = JobStatusWidget()
        w._update_progress_safe(0)
        assert w.progress.value() == 0

    def test_progress_bounds_high(self, qapp):
        w = JobStatusWidget()
        w._update_progress_safe(100)
        assert w.progress.value() == 100

    def test_has_clear_method_after_fix(self, qapp):
        """Bug #1 regression: seg_to_mesh.py calls self.status.clear().
        After fix, JobStatusWidget should have clear() and append_output() methods."""
        w = JobStatusWidget()
        assert hasattr(w, "clear"), "JobStatusWidget must have clear() method (bug #1 fix)"
        assert hasattr(w, "append_output"), "JobStatusWidget must have append_output() method (bug #1 fix)"
