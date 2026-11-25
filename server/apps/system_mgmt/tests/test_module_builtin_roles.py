from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.system_mgmt.management.commands.init_realm_resource import create_default_roles
from apps.system_mgmt.models import App, Group, Menu, Role, User
from apps.system_mgmt.nats.auth import build_user_authorization_context

pytestmark = pytest.mark.django_db

BASE = "/api/v1/system_mgmt/role"


@pytest.fixture
def super_client(db):
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(username="modrole-admin", password="pw", domain="domain.com", locale="en")
    admin.is_superuser = True
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture(autouse=True)
def _silence_logs():
    with patch("apps.system_mgmt.viewset.role_viewset.log_operation"), patch("apps.system_mgmt.viewset.role_viewset.clear_users_permission_cache"):
        yield


def _menus(app_name):
    view = Menu.objects.create(app=app_name, name="asset-View", display_name="v", url="", menu_type="t", order=1)
    add = Menu.objects.create(app=app_name, name="asset-Add", display_name="a", url="", menu_type="t", order=2)
    return view, add


def test_create_default_roles_seeds_module_roles_except_system_manager():
    cmdb = App.objects.create(name="cmdb", display_name="CMDB", url="/cmdb")
    system = App.objects.create(name="system-manager", display_name="System", url="/system-manager")
    console = App.objects.create(name="ops-console", display_name="Console", url="/ops-console/home")
    view, add = _menus("cmdb")
    _menus("system-manager")
    stale = Role.objects.create(name="module_admin", app="ops-console", menu_list=[])
    holder = User.objects.create(
        username="console-holder",
        display_name="holder",
        email="holder@example.com",
        password="x",
        domain="domain.com",
        role_list=[stale.id, 19],
    )

    create_default_roles(cmdb, [])
    create_default_roles(system, [])
    create_default_roles(console, [])

    admin_role = Role.objects.get(app="cmdb", name="module_admin")
    auditor_role = Role.objects.get(app="cmdb", name="module_auditor")
    assert set(admin_role.menu_list) == {view.id, add.id}
    assert auditor_role.menu_list == [view.id]
    assert Role.objects.filter(app="cmdb", name="manager").exists()
    assert not Role.objects.filter(app="system-manager", name__in=["module_admin", "module_auditor"]).exists()
    assert not Role.objects.filter(app="ops-console", name__in=["module_admin", "module_auditor"]).exists()
    holder.refresh_from_db()
    assert holder.role_list == [19]


def test_role_tree_puts_module_roles_first_and_marks_them():
    Role.objects.create(name="normal", app="cmdb")
    Role.objects.create(name="module_auditor", app="cmdb")
    Role.objects.create(name="admin", app="cmdb")
    Role.objects.create(name="module_admin", app="cmdb")
    client = APIClient()
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(username="tree-admin", password="pw", domain="domain.com", locale="en")
    admin.is_superuser = True
    admin.save()
    client.force_authenticate(user=admin)

    resp = client.post(
        f"{BASE}/get_role_tree/",
        {"client_list": [{"id": 2, "name": "cmdb", "display_name": "CMDB"}]},
        format="json",
    )

    children = resp.json()["data"][0]["children"]
    assert [row["name"] for row in children] == ["module_admin", "module_auditor", "admin", "normal"]
    assert [row["builtin"] for row in children] == ["module", "module", "", ""]


def test_module_roles_cannot_be_edited_or_given_to_an_organization(super_client):
    role = Role.objects.create(name="module_admin", app="cmdb", menu_list=[])
    group = Group.objects.create(name="org-a", parent_id=0)

    updated = super_client.post(f"{BASE}/update_role/", {"role_id": role.id, "role_name": "renamed"}, format="json")
    menus = super_client.post(f"{BASE}/set_role_menus/", {"role_id": role.id, "menus": ["asset-View"]}, format="json")
    assigned = super_client.post(f"{BASE}/batch_assign_group_roles/", {"role_id": role.id, "group_ids": [group.id]}, format="json")
    deleted = super_client.post(f"{BASE}/delete_role/", {"role_id": role.id, "role_name": "custom"}, format="json")

    role.refresh_from_db()
    assert updated.status_code == 400 and updated.json()["result"] is False
    assert menus.status_code == 400 and menus.json()["result"] is False
    assert assigned.status_code == 400 and assigned.json()["result"] is False
    assert deleted.status_code == 400 and deleted.json()["result"] is False
    assert role.name == "module_admin"
    assert list(group.roles.values_list("id", flat=True)) == []


def test_module_admin_sees_every_org_without_becoming_platform_superuser():
    home = Group.objects.create(name="home", parent_id=0)
    other = Group.objects.create(name="other", parent_id=0)
    view = Menu.objects.create(app="cmdb", name="asset-View", display_name="v", url="", menu_type="t", order=1)
    Menu.objects.create(app="cmdb", name="asset-Add", display_name="a", url="", menu_type="t", order=2)
    role = Role.objects.create(name="module_admin", app="cmdb", menu_list=[view.id])
    user = User.objects.create(
        username="cmdb-admin",
        password="x",
        display_name="cmdb-admin",
        email="cmdb-admin@example.com",
        domain="domain.com",
        group_list=[home.id],
        role_list=[role.id],
    )

    ctx = build_user_authorization_context(user)

    assert ctx["is_superuser"] is False
    assert ctx["is_auditor"] is False
    assert {row["id"] for row in ctx["group_list"]} == {home.id}
    assert {other.id, home.id} <= {node["id"] for node in ctx["module_group_tree"]}
    assert set(ctx["permission"]["cmdb"]) == {"asset-View", "asset-Add"}
    assert ctx["module_admin_apps"] == ["cmdb"]


