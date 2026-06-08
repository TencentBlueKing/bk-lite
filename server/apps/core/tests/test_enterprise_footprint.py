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

    def test_explicit_install_apps_license_mgmt_blocked_without_footprint(self, tmp_path, monkeypatch):
        """INSTALL_APPS=license_mgmt must NOT bypass the enterprise gate in app.py.

        Even when license_mgmt is named explicitly, apps.license_mgmt must not be
        added to INSTALLED_APPS when there is no enterprise footprint.
        """
        _make_apps(tmp_path, {"license_mgmt": ["__init__.py"]})
        mod = _load_app(tmp_path, monkeypatch, install_apps="license_mgmt")
        assert "apps.license_mgmt" not in mod.INSTALLED_APPS, "INSTALL_APPS=license_mgmt must not add apps.license_mgmt without enterprise footprint"


# ---------------------------------------------------------------------------
# extra.py enterprise wiring
# ---------------------------------------------------------------------------

_EXTRA_MODULE_PATH = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "config" / "components" / "extra.py"


def _load_extra(tmp_path, monkeypatch, install_apps="", *, base_dir=None):
    """Load config/components/extra.py with BASE_DIR and cwd pointing to tmp_path (by default).

    Pass ``base_dir`` to supply a different path as BASE_DIR while keeping cwd at
    tmp_path.  This lets tests verify that extra.py follows BASE_DIR rather than
    cwd (bug-1 regression test).

    Also prepends the effective base_dir to sys.path so that __import__ calls
    inside extra.py (e.g. ``__import__("apps.license_mgmt.config")``) resolve
    against the temp package tree rather than the real server package.
    """
    import types as _types

    effective_base = base_dir if base_dir is not None else tmp_path

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INSTALL_APPS", install_apps)

    # Prepend effective_base so __import__ inside extra.py finds temp packages first.
    monkeypatch.syspath_prepend(str(effective_base))
    # Drop any stale apps.* entries so Python doesn't return the cached real package.
    for key in list(sys.modules):
        if key == "apps" or key.startswith("apps."):
            monkeypatch.delitem(sys.modules, key, raising=False)

    # Mock config.components.base with BASE_DIR = effective_base (mirrors _load_app).
    base_mock = _types.ModuleType("config.components.base")
    base_mock.BASE_DIR = effective_base
    monkeypatch.setitem(sys.modules, "config", _types.ModuleType("config"))
    monkeypatch.setitem(sys.modules, "config.components", _types.ModuleType("config.components"))
    monkeypatch.setitem(sys.modules, "config.components.base", base_mock)

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

    def test_explicit_mode_imports_license_mgmt_config_when_footprint_present(self, tmp_path, monkeypatch):
        """When INSTALL_APPS is explicit (doesn't name license_mgmt) and enterprise footprint +
        license_mgmt are both present, extra.py must inject license_mgmt into the app list so
        that its config.py is actually imported and its settings appear on the module."""
        _make_apps(
            tmp_path,
            {
                "core": ["enterprise/license_filter.py"],
                "license_mgmt": ["__init__.py"],
            },
        )
        # Sentinel setting that only appears if license_mgmt/config.py is imported.
        (tmp_path / "apps" / "license_mgmt" / "config.py").write_text("LICENSE_MGMT_CONFIG_LOADED = True\n")
        (tmp_path / "apps" / "core" / "__init__.py").write_text("")

        # install_apps lists "core" only — license_mgmt must be injected by enterprise wiring.
        mod = _load_extra(tmp_path, monkeypatch, install_apps="core")

        assert (
            getattr(mod, "LICENSE_MGMT_CONFIG_LOADED", False) is True
        ), "license_mgmt/config.py was not imported: enterprise wiring failed to inject license_mgmt"

    def test_explicit_mode_skips_license_mgmt_config_when_no_footprint(self, tmp_path, monkeypatch):
        """Without enterprise footprint, license_mgmt is NOT injected into an explicit INSTALL_APPS
        list, so its config.py must not be imported even if the directory exists."""
        _make_apps(tmp_path, {"license_mgmt": ["__init__.py"]})
        (tmp_path / "apps" / "license_mgmt" / "config.py").write_text("LICENSE_MGMT_CONFIG_LOADED = True\n")

        # "other_app" explicit list, no enterprise footprint → no injection.
        mod = _load_extra(tmp_path, monkeypatch, install_apps="other_app")

        assert (
            getattr(mod, "LICENSE_MGMT_CONFIG_LOADED", False) is False
        ), "license_mgmt/config.py must not be imported when there is no enterprise footprint"

    def test_auto_discovery_mode_preserved_when_footprint_present(self, tmp_path, monkeypatch):
        """When INSTALL_APPS is empty (auto-discovery), extra.py must not block normal config
        discovery — license_mgmt/config.py is still imported via the standard app iteration."""
        _make_apps(
            tmp_path,
            {
                "core": ["enterprise/license_filter.py"],
                "license_mgmt": ["__init__.py"],
            },
        )
        (tmp_path / "apps" / "license_mgmt" / "config.py").write_text("LICENSE_MGMT_CONFIG_LOADED = True\n")
        (tmp_path / "apps" / "core" / "__init__.py").write_text("")

        mod = _load_extra(tmp_path, monkeypatch, install_apps="")

        # In auto-discovery mode all apps are iterated; license_mgmt/config.py is found normally.
        assert getattr(mod, "LICENSE_MGMT_CONFIG_LOADED", False) is True, "auto-discovery mode must not block license_mgmt/config.py import"

    def test_uses_base_dir_not_cwd_for_enterprise_detection(self, tmp_path, monkeypatch, tmp_path_factory):
        """extra.py must scan BASE_DIR, not cwd, for enterprise content.

        Arrange: BASE_DIR has enterprise footprint + license_mgmt; cwd (tmp_path)
        has only an empty apps/ directory.  extra.py must follow BASE_DIR and detect
        the enterprise footprint, causing license_mgmt/config.py to be imported.
        With the buggy Path.cwd() code the test fails because cwd has no footprint.
        """
        base_dir = tmp_path_factory.mktemp("base_dir")
        _make_apps(
            base_dir,
            {
                "core": ["enterprise/license_filter.py"],
                "license_mgmt": ["__init__.py"],
            },
        )
        (base_dir / "apps" / "license_mgmt" / "config.py").write_text("LICENSE_MGMT_CONFIG_LOADED = True\n")
        (base_dir / "apps" / "core" / "__init__.py").write_text("")

        # cwd (tmp_path) has an apps/ dir but no enterprise content.
        (tmp_path / "apps").mkdir()

        mod = _load_extra(tmp_path, monkeypatch, install_apps="core", base_dir=base_dir)

        assert getattr(mod, "LICENSE_MGMT_CONFIG_LOADED", False) is True, "extra.py used cwd instead of BASE_DIR for enterprise detection"

    def test_explicit_install_apps_license_mgmt_blocked_without_footprint(self, tmp_path, monkeypatch):
        """INSTALL_APPS=license_mgmt must NOT bypass the enterprise gate in extra.py.

        Even when license_mgmt is named explicitly in INSTALL_APPS, its config.py
        must not be imported when there is no enterprise footprint.
        """
        _make_apps(tmp_path, {"license_mgmt": ["__init__.py"]})
        (tmp_path / "apps" / "license_mgmt" / "config.py").write_text("LICENSE_MGMT_CONFIG_LOADED = True\n")

        mod = _load_extra(tmp_path, monkeypatch, install_apps="license_mgmt")

        assert getattr(mod, "LICENSE_MGMT_CONFIG_LOADED", False) is False, "INSTALL_APPS=license_mgmt must not bypass the enterprise gate in extra.py"
