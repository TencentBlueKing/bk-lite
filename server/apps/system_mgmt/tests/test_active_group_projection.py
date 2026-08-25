"""活动组织投影：正常使用路径默认排除 is_delete=True。"""

import types

import pytest
from rest_framework.exceptions import PermissionDenied

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.system_mgmt.models import Channel, ChannelChoices, Group, Role, User
from apps.system_mgmt.nats.auth import build_user_authorization_context
from apps.system_mgmt.nats.channels import search_channel_list, search_opspilot_nats_channels
from apps.system_mgmt.nats.common import _collect_ancestor_group_ids, get_user_all_roles
from apps.system_mgmt.nats.users import get_archived_groups, get_assignable_groups, get_group_id, search_groups
from apps.system_mgmt.utils.group_filter_mixin import GroupFilterMixin
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.system_mgmt.viewset.user_viewset import _merge_retained_archived_groups, _validate_selected_groups

pytestmark = [pytest.mark.django_db]


@pytest.fixture
def active_and_archived():
    active = Group.objects.create(name="proj-active", parent_id=0, is_delete=False)
    archived = Group.objects.create(name="proj-archived", parent_id=0, is_delete=True)
    archived_child = Group.objects.create(name="proj-arch-child", parent_id=archived.id, is_delete=True)
    active_child = Group.objects.create(name="proj-active-child", parent_id=active.id, is_delete=False)
    return {
        "active": active,
        "archived": archived,
        "archived_child": archived_child,
        "active_child": active_child,
    }


def _make_user(username, *, group_list, role_ids=None):
    return User.objects.create(
        username=username,
        password="x",
        display_name=username,
        email=f"{username}@example.com",
        domain="domain.com",
        group_list=group_list,
        role_list=role_ids or [],
    )


def _tree_ids(nodes):
    ids = set()
    for node in nodes:
        ids.add(node["id"])
        ids.update(_tree_ids(node.get("subGroups") or []))
    return ids


@pytest.mark.parametrize("as_superuser", [False, True])
def test_assignable_groups_excludes_archived(active_and_archived, as_superuser):
    groups = active_and_archived
    role_ids = [Role.objects.create(name="admin", app="").id] if as_superuser else []
    group_list = [] if as_superuser else [groups["active"].id, groups["archived"].id]
    _make_user(f"assign-{'su' if as_superuser else 'n'}", group_list=group_list, role_ids=role_ids)

    result = get_assignable_groups(
        {"username": f"assign-{'su' if as_superuser else 'n'}", "domain": "domain.com"}
    )

    assert result["result"] is True
    assert groups["active"].id in result["data"]
    assert groups["archived"].id not in result["data"]
    if not as_superuser:
        assert groups["active_child"].id in result["data"]
        assert groups["archived_child"].id not in result["data"]


def test_search_groups_excludes_archived(active_and_archived):
    groups = active_and_archived
    result = search_groups({"search": "proj-"})
    names = {g["name"] for g in result["data"]}
    ids = {g["id"] for g in result["data"]}
    assert {"proj-active", "proj-active-child"} <= names
    assert "proj-archived" not in names and "proj-arch-child" not in names
    assert groups["archived"].id not in ids


@pytest.mark.parametrize("as_superuser", [False, True])
def test_auth_context_excludes_archived(active_and_archived, as_superuser):
    groups = active_and_archived
    role_ids = [Role.objects.create(name="admin", app="").id] if as_superuser else []
    group_list = [] if as_superuser else [groups["active"].id, groups["archived"].id]
    user = _make_user(f"auth-{'su' if as_superuser else 'n'}", group_list=group_list, role_ids=role_ids)

    ctx = build_user_authorization_context(user)
    group_ids = {g["id"] for g in ctx["group_list"]}
    assert groups["active"].id in group_ids
    assert groups["archived"].id not in group_ids
    if as_superuser:
        assert ctx["is_superuser"] is True
    else:
        assert groups["archived"].id not in _tree_ids(ctx["group_tree"])


