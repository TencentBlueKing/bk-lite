"""GroupViewSet 自定义 action 的 API 行为测试（superuser 绕过权限）。

只 mock 真实外部边界（log_operation、CMDB rpc、clear_users_permission_cache、cache）。
"""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.system_mgmt.models import Group, Role, User

pytestmark = pytest.mark.django_db

BASE = "/api/v1/system_mgmt/group"


@pytest.fixture
def super_client(db):
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(username="gvadmin", password="pw", domain="domain.com", locale="en")
    admin.is_superuser = True
    admin.group_list = [{"id": 1, "name": "Default"}]
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture(autouse=True)
def _patch_externals():
    with patch("apps.system_mgmt.viewset.group_viewset.log_operation"), patch(
        "apps.system_mgmt.viewset.group_viewset.clear_users_permission_cache"
    ), patch("apps.system_mgmt.viewset.group_viewset.CMDB") as m_cmdb:
        m_cmdb.return_value.sync_display_fields.return_value = None
        yield


# ---------------------------------------------------------------------------
# disabled CRUD
# ---------------------------------------------------------------------------
def test_builtin_list_disabled(super_client):
    resp = super_client.get(f"{BASE}/")
    assert resp.status_code == 405


# ---------------------------------------------------------------------------
# get_teams / search_group_list
# ---------------------------------------------------------------------------
def test_get_teams(super_client):
    resp = super_client.get(f"{BASE}/get_teams/")
    assert resp.status_code == 200
    assert resp.json()["data"] == [{"id": 1, "name": "Default"}]


def test_search_group_list(super_client):
    Group.objects.create(name="SGLGroup", parent_id=0)
    resp = super_client.get(f"{BASE}/search_group_list/")
    assert resp.status_code == 200
    assert resp.json()["result"] is True


