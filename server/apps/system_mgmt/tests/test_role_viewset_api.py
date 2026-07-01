"""RoleViewSet 自定义 action 的 API 行为测试（经 DRF 路由，superuser 绕过权限）。

只 mock 真实外部边界（log_operation、clear_users_permission_cache、cache）；
断言真实 DB 副作用与响应结构。
"""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.system_mgmt.models import Group, Menu, Role, User

pytestmark = pytest.mark.django_db

BASE = "/api/v1/system_mgmt/role"


@pytest.fixture
def super_client(db):
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(
        username="rvadmin", password="pw", domain="domain.com", locale="en",
    )
    admin.is_superuser = True
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture(autouse=True)
def _silence_logs():
    with patch("apps.system_mgmt.viewset.role_viewset.log_operation"), patch(
        "apps.system_mgmt.viewset.role_viewset.clear_users_permission_cache"
    ):
        yield


def test_search_role_list(super_client):
    Role.objects.create(name="r1", app="cmdb")
    Role.objects.create(name="r2", app="monitor")
    resp = super_client.post(f"{BASE}/search_role_list/", {"client_id": ["cmdb"]}, format="json")
    assert resp.status_code == 200
    data = resp.json()["data"]
    names = {r["name"] for r in data}
    assert names == {"r1"}


def test_get_role_tree(super_client):
    Role.objects.create(name="ra", app="cmdb")
    resp = super_client.post(
        f"{BASE}/get_role_tree/",
        {"client_list": [{"id": 2, "name": "cmdb", "is_build_in": False}]},
        format="json",
    )
    assert resp.status_code == 200
    tree = resp.json()["data"]
    assert tree[0]["id"] == 2 * 886
    assert any(c["name"] == "ra" for c in tree[0]["children"])


def test_create_role(super_client):
    resp = super_client.post(
        f"{BASE}/create_role/", {"client_id": "cmdb", "name": "新角色"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.json()["result"] is True
    assert Role.objects.filter(name="新角色", app="cmdb").exists()


def test_update_role(super_client):
    role = Role.objects.create(name="old", app="cmdb")
    resp = super_client.post(
        f"{BASE}/update_role/", {"role_id": role.id, "role_name": "new"}, format="json"
    )
    assert resp.status_code == 200
    role.refresh_from_db()
    assert role.name == "new"


def test_delete_role_protected(super_client):
    resp = super_client.post(
        f"{BASE}/delete_role/", {"role_id": 1, "role_name": "admin"}, format="json"
    )
    assert resp.json()["result"] is False


def test_delete_role_success(super_client):
    role = Role.objects.create(name="todelete", app="cmdb")
    resp = super_client.post(
        f"{BASE}/delete_role/", {"role_id": role.id, "role_name": "todelete"}, format="json"
    )
    assert resp.json()["result"] is True
    assert not Role.objects.filter(id=role.id).exists()


def test_get_role_menus(super_client):
    m1 = Menu.objects.create(name="menu-a", display_name="A-x", order=1, app="cmdb", menu_type="t")
    role = Role.objects.create(name="withmenus", app="cmdb", menu_list=[m1.id])
    resp = super_client.get(f"{BASE}/get_role_menus/?role_id={role.id}")
    assert resp.status_code == 200
    assert "menu-a" in resp.json()["data"]


def test_get_all_menus_action(super_client):
    Menu.objects.create(name="x-view", display_name="X-查看-x", order=1, app="cmdb", menu_type="t")
    resp = super_client.get(f"{BASE}/get_all_menus/?client_id=cmdb")
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


def test_add_user_and_delete_user(super_client):
    role = Role.objects.create(name="assignable", app="cmdb")
    user = User.objects.create(
        username="rvu", password="x", display_name="U", email="u@x.com", role_list=[]
    )
    add = super_client.post(
        f"{BASE}/add_user/", {"role_id": role.id, "user_ids": [user.id]}, format="json"
    )
    assert add.json()["result"] is True
    user.refresh_from_db()
    assert role.id in user.role_list

    rm = super_client.post(
        f"{BASE}/delete_user/", {"role_id": role.id, "user_ids": [user.id]}, format="json"
    )
    assert rm.json()["result"] is True
    user.refresh_from_db()
    assert role.id not in user.role_list


def test_set_role_menus(super_client):
    m1 = Menu.objects.create(name="set-a", display_name="A-x", order=1, app="cmdb", menu_type="t")
    Menu.objects.create(name="set-b", display_name="B-x", order=2, app="cmdb", menu_type="t")
    role = Role.objects.create(name="setmenus", app="cmdb", menu_list=[])
    resp = super_client.post(
        f"{BASE}/set_role_menus/", {"role_id": role.id, "menus": ["set-a"]}, format="json"
    )
    assert resp.json()["result"] is True
    role.refresh_from_db()
    assert role.menu_list == [m1.id]


def test_batch_assign_and_revoke_group_roles(super_client):
    role = Role.objects.create(name="grouprole", app="cmdb")
    g1 = Group.objects.create(name="GR1", parent_id=0)
    g2 = Group.objects.create(name="GR2", parent_id=0)
    assign = super_client.post(
        f"{BASE}/batch_assign_group_roles/",
        {"group_ids": [g1.id, g2.id], "role_id": role.id},
        format="json",
    )
    assert assign.json()["result"] is True
    assert role.group_set.count() == 2

    revoke = super_client.post(
        f"{BASE}/revoke_group_roles/",
        {"group_ids": [g1.id], "role_id": role.id},
        format="json",
    )
    assert revoke.json()["result"] is True
    assert role.group_set.count() == 1


def test_batch_assign_missing_params(super_client):
    resp = super_client.post(f"{BASE}/batch_assign_group_roles/", {"group_ids": []}, format="json")
    assert resp.json()["result"] is False


def test_batch_assign_nonexistent_group(super_client):
    role = Role.objects.create(name="r", app="cmdb")
    resp = super_client.post(
        f"{BASE}/batch_assign_group_roles/",
        {"group_ids": [999999], "role_id": role.id},
        format="json",
    )
    assert resp.json()["result"] is False


def test_get_role_groups(super_client):
    role = Role.objects.create(name="rg", app="cmdb")
    g = Group.objects.create(name="RGGroup", parent_id=0)
    role.group_set.add(g)
    resp = super_client.get(f"{BASE}/get_role_groups/?role_id={role.id}")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert any(i["name"] == "RGGroup" for i in items)


def test_get_role_groups_missing_role_id(super_client):
    resp = super_client.get(f"{BASE}/get_role_groups/")
    assert resp.json()["result"] is False


def test_get_groups_roles(super_client):
    role = Role.objects.create(name="ggr", app="cmdb")
    g = Group.objects.create(name="GGRGroup", parent_id=0)
    role.group_set.add(g)
    resp = super_client.post(f"{BASE}/get_groups_roles/", {"group_ids": [g.id]}, format="json")
    assert resp.status_code == 200
    assert any(r["name"] == "ggr" for r in resp.json()["data"])


def test_get_groups_roles_empty(super_client):
    resp = super_client.post(f"{BASE}/get_groups_roles/", {"group_ids": []}, format="json")
    assert resp.json() == {"result": True, "data": []}


def test_search_role_users(super_client):
    role = Role.objects.create(name="sru", app="cmdb")
    User.objects.create(
        username="finduser", password="x", display_name="Find", email="f@x.com", role_list=[role.id]
    )
    resp = super_client.get(f"{BASE}/search_role_users/?role_id={role.id}&search=find")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert any(i["username"] == "finduser" for i in items)