@pytest.mark.parametrize(
    "team_id_factory",
    [
        lambda groups: groups["archived"].id,
        lambda groups: 9_999_991,
    ],
    ids=["archived", "missing"],
)
def test_current_team_rejects_archived_or_missing(active_and_archived, monkeypatch, team_id_factory):
    from apps.core.utils.current_team_scope import resolve_current_team_data_scope

    team_id = team_id_factory(active_and_archived)

    class _SystemMgmt:
        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            return {"result": True, "data": [team_id]}

    monkeypatch.setattr("apps.core.utils.current_team_scope.SystemMgmt", _SystemMgmt)
    request = types.SimpleNamespace(
        COOKIES={"current_team": str(team_id), "include_children": "0"},
        user=types.SimpleNamespace(
            username="admin",
            domain="domain.com",
            group_list=[team_id],
            is_superuser=True,
        ),
    )
    with pytest.raises(BaseAppException, match="归档|不存在|不可用"):
        resolve_current_team_data_scope(request)


def test_group_utils_descendants_exclude_archived_by_default(active_and_archived):
    groups = active_and_archived
    orphan_archived = Group.objects.create(
        name="proj-orphan-arch", parent_id=groups["active"].id, is_delete=True
    )
    result = set(GroupUtils.get_group_with_descendants(groups["active"].id))
    assert result == {groups["active"].id, groups["active_child"].id}
    assert orphan_archived.id not in result
    assert GroupUtils.get_group_with_descendants(groups["archived"].id) == []


def test_group_utils_include_deleted_sees_archived_subtree(active_and_archived):
    groups = active_and_archived
    result = set(GroupUtils.get_group_with_descendants(groups["archived"].id, include_deleted=True))
    assert result == {groups["archived"].id, groups["archived_child"].id}


def test_user_edit_rejects_archived_group(active_and_archived):
    loader = types.SimpleNamespace(get=lambda key, default=None, **kwargs: default or key)
    groups = active_and_archived
    assert _validate_selected_groups([groups["archived"].id], loader) is not None
    assert _validate_selected_groups([groups["active"].id], loader) is None


def test_update_user_retains_archived_group_ids():
    import json

    from rest_framework.test import APIClient

    from apps.base.models import User as BaseUser
    from apps.system_mgmt.models import Role

    Role.objects.get_or_create(name="admin", app="")
    active = Group.objects.create(name="upd-active", parent_id=0)
    archived = Group.objects.create(name="upd-archived", parent_id=0, is_delete=True)
    extra = Group.objects.create(name="upd-extra", parent_id=0)
    target = _make_user("upd-target", group_list=[active.id, archived.id])

    assert _merge_retained_archived_groups([active.id, extra.id], target.group_list) == [
        active.id,
        extra.id,
        archived.id,
    ]

    admin = BaseUser.objects.create_user(username="upd-admin", password="pw", domain="domain.com", locale="en")
    admin.is_superuser = True
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)
    response = client.post(
        "/api/v1/system_mgmt/user/update_user/",
        {
            "user_id": target.id,
            "username": target.username,
            "lastName": target.display_name,
            "email": target.email,
            "phone": None,
            "locale": "en",
            "timezone": "Asia/Shanghai",
            "groups": [active.id, extra.id],
            "roles": [],
            "rules": [],
        },
        format="json",
    )
    data = response.json() if hasattr(response, "json") else json.loads(response.content.decode())
    assert response.status_code == 200
    assert data["result"] is True
    target.refresh_from_db()
    assert target.group_list == [active.id, extra.id, archived.id]

    rejected = client.post(
        "/api/v1/system_mgmt/user/update_user/",
        {
            "user_id": target.id,
            "username": target.username,
            "lastName": target.display_name,
            "email": target.email,
            "phone": None,
            "locale": "en",
            "timezone": "Asia/Shanghai",
            "groups": [active.id, archived.id],
            "roles": [],
            "rules": [],
        },
        format="json",
    )
    rejected_data = rejected.json() if hasattr(rejected, "json") else json.loads(rejected.content.decode())
    assert rejected_data["result"] is False
    target.refresh_from_db()
    assert target.group_list == [active.id, extra.id, archived.id]


