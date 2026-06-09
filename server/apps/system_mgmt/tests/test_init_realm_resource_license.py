"""
TDD tests for get_install_apps() using the centralized enterprise footprint detector.

Task 3 covers:
- license_mgmt is added when enterprise footprint is present and license_mgmt exists
- EnterpriseFootprintError propagates when footprint is present but license_mgmt is absent
- No Django DB required; pure unit tests via mocking

The logic under test lives in the lightweight helper
apps.system_mgmt.management.commands._install_apps, which has no Django model imports,
making it testable without a full Django project setup.
"""
import types
from unittest.mock import MagicMock, mock_open, patch

import pytest

from apps.core.utils.enterprise_footprint import EnterpriseFootprintError, EnterpriseFootprintStatus
from apps.system_mgmt.management.commands._install_apps import get_install_apps

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


# Patch target: detect_enterprise_footprint as bound in the helper module
_DETECTOR_PATH = "apps.system_mgmt.management.commands._install_apps.detect_enterprise_footprint"


class TestGetInstallAppsLicense:
    def test_license_mgmt_added_when_footprint_and_license_mgmt_present(self, monkeypatch):
        """If enterprise footprint exists AND license_mgmt dir is present, add license_mgmt."""
        status = EnterpriseFootprintStatus(enterprise_apps=["some_enterprise_app"], license_mgmt_present=True)
        monkeypatch.setenv("INSTALL_APPS", "")
        with patch(_DETECTOR_PATH, return_value=status):
            result = get_install_apps()
        assert "license_mgmt" in result

    def test_enterprise_footprint_error_propagates_when_license_mgmt_absent(self, monkeypatch):
        """If enterprise footprint exists but license_mgmt is absent, EnterpriseFootprintError is raised."""
        status = EnterpriseFootprintStatus(enterprise_apps=["some_enterprise_app"], license_mgmt_present=False)
        monkeypatch.setenv("INSTALL_APPS", "")
        with patch(_DETECTOR_PATH, return_value=status):
            with pytest.raises(EnterpriseFootprintError):
                get_install_apps()

    def test_license_mgmt_not_added_when_no_enterprise_footprint(self, monkeypatch):
        """Community edition (no enterprise footprint) must not inject license_mgmt."""
        status = EnterpriseFootprintStatus(enterprise_apps=[], license_mgmt_present=False)
        monkeypatch.setenv("INSTALL_APPS", "")
        with patch(_DETECTOR_PATH, return_value=status):
            result = get_install_apps()
        assert "license_mgmt" not in result

    def test_existing_install_apps_preserved_alongside_license_mgmt(self, monkeypatch):
        """Explicit INSTALL_APPS entries must be preserved when license_mgmt is also injected."""
        status = EnterpriseFootprintStatus(enterprise_apps=["some_enterprise_app"], license_mgmt_present=True)
        monkeypatch.setenv("INSTALL_APPS", "cmdb,monitor")
        with patch(_DETECTOR_PATH, return_value=status):
            result = get_install_apps()
        assert "cmdb" in result
        assert "monitor" in result
        assert "license_mgmt" in result

    def test_explicit_install_apps_license_mgmt_discarded_without_enterprise_footprint(self, monkeypatch):
        """INSTALL_APPS=license_mgmt must be discarded when there is no enterprise footprint.

        Regression: get_install_apps() was preserving the explicit value from os.getenv
        without gating it on enterprise status, inconsistent with app.py Task 2 behaviour.
        """
        status = EnterpriseFootprintStatus(enterprise_apps=[], license_mgmt_present=True)
        monkeypatch.setenv("INSTALL_APPS", "license_mgmt")
        with patch(_DETECTOR_PATH, return_value=status):
            result = get_install_apps()
        assert "license_mgmt" not in result, "get_install_apps() must discard explicit license_mgmt when there is no enterprise footprint"


class TestCommandHandleEnterpriseFootprintPropagation:
    """Regression: Command.handle() must propagate EnterpriseFootprintError, not swallow it."""

    _CMD_PATH = "apps.system_mgmt.management.commands.init_realm_resource"

    def test_handle_propagates_enterprise_footprint_error(self):
        """EnterpriseFootprintError from get_install_apps() must escape Command.handle().

        Regression: get_install_apps() was called inside the per-file try/except block,
        so EnterpriseFootprintError was silently logged and execution continued.
        After the fix, get_install_apps() is resolved before the file-read loop so the
        error propagates immediately.
        """
        from apps.system_mgmt.management.commands.init_realm_resource import Command

        fake_menu = {
            "client_id": "system-manager",
            "name": "System Manager",
            "description": "",
            "url": "",
            "icon": "system-manager",
            "menus": [],
            "roles": [],
        }

        with patch(
            f"{self._CMD_PATH}.get_install_apps",
            side_effect=EnterpriseFootprintError("enterprise footprint detected but license_mgmt missing"),
        ), patch(f"{self._CMD_PATH}.os.walk", return_value=[("root", [], ["menu.json"])],), patch("builtins.open", mock_open()), patch(
            f"{self._CMD_PATH}.json"
        ) as mock_json, patch(
            f"{self._CMD_PATH}.Group"
        ) as mock_group:
            mock_json.load.return_value = fake_menu
            mock_group.objects.get_or_create.return_value = (MagicMock(), True)

            with pytest.raises(EnterpriseFootprintError):
                Command().handle()
