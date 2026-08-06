from types import SimpleNamespace

from apps.system_mgmt.services.capability_contract_service import get_integration_capability_availability


def test_capability_availability_reports_disabled_capability():
    instance = SimpleNamespace(
        enabled=True,
        status="ready",
        capability_enabled={"login_auth": False},
        capability_status={"login_auth": "ready"},
    )

    assert get_integration_capability_availability(instance, "login_auth") == {
        "available": False,
        "reason": "capability_disabled",
    }


def test_capability_availability_accepts_legacy_instance_without_enabled_map():
    instance = SimpleNamespace(
        enabled=True,
        status="ready",
        capability_enabled={},
        capability_status={"login_auth": "ready"},
    )

    assert get_integration_capability_availability(instance, "login_auth") == {
        "available": True,
        "reason": "",
    }
