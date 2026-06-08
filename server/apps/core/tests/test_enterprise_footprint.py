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
import types

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
# Settings stub — satisfies root-conftest autouse fixtures without Django
# ---------------------------------------------------------------------------


@pytest.fixture
def settings():
    """Lightweight stub that shadows pytest-django's ``settings`` fixture.

    The root conftest has two ``autouse=True`` fixtures that only do
    attribute assignments on the settings object (CACHES, MIDDLEWARE).
    A SimpleNamespace is sufficient; no Django runtime is needed.
    """
    return types.SimpleNamespace(CACHES={}, MIDDLEWARE=())


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


# ---------------------------------------------------------------------------
# app.py enterprise wiring
# ---------------------------------------------------------------------------

_APP_MODULE_PATH = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "config" / "components" / "app.py"


def _load_app(tmp_path, monkeypatch, install_apps="", debug=False):
    """Load config/components/app.py with BASE_DIR pointing to tmp_path.

    Mocks the two dependencies that would otherwise require a full Django
    environment: config.components.base and config.components.enterprise.
    The real enterprise functions from the already-loaded _mod are reused.
    """
    import types as _types

    # Mock config.components.base
    base_mock = _types.ModuleType("config.components.base")
    base_mock.BASE_DIR = tmp_path
    base_mock.DEBUG = debug
    monkeypatch.setitem(sys.modules, "config", _types.ModuleType("config"))
    monkeypatch.setitem(sys.modules, "config.components", _types.ModuleType("config.components"))
    monkeypatch.setitem(sys.modules, "config.components.base", base_mock)

    # Mock config.components.enterprise with real implementations
    ent_mock = _types.ModuleType("config.components.enterprise")
    ent_mock.require_enterprise_license_management = _mod.require_enterprise_license_management
    ent_mock.detect_enterprise_footprint = _mod.detect_enterprise_footprint
    monkeypatch.setitem(sys.modules, "config.components.enterprise", ent_mock)

    monkeypatch.setenv("INSTALL_APPS", install_apps)

    unique_name = f"_app_under_test_{id(tmp_path)}"
    spec = importlib.util.spec_from_file_location(unique_name, _APP_MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestAppPyEnterpriseWiring:
    def test_raises_when_footprint_without_license_mgmt(self, tmp_path, monkeypatch):
        """app.py must refuse to start when enterprise content exists but license_mgmt is absent."""
        _make_apps(tmp_path, {"core": ["enterprise/license_filter.py"]})
        with pytest.raises(EnterpriseFootprintError):
            _load_app(tmp_path, monkeypatch)

    def test_no_error_when_no_enterprise_footprint(self, tmp_path, monkeypatch):
        """Community edition without any enterprise content starts normally."""
        _make_apps(tmp_path, {"console_mgmt": ["enterprise/__init__.py"]})
        mod = _load_app(tmp_path, monkeypatch)
        assert "apps.license_mgmt" not in mod.INSTALLED_APPS

    def test_license_mgmt_in_installed_apps_when_footprint_and_license_present(self, tmp_path, monkeypatch):
        """apps.license_mgmt is added to INSTALLED_APPS when enterprise footprint and license_mgmt dir exist."""
        _make_apps(
            tmp_path,
            {
                "core": ["enterprise/license_filter.py"],
                "license_mgmt": ["__init__.py"],
            },
        )
        mod = _load_app(tmp_path, monkeypatch)
        assert "apps.license_mgmt" in mod.INSTALLED_APPS

    def test_license_mgmt_not_added_when_no_footprint(self, tmp_path, monkeypatch):
        """license_mgmt dir alone (no enterprise content) must NOT inject the license middleware."""
        _make_apps(tmp_path, {"license_mgmt": ["__init__.py"]})
        mod = _load_app(tmp_path, monkeypatch)
        license_middleware = [mw for mw in mod.MIDDLEWARE if "license_mgmt" in mw]
        assert license_middleware == [], f"Unexpected license middleware: {license_middleware}"


# ---------------------------------------------------------------------------
# extra.py enterprise wiring
# ---------------------------------------------------------------------------

_EXTRA_MODULE_PATH = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "config" / "components" / "extra.py"


def _load_extra(tmp_path, monkeypatch, install_apps=""):
    """Load config/components/extra.py with cwd set to tmp_path.

    extra.py uses Path.cwd() after wiring, so we change cwd to tmp_path.
    """
    import types as _types

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INSTALL_APPS", install_apps)

    # Provide config.components.enterprise with real implementations
    ent_mock = _types.ModuleType("config.components.enterprise")
    ent_mock.require_enterprise_license_management = _mod.require_enterprise_license_management
    ent_mock.detect_enterprise_footprint = _mod.detect_enterprise_footprint
    monkeypatch.setitem(sys.modules, "config.components.enterprise", ent_mock)

    unique_name = f"_extra_under_test_{id(tmp_path)}"
    spec = importlib.util.spec_from_file_location(unique_name, _EXTRA_MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestExtraPyEnterpriseWiring:
    def test_raises_when_footprint_without_license_mgmt(self, tmp_path, monkeypatch):
        """extra.py must refuse to start when enterprise content exists but license_mgmt is absent."""
        _make_apps(tmp_path, {"core": ["enterprise/license_filter.py"]})
        with pytest.raises(EnterpriseFootprintError):
            _load_extra(tmp_path, monkeypatch, install_apps="core")

    def test_license_mgmt_added_to_explicit_install_apps_when_footprint_present(self, tmp_path, monkeypatch):
        """When enterprise footprint + license_mgmt present and INSTALL_APPS is explicit,
        license_mgmt must be injected into install_apps."""
        _make_apps(
            tmp_path,
            {
                "core": ["enterprise/license_filter.py"],
                "license_mgmt": ["__init__.py"],
            },
        )
        mod = _load_extra(tmp_path, monkeypatch, install_apps="core,other_app")
        assert "license_mgmt" in mod.install_apps.split(",")

    def test_license_mgmt_not_added_when_install_apps_empty(self, tmp_path, monkeypatch):
        """When INSTALL_APPS is empty (auto-discovery mode), extra.py must not modify install_apps."""
        _make_apps(
            tmp_path,
            {
                "core": ["enterprise/license_filter.py"],
                "license_mgmt": ["__init__.py"],
            },
        )
        mod = _load_extra(tmp_path, monkeypatch, install_apps="")
        assert mod.install_apps == ""

    def test_no_error_when_no_enterprise_footprint(self, tmp_path, monkeypatch):
        """Community edition (no enterprise content) loads without error."""
        _make_apps(tmp_path, {"myapp": []})
        mod = _load_extra(tmp_path, monkeypatch, install_apps="myapp")
        assert "license_mgmt" not in mod.install_apps
