"""
TDD tests for get_install_apps() using the centralized enterprise footprint detector.

Task 3 covers:
- license_mgmt is added when enterprise footprint is present and license_mgmt exists
- EnterpriseFootprintError propagates when footprint is present but license_mgmt is absent
- No Django DB required; pure unit tests via mocking
"""
from unittest.mock import patch

import pytest

from config.components.enterprise import EnterpriseFootprintError, EnterpriseFootprintStatus

# Patch target: the name bound in the command module after the module-level import
_DETECTOR_PATH = "apps.system_mgmt.management.commands.init_realm_resource.detect_enterprise_footprint"


def _get_install_apps():
    """Late import so Django setup from pytest.ini is in effect."""
    from apps.system_mgmt.management.commands.init_realm_resource import get_install_apps

    return get_install_apps


class TestGetInstallAppsLicense:
    def test_license_mgmt_added_when_footprint_and_license_mgmt_present(self, monkeypatch):
        """If enterprise footprint exists AND license_mgmt dir is present, add license_mgmt."""
        status = EnterpriseFootprintStatus(enterprise_apps=["some_enterprise_app"], license_mgmt_present=True)
        monkeypatch.setenv("INSTALL_APPS", "")
        with patch(_DETECTOR_PATH, return_value=status):
            result = _get_install_apps()()
        assert "license_mgmt" in result

    def test_enterprise_footprint_error_propagates_when_license_mgmt_absent(self, monkeypatch):
        """If enterprise footprint exists but license_mgmt is absent, EnterpriseFootprintError is raised."""
        status = EnterpriseFootprintStatus(enterprise_apps=["some_enterprise_app"], license_mgmt_present=False)
        monkeypatch.setenv("INSTALL_APPS", "")
        with patch(_DETECTOR_PATH, return_value=status):
            with pytest.raises(EnterpriseFootprintError):
                _get_install_apps()()

    def test_license_mgmt_not_added_when_no_enterprise_footprint(self, monkeypatch):
        """Community edition (no enterprise footprint) must not inject license_mgmt."""
        status = EnterpriseFootprintStatus(enterprise_apps=[], license_mgmt_present=False)
        monkeypatch.setenv("INSTALL_APPS", "")
        with patch(_DETECTOR_PATH, return_value=status):
            result = _get_install_apps()()
        assert "license_mgmt" not in result

    def test_existing_install_apps_preserved_alongside_license_mgmt(self, monkeypatch):
        """Explicit INSTALL_APPS entries must be preserved when license_mgmt is also injected."""
        status = EnterpriseFootprintStatus(enterprise_apps=["some_enterprise_app"], license_mgmt_present=True)
        monkeypatch.setenv("INSTALL_APPS", "cmdb,monitor")
        with patch(_DETECTOR_PATH, return_value=status):
            result = _get_install_apps()()
        assert "cmdb" in result
        assert "monitor" in result
        assert "license_mgmt" in result
