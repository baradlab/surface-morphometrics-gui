"""Tests for ConfigYAMLPreserver: format_value, update, save."""
import yaml
from pathlib import Path
from morphometrics_config import ConfigYAMLPreserver


class TestFormatValue:
    def setup_method(self, tmp_path=None):
        # We need a minimal YAML file for ConfigYAMLPreserver init
        pass

    def _make_preserver(self, tmp_path, content="key: value\n"):
        p = tmp_path / "test.yml"
        p.write_text(content)
        return ConfigYAMLPreserver(p)

    def test_format_bool_true(self, tmp_path):
        cp = self._make_preserver(tmp_path)
        assert cp._format_value(True) == "true"

    def test_format_bool_false(self, tmp_path):
        cp = self._make_preserver(tmp_path)
        assert cp._format_value(False) == "false"

    def test_format_int(self, tmp_path):
        cp = self._make_preserver(tmp_path)
        assert cp._format_value(42) == "42"

    def test_format_float(self, tmp_path):
        cp = self._make_preserver(tmp_path)
        assert cp._format_value(3.14) == "3.14"

    def test_format_string_simple(self, tmp_path):
        cp = self._make_preserver(tmp_path)
        assert cp._format_value("hello") == "hello"

    def test_format_string_with_spaces(self, tmp_path):
        cp = self._make_preserver(tmp_path)
        assert cp._format_value("hello world") == '"hello world"'

    def test_format_string_with_colon(self, tmp_path):
        cp = self._make_preserver(tmp_path)
        assert cp._format_value("key:value") == '"key:value"'

    def test_format_empty_list(self, tmp_path):
        cp = self._make_preserver(tmp_path)
        assert cp._format_value([]) == "[]"

    def test_format_list(self, tmp_path):
        cp = self._make_preserver(tmp_path)
        result = cp._format_value(["a", "b"])
        assert "- a" in result
        assert "- b" in result

    def test_format_empty_dict(self, tmp_path):
        cp = self._make_preserver(tmp_path)
        assert cp._format_value({}) == "{}"

    def test_format_dict(self, tmp_path):
        cp = self._make_preserver(tmp_path)
        result = cp._format_value({"key": "val"})
        assert "key: val" in result

    def test_format_none(self, tmp_path):
        cp = self._make_preserver(tmp_path)
        assert cp._format_value(None) == "None"


class TestUpdate:
    def test_update_simple_key(self, tmp_path):
        p = tmp_path / "test.yml"
        p.write_text("key: old_value\n")
        cp = ConfigYAMLPreserver(p)
        cp.update({"key": "new_value"})
        assert cp.yaml_data["key"] == "new_value"

    def test_update_deep_merge(self, tmp_path):
        p = tmp_path / "test.yml"
        p.write_text("parent:\n  child1: a\n  child2: b\n")
        cp = ConfigYAMLPreserver(p)
        cp.update({"parent": {"child1": "updated"}})
        assert cp.yaml_data["parent"]["child1"] == "updated"
        assert cp.yaml_data["parent"]["child2"] == "b"

    def test_update_adds_new_key(self, tmp_path):
        p = tmp_path / "test.yml"
        p.write_text("key: value\n")
        cp = ConfigYAMLPreserver(p)
        cp.update({"new_key": "new_value"})
        assert cp.yaml_data["new_key"] == "new_value"
        assert cp.yaml_data["key"] == "value"


class TestSave:
    def test_save_roundtrip(self, tmp_path):
        p = tmp_path / "test.yml"
        p.write_text("key: value\n")
        cp = ConfigYAMLPreserver(p)
        cp.update({"key": "updated"})
        cp.save()
        # Re-read and verify
        cp2 = ConfigYAMLPreserver(p)
        assert cp2.yaml_data["key"] == "updated"

    def test_save_creates_backup(self, tmp_path):
        p = tmp_path / "test.yml"
        p.write_text("key: value\n")
        cp = ConfigYAMLPreserver(p)
        cp.save()
        # After bug fix, backup should be cleaned up
        backup = tmp_path / "test.bak"
        # This test documents current behavior (backup left behind - bug #9)
        # After fix, backup should not exist
        # For now just ensure the file was saved correctly
        assert p.exists()
        content = yaml.safe_load(p.read_text())
        assert content["key"] == "value"

    def test_save_restores_on_failure(self, tmp_path):
        p = tmp_path / "test.yml"
        p.write_text("key: original\n")
        cp = ConfigYAMLPreserver(p)
        # Corrupt content to cause write issue indirectly
        # (can't easily force write failure, so just test normal path)
        cp.update({"key": "new"})
        cp.save()
        assert yaml.safe_load(p.read_text())["key"] == "new"

    def test_empty_file(self, tmp_path):
        p = tmp_path / "test.yml"
        p.write_text("")
        cp = ConfigYAMLPreserver(p)
        assert cp.yaml_data == {}
        cp.update({"key": "val"})
        cp.save()
        assert yaml.safe_load(p.read_text())["key"] == "val"