def test_module_auditor_permission_stays_view_only_when_another_role_can_write():
    home = Group.objects.create(name="home-aud", parent_id=0)
    Menu.objects.create(app="cmdb", name="asset-View", display_name="v", url="", menu_type="t", order=1)
    add = Menu.objects.create(app="cmdb", name="asset-Add", display_name="a", url="", menu_type="t", order=2)
    writer = Role.objects.create(name="writer", app="cmdb", menu_list=[add.id])
    auditor = Role.objects.create(name="module_auditor", app="cmdb", menu_list=[])
    user = User.objects.create(
        username="cmdb-auditor",
        password="x",
        display_name="cmdb-auditor",
        email="cmdb-auditor@example.com",
        domain="domain.com",
        group_list=[home.id],
        role_list=[writer.id, auditor.id],
    )

    ctx = build_user_authorization_context(user)

    assert ctx["is_superuser"] is False
    assert ctx["permission"]["cmdb"] == ["asset-View"]
    assert ctx["module_auditor_apps"] == ["cmdb"]


def test_module_admin_role_does_not_persist_as_platform_superuser():
    from apps.core.backends import AuthBackend

    cmdb_request = SimpleNamespace(resolver_match=SimpleNamespace(route="api/v1/cmdb/instance/"), path="/api/v1/cmdb/instance/")
    assert AuthBackend.get_is_superuser(cmdb_request, {"is_superuser": False, "roles": ["cmdb--module_admin"]}) is False
    assert AuthBackend.get_is_superuser(cmdb_request, {"is_superuser": False, "roles": ["cmdb--admin"]}) is True

    job_request = SimpleNamespace(resolver_match=SimpleNamespace(route="api/v1/job_mgmt/target/"), path="/api/v1/job_mgmt/target/")
    assert AuthBackend.get_is_superuser(job_request, {"is_superuser": False, "roles": ["job--module_admin"]}) is False


def test_cmdb_module_role_can_reach_another_org_without_a_data_rule():
    from apps.cmdb.constants.constants import OPERATE, VIEW
    from apps.cmdb.views.mixins import CmdbPermissionMixin

    def make_request(roles, *, is_auditor=False):
        return SimpleNamespace(
            user=SimpleNamespace(roles=roles, is_superuser=False, is_auditor=is_auditor, group_list=[{"id": 1}]),
            COOKIES={"current_team": "9", "include_children": "0"},
        )

    instance = {"organization": [9], "model_id": "host", "inst_name": "host-a"}
    mixin = CmdbPermissionMixin()

    assert mixin.check_instance_permission(make_request(["cmdb--module_admin"]), instance, OPERATE) is True
    assert mixin.check_instance_permission(make_request(["cmdb--module_auditor"]), instance, VIEW) is True
    assert mixin.check_instance_permission(make_request(["cmdb--module_auditor"]), instance, OPERATE) is False
    assert mixin.check_instance_permission(make_request(["cmdb--normal"]), instance, VIEW) is False
    assert mixin.check_instance_permission(make_request(["cmdb--module_admin"], is_auditor=True), instance, OPERATE) is False
    assert mixin.get_user_organizations(make_request(["cmdb--module_admin"]), instance) == [9]


def test_platform_identity_cannot_take_module_roles(super_client):
    admin = Role.objects.create(name="admin", app="")
    auditor = Role.objects.create(name="auditor", app="")
    module_admin = Role.objects.create(name="module_admin", app="cmdb")
    module_auditor = Role.objects.create(name="module_auditor", app="cmdb")
    auditor_user = User.objects.create(
        username="plat-auditor",
        password="x",
        display_name="plat-auditor",
        email="plat-auditor@example.com",
        domain="domain.com",
        role_list=[auditor.id],
    )
    admin_user = User.objects.create(
        username="plat-admin",
        password="x",
        display_name="plat-admin",
        email="plat-admin@example.com",
        domain="domain.com",
        role_list=[admin.id],
    )
    normal_user = User.objects.create(
        username="plain-user",
        password="x",
        display_name="plain-user",
        email="plain-user@example.com",
        domain="domain.com",
        role_list=[],
    )

    blocked_pairs = (
        (module_admin, auditor_user),
        (module_auditor, auditor_user),
        (module_admin, admin_user),
        (module_auditor, admin_user),
    )
    for role, user in blocked_pairs:
        response = super_client.post(f"{BASE}/add_user/", {"role_id": role.id, "user_ids": [user.id]}, format="json")
        user.refresh_from_db()
        assert response.status_code == 400
        assert role.id not in user.role_list

    mixed = super_client.post(
        f"{BASE}/add_user/",
        {"role_id": module_admin.id, "user_ids": [auditor_user.id, normal_user.id]},
        format="json",
    )
    auditor_user.refresh_from_db()
    normal_user.refresh_from_db()
    assert mixed.status_code == 400
    assert module_admin.id not in auditor_user.role_list
    assert module_admin.id not in normal_user.role_list

    for role in (module_admin, module_auditor):
        allowed = super_client.post(f"{BASE}/add_user/", {"role_id": role.id, "user_ids": [normal_user.id]}, format="json")
        normal_user.refresh_from_db()
        assert allowed.json()["result"] is True
        assert role.id in normal_user.role_list
