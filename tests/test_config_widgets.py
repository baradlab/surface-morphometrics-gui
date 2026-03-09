"""Tests for IntraListEditor and InterDictEditor widgets."""
import pytest
from morphometrics_config import IntraListEditor, InterDictEditor


@pytest.mark.gui
class TestIntraListEditor:
    def test_creation(self, qapp):
        editor = IntraListEditor()
        assert editor.get_values() == []

    def test_set_and_get_values(self, qapp):
        editor = IntraListEditor()
        editor.set_values(["ER", "PM"])
        assert editor.get_values() == ["ER", "PM"]

    def test_clear_values(self, qapp):
        editor = IntraListEditor()
        editor.set_values(["ER", "PM"])
        editor.set_values([])
        assert editor.get_values() == []

    def test_add_entry(self, qapp):
        editor = IntraListEditor()
        editor._add_entry("test")
        assert "test" in editor.get_values()

    def test_empty_entries_filtered(self, qapp):
        editor = IntraListEditor()
        editor._add_entry("")
        editor._add_entry("valid")
        assert editor.get_values() == ["valid"]


@pytest.mark.gui
class TestInterDictEditor:
    def test_creation(self, qapp):
        editor = InterDictEditor()
        assert editor.get_values() == {}

    def test_set_and_get_values(self, qapp):
        editor = InterDictEditor()
        editor.set_values({"PM": ["ER"]})
        result = editor.get_values()
        assert "PM" in result
        assert result["PM"] == ["ER"]

    def test_clear_values(self, qapp):
        editor = InterDictEditor()
        editor.set_values({"PM": ["ER"]})
        editor.set_values({})
        assert editor.get_values() == {}

    def test_empty_key_filtered(self, qapp):
        editor = InterDictEditor()
        editor._add_entry("", ["ER"])
        editor._add_entry("PM", ["ER"])
        result = editor.get_values()
        assert "" not in result
        assert "PM" in result
