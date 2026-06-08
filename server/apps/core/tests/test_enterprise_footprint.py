"""
Pure pytest tests for enterprise footprint detection.
No Django app setup required.

The module is loaded directly by file path so that importing it never
triggers the config package __init__ (which would pull in Django settings
and other side effects during bare test collection).
"""
import importlib.util
import pathlib
import sys

import pytest

_MODULE_PATH = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "config" / "components" / "enterprise.py"  # server/
_spec = importlib.util.spec_from_file_location("enterprise_footprint", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["enterprise_footprint"] = _mod  # register before exec so @dataclass resolves __module__
_spec.loader.exec_module(_mod)

EnterpriseFootprintError = _mod.EnterpriseFootprintError
EnterpriseFootprintStatus = _mod.EnterpriseFootprintStatus
detect_enterprise_footprint = _mod.detect_enterprise_footprint
require_enterprise_license_management = _mod.require_enterprise_license_management

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_apps(tmp_path, layout):
    """
    layout: dict mapping app_name -> list of relative file paths inside
    the app dir.  Paths are created as empty files.
    Also creates apps/__init__.py so the apps dir exists properly.
    Returns the tmp_path (acts as base_dir).
    """
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    (apps_dir / "__init__.py").write_text("")
    for app_name, files in layout.items():
        app_dir = apps_dir / app_name
        app_dir.mkdir()
        for rel in files:
            target = app_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("")
    return tmp_path


# ---------------------------------------------------------------------------
# detect_enterprise_footprint
# ---------------------------------------------------------------------------


class TestDetectEnterpriseFootprint:
    def test_returns_status_dataclass(self, tmp_path):
        base = _make_apps(tmp_path, {})
        result = detect_enterprise_footprint(base_dir=base)
        assert isinstance(result, EnterpriseFootprintStatus)

    def test_no_enterprise_dirs_is_community(self, tmp_path):
        base = _make_apps(tmp_path, {"myapp": []})
        result = detect_enterprise_footprint(base_dir=base)
        assert result.enterprise_apps == []
        assert not result.has_enterprise_footprint

    def test_init_only_enterprise_dir_is_community(self, tmp_path):
        base = _make_apps(
            tmp_path,
            {"console_mgmt": ["enterprise/__init__.py"]},
        )
        result = detect_enterprise_footprint(base_dir=base)
        assert result.enterprise_apps == []
        assert not result.has_enterprise_footprint

    def test_python_file_triggers_footprint(self, tmp_path):
        base = _make_apps(
            tmp_path,
            {"core": ["enterprise/__init__.py", "enterprise/license_filter.py"]},
        )
        result = detect_enterprise_footprint(base_dir=base)
        assert "core" in result.enterprise_apps
        assert result.has_enterprise_footprint

    def test_resource_file_triggers_footprint(self, tmp_path):
        """Non-Python resource files (e.g. JSON, support-files) count."""
        base = _make_apps(
            tmp_path,
            {
                "monitor": [
                    "enterprise/__init__.py",
                    "enterprise/support-files/plugins/my_plugin.json",
                ]
            },
        )
        result = detect_enterprise_footprint(base_dir=base)
        assert "monitor" in result.enterprise_apps

    def test_multiple_apps_with_footprint(self, tmp_path):
        base = _make_apps(
            tmp_path,
            {
                "core": ["enterprise/license_filter.py"],
                "system_mgmt": ["enterprise/urls.py"],
                "console_mgmt": ["enterprise/__init__.py"],
            },
        )
        result = detect_enterprise_footprint(base_dir=base)
        assert set(result.enterprise_apps) == {"core", "system_mgmt"}

    def test_hidden_files_ignored(self, tmp_path):
        base = _make_apps(
            tmp_path,
            {"myapp": ["enterprise/__init__.py", "enterprise/.hidden_file"]},
        )
        result = detect_enterprise_footprint(base_dir=base)
        assert result.enterprise_apps == []

    def test_pycache_ignored(self, tmp_path):
        base = _make_apps(
            tmp_path,
            {
                "myapp": [
                    "enterprise/__init__.py",
                    "enterprise/__pycache__/something.pyc",
                ]
            },
        )
        result = detect_enterprise_footprint(base_dir=base)
        assert result.enterprise_apps == []

    def test_license_mgmt_present_true_when_dir_exists(self, tmp_path):
        base = _make_apps(tmp_path, {"license_mgmt": ["__init__.py"]})
        result = detect_enterprise_footprint(base_dir=base)
        assert result.license_mgmt_present is True

    def test_license_mgmt_present_false_when_missing(self, tmp_path):
        base = _make_apps(tmp_path, {})
        result = detect_enterprise_footprint(base_dir=base)
        assert result.license_mgmt_present is False

    def test_should_enable_license_mgmt_true_when_footprint_and_license_present(self, tmp_path):
        base = _make_apps(
            tmp_path,
            {
                "core": ["enterprise/license_filter.py"],
                "license_mgmt": ["__init__.py"],
            },
        )
        result = detect_enterprise_footprint(base_dir=base)
        assert result.should_enable_license_mgmt is True

    def test_should_enable_license_mgmt_false_when_no_footprint(self, tmp_path):
        base = _make_apps(
            tmp_path,
            {"license_mgmt": ["__init__.py"]},
        )
        result = detect_enterprise_footprint(base_dir=base)
        assert result.should_enable_license_mgmt is False

    def test_should_enable_license_mgmt_false_when_no_license_mgmt(self, tmp_path):
        base = _make_apps(
            tmp_path,
            {"core": ["enterprise/license_filter.py"]},
        )
        result = detect_enterprise_footprint(base_dir=base)
        assert result.should_enable_license_mgmt is False


# ---------------------------------------------------------------------------
# require_enterprise_license_management
# ---------------------------------------------------------------------------


class TestRequireEnterpriseLicenseManagement:
    def test_no_footprint_no_error(self, tmp_path):
        base = _make_apps(tmp_path, {"console_mgmt": ["enterprise/__init__.py"]})
        # should not raise
        require_enterprise_license_management(base_dir=base)

    def test_footprint_and_license_mgmt_no_error(self, tmp_path):
        base = _make_apps(
            tmp_path,
            {
                "core": ["enterprise/license_filter.py"],
                "license_mgmt": ["__init__.py"],
            },
        )
        require_enterprise_license_management(base_dir=base)

    def test_footprint_without_license_mgmt_raises(self, tmp_path):
        base = _make_apps(
            tmp_path,
            {"core": ["enterprise/license_filter.py"]},
        )
        with pytest.raises(EnterpriseFootprintError) as exc_info:
            require_enterprise_license_management(base_dir=base)
        assert "core" in str(exc_info.value)
        assert "license_mgmt" in str(exc_info.value)

    def test_error_message_lists_all_enterprise_apps(self, tmp_path):
        base = _make_apps(
            tmp_path,
            {
                "core": ["enterprise/license_filter.py"],
                "system_mgmt": ["enterprise/urls.py"],
            },
        )
        with pytest.raises(EnterpriseFootprintError) as exc_info:
            require_enterprise_license_management(base_dir=base)
        msg = str(exc_info.value)
        assert "core" in msg
        assert "system_mgmt" in msg

    def test_raises_runtime_error_subclass(self, tmp_path):
        base = _make_apps(
            tmp_path,
            {"core": ["enterprise/license_filter.py"]},
        )
        with pytest.raises(RuntimeError):
            require_enterprise_license_management(base_dir=base)
