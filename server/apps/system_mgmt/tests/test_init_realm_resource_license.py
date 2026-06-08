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
from unittest.mock import patch

import pytest

from apps.system_mgmt.management.commands._install_apps import get_install_apps
from config.components.enterprise import EnterpriseFootprintError, EnterpriseFootprintStatus

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
