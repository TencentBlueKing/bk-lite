"""GroupViewSet 自定义 action 的 API 行为测试（superuser 绕过权限）。

只 mock 真实外部边界（log_operation、CMDB rpc、clear_users_permission_cache、cache）。
"""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.system_mgmt.models import Group, IntegrationInstance, Role, User, UserSyncSource

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
        "apps.system_mgmt.services.group_archive_service.log_operation"
    ), patch("apps.system_mgmt.viewset.group_viewset.clear_users_permission_cache"), patch(
        "apps.system_mgmt.services.group_archive_service.clear_users_permission_cache"
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
def test_get_teams_excludes_archived(super_client):
    from apps.base.models import User as BaseUser

    active = Group.objects.create(name="teams-active", parent_id=0)
    archived = Group.objects.create(name="teams-archived", parent_id=0, is_delete=True)
    admin = BaseUser.objects.get(username="gvadmin")
    admin.group_list = [
        {"id": active.id, "name": active.name},
        {"id": archived.id, "name": archived.name},
    ]
    admin.save()
    super_client.force_authenticate(user=admin)

    resp = super_client.get(f"{BASE}/get_teams/")
    assert resp.status_code == 200
    data = resp.json()["data"]
    ids = [item["id"] for item in data]
    assert active.id in ids
    assert archived.id not in ids
    assert all(item["name"] != "teams-archived" for item in data)


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


def test_get_detail_hides_archived_group(super_client):
    archived = Group.objects.create(name="ArchivedDetail", parent_id=0, is_delete=True)
    resp = super_client.get(f"{BASE}/get_detail/?group_id={archived.id}")
    body = resp.json()
    assert body["result"] is False
    assert "ArchivedDetail" not in str(body)


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


def test_create_group_under_synced_group_is_rejected(super_client, user_sync_source):
    synced_root = Group.objects.create(name="同步根组织", parent_id=0, sync_source=user_sync_source)

    response = super_client.post(
        f"{BASE}/create_group/",
        {"group_name": "不允许手动新增的子组织", "parent_group_id": synced_root.id},
        format="json",
    )

    assert response.json()["result"] is False
    assert not Group.objects.filter(name="不允许手动新增的子组织", parent_id=synced_root.id).exists()


def test_create_group_under_archived_parent_is_rejected(super_client):
    archived_parent = Group.objects.create(name="ArchivedParent", parent_id=0, is_delete=True)

    response = super_client.post(
        f"{BASE}/create_group/",
        {"group_name": "归档下子组", "parent_group_id": archived_parent.id},
        format="json",
    )

    body = response.json()
    assert body["result"] is False
    assert "archived" in body["message"].lower() or "归档" in body["message"]
    assert not Group.objects.filter(name="归档下子组", parent_id=archived_parent.id).exists()


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


def test_update_group_rejects_archived(super_client):
    archived = Group.objects.create(name="ArchivedUpdate", parent_id=0, is_delete=True)
    resp = super_client.post(
        f"{BASE}/update_group/",
        {"group_id": archived.id, "group_name": "ShouldNotRename", "role_ids": []},
        format="json",
    )
    archived.refresh_from_db()
    assert resp.json()["result"] is False
    assert archived.name == "ArchivedUpdate"
    assert archived.is_delete is True


def test_update_group_invalidates_descendant_users(super_client):
    parent = Group.objects.create(name="UpdateParent", parent_id=0, allow_inherit_roles=True)
    child = Group.objects.create(name="UpdateChild", parent_id=parent.id)
    User.objects.create(
        username="update-descendant",
        password="x",
        display_name="Descendant",
        email="descendant@x.com",
        group_list=[child.id],
    )

    with patch("apps.system_mgmt.viewset.group_viewset.clear_users_permission_cache") as clear_cache:
        resp = super_client.post(
            f"{BASE}/update_group/",
            {"group_id": parent.id, "group_name": parent.name, "role_ids": []},
            format="json",
        )

    assert resp.json()["result"] is True
    affected_users = clear_cache.call_args.args[0]
    assert {user["username"] for user in affected_users} == {"update-descendant"}


def test_update_group_default_protected(super_client):
    Group.objects.filter(name="Default", parent_id=0).delete()
    g = Group.objects.create(name="Default", parent_id=0)
    resp = super_client.post(
        f"{BASE}/update_group/", {"group_id": g.id, "group_name": "x"}, format="json"
    )
    assert resp.json()["result"] is False


@pytest.fixture
def user_sync_source(db):
    instance = IntegrationInstance.objects.create(
        name="group-guard-source-instance",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready"},
        config={},
    )
    return UserSyncSource.objects.create(
        name="group-guard-source",
        integration_instance=instance,
        root_group_name="同步根组织",
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
    )


def test_update_synced_root_group_updates_sync_source_name(super_client, user_sync_source):
    root = Group.objects.create(name="同步根组织", parent_id=0, sync_source=user_sync_source)

    response = super_client.post(
        f"{BASE}/update_group/",
        {"group_id": root.id, "group_name": "已改名根组织", "role_ids": []},
        format="json",
    )

    user_sync_source.refresh_from_db()
    assert response.json()["result"] is True
    assert user_sync_source.root_group_name == "已改名根组织"


def test_update_synced_child_group_rejects_name_change(super_client, user_sync_source):
    root = Group.objects.create(name="同步根组织", parent_id=0, sync_source=user_sync_source)
    child = Group.objects.create(name="外部子组织", parent_id=root.id, sync_source=user_sync_source)

    response = super_client.post(
        f"{BASE}/update_group/",
        {"group_id": child.id, "group_name": "不允许的新名称", "role_ids": []},
        format="json",
    )

    child.refresh_from_db()
    assert response.json()["result"] is False
    assert child.name == "外部子组织"


# ---------------------------------------------------------------------------
# delete_groups
# ---------------------------------------------------------------------------
def test_delete_groups_with_children(super_client):
    parent = Group.objects.create(name="DelParent", parent_id=0)
    child = Group.objects.create(name="DelChild", parent_id=parent.id)
    resp = super_client.post(f"{BASE}/delete_groups/", {"id": parent.id}, format="json")
    assert resp.json()["result"] is True
    parent.refresh_from_db()
    child.refresh_from_db()
    assert parent.is_delete is True
    assert child.is_delete is True
    assert Group.objects.filter(id__in=[parent.id, child.id]).count() == 2


def test_delete_groups_default_protected(super_client):
    Group.objects.filter(name="Default", parent_id=0).delete()
    g = Group.objects.create(name="Default", parent_id=0)
    resp = super_client.post(f"{BASE}/delete_groups/", {"id": g.id}, format="json")
    assert resp.json()["result"] is False
    g.refresh_from_db()
    assert g.is_delete is False


def test_delete_groups_virtual_top_protected(super_client):
    g = Group.objects.create(name="VTopDel", parent_id=0, is_virtual=True)
    resp = super_client.post(f"{BASE}/delete_groups/", {"id": g.id}, format="json")
    assert resp.json()["result"] is False
    g.refresh_from_db()
    assert g.is_delete is False
    assert Group.objects.filter(id=g.id).exists()


def test_delete_synced_group_is_rejected(super_client, user_sync_source):
    root = Group.objects.create(name="同步根组织", parent_id=0, sync_source=user_sync_source)

    response = super_client.post(f"{BASE}/delete_groups/", {"id": root.id}, format="json")

    assert response.json()["result"] is False
    root.refresh_from_db()
    assert root.is_delete is False
    assert Group.objects.filter(id=root.id).exists()


def test_delete_groups_allows_user_with_other_active_group(super_client):
    parent = Group.objects.create(name="DelKeepUser", parent_id=0)
    other = Group.objects.create(name="DelOtherActive", parent_id=0)
    User.objects.create(
        username="del-keep",
        password="x",
        display_name="Del Keep",
        email="del-keep@x.com",
        group_list=[parent.id, other.id],
    )

    resp = super_client.post(f"{BASE}/delete_groups/", {"id": parent.id}, format="json")

    assert resp.json()["result"] is True
    parent.refresh_from_db()
    assert parent.is_delete is True
    user = User.objects.get(username="del-keep")
    assert parent.id in user.group_list
    assert other.id in user.group_list


def test_delete_groups_rejects_when_user_has_no_other_active_group(super_client):
    g = Group.objects.create(name="DelOnlyGroup", parent_id=0)
    User.objects.create(
        username="del-lonely",
        password="x",
        display_name="Del Lonely",
        email="del-lonely@x.com",
        group_list=[g.id],
    )

    resp = super_client.post(f"{BASE}/delete_groups/", {"id": g.id}, format="json")

    assert resp.json()["result"] is False
    g.refresh_from_db()
    assert g.is_delete is False


# ---------------------------------------------------------------------------
# archived list / restore / permanent delete
# ---------------------------------------------------------------------------
def test_list_restore_permanent_delete_archived_groups_api(super_client):
    root = Group.objects.create(name="ApiArchRoot", parent_id=0, is_delete=True)
    child = Group.objects.create(name="ApiArchChild", parent_id=root.id, is_delete=True)
    other = Group.objects.create(name="ApiArchOther", parent_id=0, is_delete=False)
    User.objects.create(
        username="api-arch-user",
        password="x",
        display_name="Api Arch",
        email="api-arch@x.com",
        group_list=[root.id, other.id],
    )

    listed = super_client.get(f"{BASE}/list_archived_groups/")
    assert listed.status_code == 200
    payload = listed.json()["data"]
    data = payload["items"]
    assert payload["count"] >= 1
    matched = next(item for item in data if item["id"] == root.id)
    assert matched["kind"] == "local"
    assert matched["can_restore"] is True
    assert matched["can_permanently_delete"] is True
    assert matched["children"][0]["id"] == child.id

    restored = super_client.post(f"{BASE}/restore_archived_groups/", {"id": root.id}, format="json")
    assert restored.json()["result"] is True
    root.refresh_from_db()
    child.refresh_from_db()
    assert root.is_delete is False and child.is_delete is False

    # 再归档后永久删除
    assert super_client.post(f"{BASE}/delete_groups/", {"id": root.id}, format="json").json()["result"] is True
    deleted = super_client.post(
        f"{BASE}/permanently_delete_archived_groups/", {"id": root.id}, format="json"
    )
    assert deleted.json()["result"] is True
    assert not Group.objects.filter(id__in=[root.id, child.id]).exists()
    user = User.objects.get(username="api-arch-user")
    assert user.group_list == [other.id]


def test_list_archived_groups_rejects_oversized_page(super_client):
    resp = super_client.get(f"{BASE}/list_archived_groups/?page_size=101")
    assert resp.status_code == 400
    assert resp.json()["result"] is False


def test_delete_groups_rejects_invalid_id(super_client):
    resp = super_client.post(f"{BASE}/delete_groups/", {"id": "abc"}, format="json")
    assert resp.status_code == 400
    assert resp.json()["result"] is False


def test_delete_groups_forbidden_returns_403():
    from apps.base.models import User as BaseUser

    allowed = Group.objects.create(name="member-allowed", parent_id=0)
    target = Group.objects.create(name="member-forbidden", parent_id=0)
    member = BaseUser.objects.create_user(username="arch-member", password="pw", domain="domain.com", locale="en")
    member.is_superuser = False
    member.group_list = [{"id": allowed.id, "name": allowed.name}]
    member.save()
    member.permission = {"system-manager": {"user_group-Delete Group"}}
    client = APIClient()
    client.force_authenticate(user=member)
    resp = client.post(f"{BASE}/delete_groups/", {"id": target.id}, format="json")
    assert resp.status_code == 403
    assert resp.json()["result"] is False


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


@pytest.mark.parametrize("batch", [False, True])
def test_group_detail_with_roles_skips_archived_parents(super_client, batch):
    role_archived = Role.objects.create(name="r-arch", app="cmdb")
    role_active = Role.objects.create(name="r-active", app="cmdb")
    archived_parent = Group.objects.create(
        name="ArchRP", parent_id=0, allow_inherit_roles=True, is_delete=True
    )
    archived_parent.roles.add(role_archived)
    mid = Group.objects.create(name="MidRP", parent_id=archived_parent.id, allow_inherit_roles=True)
    mid.roles.add(role_active)
    child = Group.objects.create(name="ChildRP", parent_id=mid.id)

    if batch:
        resp = super_client.post(
            f"{BASE}/batch_get_group_detail_with_roles/",
            {"group_ids": [child.id]},
            format="json",
        )
        assert resp.json()["result"] is True
        data = resp.json()["data"][0]
    else:
        resp = super_client.post(
            f"{BASE}/get_group_detail_with_roles/", {"group_id": child.id}, format="json"
        )
        data = resp.json()["data"]

    assert role_active.id in data["inherited_role_ids"]
    assert role_archived.id not in data["inherited_role_ids"]
    assert str(role_archived.id) not in data["inherited_role_source_map"]


def test_get_group_detail_with_roles_not_found(super_client):
    resp = super_client.post(
        f"{BASE}/get_group_detail_with_roles/", {"group_id": 999999}, format="json"
    )
    assert resp.json()["result"] is False


def test_get_group_detail_with_roles_hides_archived(super_client):
    archived = Group.objects.create(name="ArchivedRoles", parent_id=0, is_delete=True)
    resp = super_client.post(
        f"{BASE}/get_group_detail_with_roles/", {"group_id": archived.id}, format="json"
    )
    body = resp.json()
    assert body["result"] is False
    assert "ArchivedRoles" not in str(body)


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
