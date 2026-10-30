import sys
import types

import pytest

from apps.operation_analysis.services.render_authorized_apps import resolve_execution_authorized_app_names
from apps.system_mgmt.models.app import App
from apps.system_mgmt.models.role import Role
from apps.system_mgmt.models.user import User


def _app(name):
    return App.objects.create(name=name, display_name=name, url=f"/{name}")


def _user(username, role_ids):
    return User.objects.create(
        username=username,
        domain="domain.com",
        display_name=username,
        email=f"{username}@example.com",
        password="x",
        group_list=[],
        role_list=role_ids,
    )


@pytest.mark.django_db
def test_execution_authorized_apps_follow_creator_roles_not_every_app():
    _app("cmdb")
    _app("alarm")
    _app("monitor")
    alarm = Role.objects.create(name="guest", app="alarm")
    cmdb = Role.objects.create(name="guest", app="cmdb")
    _user("creator", [alarm.id, cmdb.id])

    assert resolve_execution_authorized_app_names(username="creator", domain="domain.com") == ["cmdb", "alarm"]


@pytest.mark.django_db
def test_execution_authorized_apps_for_platform_admin_include_installed_apps():
    _app("cmdb")
    _app("monitor")
    admin = Role.objects.create(name="admin", app="")
    _user("root", [admin.id])

    assert resolve_execution_authorized_app_names(username="root", domain="domain.com") == ["cmdb", "monitor"]


@pytest.mark.django_db
def test_license_filter_receives_get_client_fields(monkeypatch):
    _app("cmdb")
    _app("alarm")
    role = Role.objects.create(name="guest", app="cmdb")
    _user("licensed", [role.id])
    seen = {}

    def fake_filter(rows):
        seen["rows"] = rows
        return [row for row in rows if row.get("name") == "cmdb"]

    package = types.ModuleType("apps.core.enterprise")
    module = types.ModuleType("apps.core.enterprise.license_filter")
    module.filter_clients_by_license = fake_filter
    monkeypatch.setitem(sys.modules, "apps.core.enterprise", package)
    monkeypatch.setitem(sys.modules, "apps.core.enterprise.license_filter", module)

    assert resolve_execution_authorized_app_names(username="licensed", domain="domain.com") == ["cmdb"]
    assert seen["rows"][0]["name"] == "cmdb"
    assert seen["rows"][0]["is_build_in"] is True
    assert "display_name" in seen["rows"][0]
    assert "url" in seen["rows"][0]


@pytest.mark.django_db
def test_execution_authorized_apps_accept_dict_shaped_group_list():
    _app("cmdb")
    role = Role.objects.create(name="guest", app="cmdb")
    user = _user("dict-groups", [role.id])
    user.group_list = [{"id": 1, "name": "Default"}]
    user.save(update_fields=["group_list"])

    assert resolve_execution_authorized_app_names(username="dict-groups", domain="domain.com") == ["cmdb"]


@pytest.mark.django_db
def test_missing_execution_creator_has_explicit_empty_app_list():
    _app("alarm")
    assert resolve_execution_authorized_app_names(username="gone", domain="domain.com") == []
