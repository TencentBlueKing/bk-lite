import pytest

from apps.system_mgmt.models import Menu, Role
from apps.system_mgmt.services.platform_roles import (
    PLATFORM_ADMIN_ROLE_NAMES,
    PLATFORM_AUDITOR_ROLE_NAMES,
    ensure_platform_auditor_role,
    is_platform_admin,
    is_platform_auditor,
    view_permission_map,
)


def test_role_name_detection():
    assert is_platform_admin(["admin"]) is True
    assert is_platform_admin(["system-manager--admin"]) is True
    assert is_platform_admin(["cmdb--admin"]) is False
    assert is_platform_auditor(["auditor"]) is True
    assert is_platform_auditor(["system-manager--auditor"]) is True
    assert is_platform_auditor(["admin"]) is False
    assert PLATFORM_ADMIN_ROLE_NAMES == frozenset({"admin", "system-manager--admin"})
    assert PLATFORM_AUDITOR_ROLE_NAMES == frozenset({"auditor", "system-manager--auditor"})


@pytest.mark.django_db
def test_ensure_auditor_role_is_idempotent():
    first = ensure_platform_auditor_role()
    second = ensure_platform_auditor_role()
    assert first.id == second.id
    assert first.name == "auditor"
    assert first.app == ""
    assert Role.objects.filter(name="auditor", app="").count() == 1


@pytest.mark.django_db
def test_view_permission_map_keeps_only_view_ops():
    Menu.objects.create(app="cmdb", name="asset_info-View", display_name="x-View", menu_type="t", order=1)
    Menu.objects.create(app="cmdb", name="asset_info-Add", display_name="x-Add", menu_type="t", order=2)
    Menu.objects.create(app="alarm", name="alerts-View", display_name="y-View", menu_type="t", order=1)
    perms = view_permission_map()
    assert perms["cmdb"] == ["asset_info-View"]
    assert perms["alarm"] == ["alerts-View"]
    assert "asset_info-Add" not in perms["cmdb"]