def test_group_filter_mixin_rejects_archived_current_team(active_and_archived):
    archived_id = active_and_archived["archived"].id
    m = GroupFilterMixin()
    req = types.SimpleNamespace(
        user=types.SimpleNamespace(is_superuser=True, group_list=[{"id": archived_id}]),
        COOKIES={"current_team": str(archived_id)},
        META={},
    )
    with pytest.raises(PermissionDenied):
        m._validate_current_team_permission(req)


def test_role_inherit_skips_archived_groups_in_parent_chain(active_and_archived):
    groups = active_and_archived
    parent_role = Role.objects.create(name="parent-role-proj", app="system-manager")
    groups["archived"].roles.add(parent_role)
    active_child = Group.objects.create(
        name="proj-under-arch-then-active",
        parent_id=groups["archived"].id,
        is_delete=False,
    )
    user = _make_user("role-proj", group_list=[active_child.id])

    ancestor_ids = _collect_ancestor_group_ids([active_child.id])
    assert active_child.id in ancestor_ids
    assert groups["archived"].id not in ancestor_ids
    assert parent_role.id not in get_user_all_roles(user)


def test_get_group_users_excludes_archived_group():
    from apps.system_mgmt.nats.users import get_group_users

    active = Group.objects.create(name="nats-users-active", parent_id=0)
    archived = Group.objects.create(name="nats-users-archived", parent_id=0, is_delete=True)
    _make_user("in-active-group", group_list=[active.id])
    _make_user("in-archived-group", group_list=[archived.id])

    active_result = get_group_users(group=active.id, include_children=False)
    archived_result = get_group_users(group=archived.id, include_children=False)

    assert {u["username"] for u in active_result["data"]} == {"in-active-group"}
    assert archived_result["data"] == []


def test_get_user_all_roles_second_load_skips_archived_direct_group():
    archived = Group.objects.create(name="role-archived-direct", parent_id=0, is_delete=True)
    archived_role = Role.objects.create(name="archived-direct-role", app="system-manager")
    archived.roles.add(archived_role)
    user = _make_user("role-archived-direct-user", group_list=[archived.id])

    assert archived_role.id not in get_user_all_roles(user)


def test_get_group_id_skips_archived_root():
    archived = Group.objects.create(name="GidArchivedRoot", parent_id=0, is_delete=True)
    result = get_group_id("GidArchivedRoot")
    assert result["result"] is False
    assert archived.id != result.get("data")


def test_get_archived_groups_returns_all_archived_rows():
    active = Group.objects.create(name="mod-arch-active", parent_id=0)
    root = Group.objects.create(name="mod-arch-root", parent_id=0, is_delete=True)
    child = Group.objects.create(name="mod-arch-child", parent_id=root.id, is_delete=True)

    result = get_archived_groups(page=1, page_size=100)

    assert result["result"] is True
    ids = {item["id"] for item in result["data"]["items"]}
    names = {item["name"] for item in result["data"]["items"]}
    assert root.id in ids and child.id in ids
    assert active.id not in ids
    assert "mod-arch-root" in names and "mod-arch-child" in names
    assert result["data"]["count"] >= 2
    assert result["data"]["page"] == 1
    assert result["data"]["page_size"] == 100


def test_get_archived_groups_rejects_invalid_pagination():
    result = get_archived_groups(page="x", page_size=10)
    assert result["result"] is False
    result_zero = get_archived_groups(page=1, page_size=0)
    assert result_zero["result"] is False
    result_oversize = get_archived_groups(page=1, page_size=101)
    assert result_oversize["result"] is False
    assert result_oversize["message"] == "invalid pagination"