# ---------------------------------------------------------------------------
# get_detail
# ---------------------------------------------------------------------------
def test_get_detail(super_client):
    g = Group.objects.create(name="DetailGroup", parent_id=0, is_virtual=False)
    resp = super_client.get(f"{BASE}/get_detail/?group_id={g.id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "DetailGroup"
    assert data["id"] == g.id


# ---------------------------------------------------------------------------
# create_group
# ---------------------------------------------------------------------------
def test_create_group_top_level(super_client):
    resp = super_client.post(f"{BASE}/create_group/", {"group_name": "新顶级组"}, format="json")
    assert resp.json()["result"] is True
    assert Group.objects.filter(name="新顶级组", parent_id=0).exists()


def test_create_group_top_level_virtual_forbidden(super_client):
    resp = super_client.post(
        f"{BASE}/create_group/", {"group_name": "顶级虚拟", "is_virtual": True}, format="json"
    )
    assert resp.json()["result"] is False


def test_create_group_under_parent(super_client):
    parent = Group.objects.create(name="ParentG", parent_id=0)
    resp = super_client.post(
        f"{BASE}/create_group/",
        {"group_name": "子组", "parent_group_id": parent.id},
        format="json",
    )
    assert resp.json()["result"] is True
    assert Group.objects.filter(name="子组", parent_id=parent.id).exists()


def test_create_group_parent_not_found(super_client):
    resp = super_client.post(
        f"{BASE}/create_group/",
        {"group_name": "孤儿", "parent_group_id": 999999},
        format="json",
    )
    assert resp.json()["result"] is False


def test_create_group_inherits_virtual_from_top_virtual_parent(super_client):
    vparent = Group.objects.create(name="VTop", parent_id=0, is_virtual=True)
    resp = super_client.post(
        f"{BASE}/create_group/",
        {"group_name": "虚拟子", "parent_group_id": vparent.id},
        format="json",
    )
    assert resp.json()["result"] is True
    child = Group.objects.get(name="虚拟子")
    assert child.is_virtual is True


def test_create_group_under_virtual_subgroup_forbidden(super_client):
    vtop = Group.objects.create(name="VT", parent_id=0, is_virtual=True)
    vsub = Group.objects.create(name="VSub", parent_id=vtop.id, is_virtual=True)
    resp = super_client.post(
        f"{BASE}/create_group/",
        {"group_name": "深层", "parent_group_id": vsub.id},
        format="json",
    )
    assert resp.json()["result"] is False


# ---------------------------------------------------------------------------
# update_group
# ---------------------------------------------------------------------------
def test_update_group(super_client):
    g = Group.objects.create(name="OldG", parent_id=0)
    role = Role.objects.create(name="r", app="cmdb")
    resp = super_client.post(
        f"{BASE}/update_group/",
        {"group_id": g.id, "group_name": "NewG", "role_ids": [role.id], "allow_inherit_roles": True},
        format="json",
    )
    assert resp.json()["result"] is True
    g.refresh_from_db()
    assert g.name == "NewG"
    assert g.allow_inherit_roles is True
    assert role in g.roles.all()


def test_update_group_default_protected(super_client):
    Group.objects.filter(name="Default", parent_id=0).delete()
    g = Group.objects.create(name="Default", parent_id=0)
    resp = super_client.post(
        f"{BASE}/update_group/", {"group_id": g.id, "group_name": "x"}, format="json"
    )
    assert resp.json()["result"] is False


# ---------------------------------------------------------------------------
# delete_groups
# ---------------------------------------------------------------------------
def test_delete_groups_with_children(super_client):
    parent = Group.objects.create(name="DelParent", parent_id=0)
    child = Group.objects.create(name="DelChild", parent_id=parent.id)
    resp = super_client.post(f"{BASE}/delete_groups/", {"id": parent.id}, format="json")
    assert resp.json()["result"] is True
    assert not Group.objects.filter(id__in=[parent.id, child.id]).exists()


def test_delete_groups_default_protected(super_client):
    Group.objects.filter(name="Default", parent_id=0).delete()
    g = Group.objects.create(name="Default", parent_id=0)
    resp = super_client.post(f"{BASE}/delete_groups/", {"id": g.id}, format="json")
    assert resp.json()["result"] is False


def test_delete_groups_virtual_top_protected(super_client):
    g = Group.objects.create(name="VTopDel", parent_id=0, is_virtual=True)
    resp = super_client.post(f"{BASE}/delete_groups/", {"id": g.id}, format="json")
    assert resp.json()["result"] is False
    assert Group.objects.filter(id=g.id).exists()


# ---------------------------------------------------------------------------
# get_group_detail_with_roles / batch
# ---------------------------------------------------------------------------
def test_get_group_detail_with_roles_inheritance(super_client):
    role_parent = Role.objects.create(name="rp", app="cmdb")
    parent = Group.objects.create(name="RP", parent_id=0, allow_inherit_roles=True)
    parent.roles.add(role_parent)
    child = Group.objects.create(name="RC", parent_id=parent.id)
    role_own = Role.objects.create(name="ro", app="cmdb")
    child.roles.add(role_own)

    resp = super_client.post(
        f"{BASE}/get_group_detail_with_roles/", {"group_id": child.id}, format="json"
    )
    data = resp.json()["data"]
    assert data["own_role_ids"] == [role_own.id]
    assert role_parent.id in data["inherited_role_ids"]
    assert data["inherited_role_source_map"][str(role_parent.id)] == "RP"


def test_get_group_detail_with_roles_not_found(super_client):
    resp = super_client.post(
        f"{BASE}/get_group_detail_with_roles/", {"group_id": 999999}, format="json"
    )
    assert resp.json()["result"] is False


def test_batch_get_group_detail_with_roles(super_client):
    g1 = Group.objects.create(name="BG1", parent_id=0)
    g2 = Group.objects.create(name="BG2", parent_id=0)
    resp = super_client.post(
        f"{BASE}/batch_get_group_detail_with_roles/",
        {"group_ids": [g1.id, g2.id]},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["result"] is True


def test_batch_get_group_detail_invalid_param(super_client):
    resp = super_client.post(
        f"{BASE}/batch_get_group_detail_with_roles/", {"group_ids": "notalist"}, format="json"
    )
    assert resp.status_code == 400