def test_get_user_detail_omits_archived_groups():
    import json

    from rest_framework.test import APIClient

    from apps.base.models import User as BaseUser

    active = Group.objects.create(name="detail-active", parent_id=0)
    archived = Group.objects.create(name="detail-archived", parent_id=0, is_delete=True)
    target = _make_user("detail-target", group_list=[active.id, archived.id])
    admin = BaseUser.objects.create_user(username="detail-admin", password="pw", domain="domain.com", locale="en")
    admin.is_superuser = True
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)
    response = client.post(
        "/api/v1/system_mgmt/user/get_user_detail/",
        {"user_id": target.id},
        format="json",
    )
    data = response.json() if hasattr(response, "json") else json.loads(response.content.decode())
    assert response.status_code == 200
    assert data["result"] is True
    assert {item["id"] for item in data["data"]["groups"]} == {active.id}


def _channel_tree_for_include_children(prefix):
    parent = Group.objects.create(name=f"{prefix}-parent", parent_id=0)
    active_child = Group.objects.create(name=f"{prefix}-active-child", parent_id=parent.id)
    archived_child = Group.objects.create(name=f"{prefix}-archived-child", parent_id=parent.id, is_delete=True)
    Channel.objects.create(
        name=f"{prefix}-on-archived",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="d",
        team=[archived_child.id],
    )
    Channel.objects.create(
        name=f"{prefix}-on-active-child",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="d",
        team=[active_child.id],
    )
    Channel.objects.create(
        name=f"{prefix}-opspilot-on-archived",
        channel_type=ChannelChoices.NATS,
        config={"source": "opspilot", "bot_id": 1, "node_id": "n1"},
        description="d",
        team=[archived_child.id],
    )
    Channel.objects.create(
        name=f"{prefix}-opspilot-on-active",
        channel_type=ChannelChoices.NATS,
        config={"source": "opspilot", "bot_id": 1, "node_id": "n2"},
        description="d",
        team=[active_child.id],
    )
    return parent, archived_child, prefix


def test_search_channel_list_include_children_skips_archived_child():
    parent, archived_child, prefix = _channel_tree_for_include_children("ch-list")

    result = search_channel_list(teams=[parent.id], include_children=True)
    names = {item["name"] for item in result["data"]}
    assert f"{prefix}-on-active-child" in names
    assert f"{prefix}-on-archived" not in names

    explicit = search_channel_list(teams=[archived_child.id], include_children=False)
    assert f"{prefix}-on-archived" in {item["name"] for item in explicit["data"]}


def test_search_opspilot_nats_channels_include_children_skips_archived_child():
    parent, archived_child, prefix = _channel_tree_for_include_children("ch-ops")

    result = search_opspilot_nats_channels(teams=[parent.id], include_children=True)
    names = {item["name"] for item in result["data"]}
    assert f"{prefix}-opspilot-on-active" in names
    assert f"{prefix}-opspilot-on-archived" not in names

    explicit = search_opspilot_nats_channels(teams=[archived_child.id], include_children=False)
    assert f"{prefix}-opspilot-on-archived" in {item["name"] for item in explicit["data"]}


def test_search_channel_list_include_children_archived_seed_returns_empty():
    archived = Group.objects.create(name="ch-arch-seed", parent_id=0, is_delete=True)
    other = Group.objects.create(name="ch-arch-other-active", parent_id=0)
    Channel.objects.create(
        name="ch-on-archived-seed",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="d",
        team=[archived.id],
    )
    Channel.objects.create(
        name="ch-on-other-active",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="d",
        team=[other.id],
    )

    result = search_channel_list(teams=[archived.id], include_children=True)
    assert result["result"] is True
    assert result["data"] == []
