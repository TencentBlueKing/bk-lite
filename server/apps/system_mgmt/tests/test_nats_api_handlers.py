"""apps/system_mgmt/nats_api.py 处理函数单元测试。

nats handler 直接可调用（@nats_client.register 返回原函数）。
只 mock 真实外部边界（cache、send_msg、jwt token 验证等），断言真实 DB 行为与返回结构。
"""
import types

import nats_client
import pytest

from apps.system_mgmt import nats_api
from apps.system_mgmt.models import (
    App,
    Channel,
    Group,
    GroupDataRule,
    Menu,
    Role,
    User,
)
from apps.system_mgmt.models.channel import ChannelChoices

pytestmark = pytest.mark.django_db


def test_nats_api_compat_exports_all_nats_entrypoints():
    expected_entrypoints = {
        "get_pilot_permission_by_token",
        "verify_token",
        "revoke_token",
        "get_user_menus",
        "get_client",
        "get_client_detail",
        "get_group_users",
        "get_group_users_scoped",
        "get_authorized_groups_scoped",
        "get_all_users",
        "search_groups",
        "search_users",
        "init_user_default_attributes",
        "create_guest_role",
        "create_default_rule",
        "get_all_groups",
        "get_channel_detail",
        "search_channel_list",
        "search_channel_list_scoped",
        "send_msg_with_channel",
        "_list_opspilot_nats_channels",
        "sync_opspilot_nats_channels",
        "delete_opspilot_nats_channels",
        "search_opspilot_nats_channels",
        "send_email_to_receiver",
        "get_user_rules",
        "get_user_rules_by_module",
        "get_user_rules_by_app",
        "get_group_id",
        "login",
        "reset_pwd",
        "wechat_user_register",
        "get_wechat_settings",
        "generate_qr_code_by_user_id",
        "verify_otp_code",
        "verify_otp_code_by_user_id",
        "verify_otp_login",
        "get_namespace_by_domain",
        "bk_lite_user_login",
        "get_login_module_domain_list",
        "delete_rules",
        "verify_bk_token",
        "save_error_log",
        "save_operation_log",
    }
    registered_entrypoints = expected_entrypoints - {"_list_opspilot_nats_channels"}

    exported_entrypoints = {name for name in expected_entrypoints if callable(getattr(nats_api, name, None))}
    actual_registered_entrypoints = {item["name"] for item in nats_client.default_registry.registry.values()}

    assert exported_entrypoints == expected_entrypoints
    assert registered_entrypoints <= actual_registered_entrypoints


# ---------------------------------------------------------------------------
# _collect_ancestor_group_ids / get_user_all_roles
# ---------------------------------------------------------------------------
def test_collect_ancestor_group_ids_empty():
    assert nats_api._collect_ancestor_group_ids([]) == set()


def test_collect_ancestor_group_ids_walks_up():
    g1 = Group.objects.create(name="A1", parent_id=0)
    g2 = Group.objects.create(name="A2", parent_id=g1.id)
    g3 = Group.objects.create(name="A3", parent_id=g2.id)
    result = nats_api._collect_ancestor_group_ids([g3.id])
    assert result == {g1.id, g2.id, g3.id}


def test_get_user_all_roles_personal_and_group_inherit():
    role_personal = Role.objects.create(name="r_personal", app="cmdb")
    role_group = Role.objects.create(name="r_group", app="cmdb")
    role_parent = Role.objects.create(name="r_parent", app="cmdb")

    parent = Group.objects.create(name="GP", parent_id=0, allow_inherit_roles=True)
    parent.roles.add(role_parent)
    child = Group.objects.create(name="GC", parent_id=parent.id, allow_inherit_roles=False)
    child.roles.add(role_group)

    user = User.objects.create(
        username="ru", password="x", display_name="ru", email="r@x.com",
        role_list=[role_personal.id], group_list=[child.id],
    )
    roles = set(nats_api.get_user_all_roles(user))
    # 个人角色 + 子组角色 + 继承的父组角色（父 allow_inherit_roles=True）
    assert {role_personal.id, role_group.id, role_parent.id} <= roles


def test_verify_token_regular_user_resolves_underscore_import(monkeypatch):
    """回归测试：apps/system_mgmt/nats/auth.py 通过 `from .common import *` 引入
    `_collect_ancestor_group_ids`，但 Python 的 import * 默认不导入下划线名字，
    导致非超管用户的 verify_token 在调用 _collect_ancestor_group_ids 时抛 NameError，
    上游 AuthBackend 捕获后返回 None → 前端表现为「登录持续过期」。

    触发链路：
        AuthBackend._verify_token_with_system_mgmt
          → SystemMgmt().verify_token (RPC)
            → apps.system_mgmt.nats.auth.verify_token
              → _collect_ancestor_group_ids(user.group_list)  ← NameError

    这里把 nats_api._verify_token 桩成 fake，强制走非超管分支
    （is_superuser=False → 必须调用 _collect_ancestor_group_ids）。
    """
    from apps.core.utils.permission_cache import clear_token_info_cache

    parent = Group.objects.create(name="VT_Parent", parent_id=0)
    user = User.objects.create(
        username="vt_regular", password="x", display_name="vt", email="vt@x.com",
        domain="domain.com", role_list=[], group_list=[parent.id],
    )
    # 避免 get_cached_token_info 命中旧数据
    clear_token_info_cache(user.username, user.domain)

    fake_user = types.SimpleNamespace(
        id=user.id,
        username=user.username,
        domain=user.domain,
        display_name=user.display_name,
        email=user.email,
        role_list=user.role_list,
        group_list=user.group_list,
        locale=user.locale,
        timezone=user.timezone,
    )
    # 同步到 _auth._verify_token（nats_api.verify_token 入口会 _sync_compat_globals）
    monkeypatch.setattr(nats_api, "_verify_token", lambda token: fake_user)

    # 修复前：此处抛 NameError: name '_collect_ancestor_group_ids' is not defined
    # 修复后：返回成功结果，且 group_list 含 user 直属组
    result = nats_api.verify_token("dummy-token")

    assert result["result"] is True, f"verify_token 应返回成功，实际: {result}"
    assert result["data"]["username"] == "vt_regular"
    assert any(g["id"] == parent.id for g in result["data"]["group_list"])


# ---------------------------------------------------------------------------
# get_client / get_client_detail
# ---------------------------------------------------------------------------
def test_get_client_all_apps():
    App.objects.create(name="appA", display_name="A", url="/a")
    App.objects.create(name="appB", display_name="B", url="/b")
    result = nats_api.get_client()
    assert result["result"] is True
    names = {a["name"] for a in result["data"]}
    assert {"appA", "appB"} <= names


def test_get_client_filter_by_client_id():
    App.objects.create(name="onlyme", display_name="X", url="/x")
    App.objects.create(name="other", display_name="Y", url="/y")
    result = nats_api.get_client(client_id="onlyme")
    names = {a["name"] for a in result["data"]}
    assert names == {"onlyme"}


def test_get_client_user_not_found():
    result = nats_api.get_client(username="nobody")
    assert result == {"result": False, "message": "User not found"}


def test_get_client_superuser_sees_all():
    App.objects.create(name="app1", display_name="1", url="/1")
    admin_role = Role.objects.create(name="admin", app="")
    User.objects.create(
        username="super", password="x", display_name="s", email="s@x.com",
        domain="domain.com", role_list=[admin_role.id], group_list=[],
    )
    result = nats_api.get_client(username="super")
    assert result["result"] is True
    assert any(a["name"] == "app1" for a in result["data"])


def test_get_client_detail_found_and_missing():
    App.objects.create(name="dc", display_name="DC", description="d", description_cn="中文", url="/dc")
    ok = nats_api.get_client_detail("dc")
    assert ok["result"] is True
    assert ok["data"]["name"] == "dc"
    assert ok["data"]["description_cn"] == "中文"
    missing = nats_api.get_client_detail("nope")
    assert missing == {"result": False, "message": "Client not found"}


# ---------------------------------------------------------------------------
# get_user_menus
# ---------------------------------------------------------------------------
def test_get_user_menus_superuser():
    Menu.objects.create(name="m1", display_name="M1-x", order=1, app="cmdb", menu_type="t")
    result = nats_api.get_user_menus("cmdb", roles=[], username="u", is_superuser=True)
    assert result["result"] is True
    assert isinstance(result["data"], list)


def test_get_user_menus_with_role_filter():
    m1 = Menu.objects.create(name="host-view", display_name="主机-查看-x", order=1, app="cmdb", menu_type="t")
    Menu.objects.create(name="host-edit", display_name="主机-编辑-x", order=2, app="cmdb", menu_type="t")
    role = Role.objects.create(name="viewer", app="cmdb", menu_list=[m1.id])
    result = nats_api.get_user_menus("cmdb", roles=[role.id], username="u", is_superuser=False)
    assert result["result"] is True
    # 仅 host-view 被授权
    flat = [c["name"] for grp in result["data"] for c in grp["children"]]
    assert "host" in flat


# ---------------------------------------------------------------------------
# get_group_users / get_all_users / search_*
# ---------------------------------------------------------------------------
def test_get_group_users_all():
    User.objects.create(username="gu1", password="x", display_name="g1", email="g1@x.com", group_list=[1])
    result = nats_api.get_group_users()
    assert result["result"] is True
    assert any(u["username"] == "gu1" for u in result["data"])


def test_get_group_users_by_group():
    g = Group.objects.create(name="GUG", parent_id=0)
    User.objects.create(username="ingrp", password="x", display_name="i", email="i@x.com", group_list=[g.id])
    User.objects.create(username="notin", password="x", display_name="n", email="n@x.com", group_list=[99999])
    result = nats_api.get_group_users(group=g.id)
    names = {u["username"] for u in result["data"]}
    assert "ingrp" in names and "notin" not in names


def test_get_all_users():
    User.objects.create(username="allu", password="x", display_name="A", email="a@x.com")
    result = nats_api.get_all_users()
    assert result["result"] is True
    assert any(u["username"] == "allu" for u in result["data"])


def test_search_groups():
    Group.objects.create(name="FindMeGroup", parent_id=0)
    Group.objects.create(name="OtherGrp", parent_id=0)
    result = nats_api.search_groups({"search": "FindMe"})
    names = {g["name"] for g in result["data"]}
    assert names == {"FindMeGroup"}


def test_search_users_pagination():
    for i in range(15):
        User.objects.create(username=f"su{i:02d}", password="x", display_name=f"S{i}", email=f"s{i}@x.com")
    result = nats_api.search_users({"page": 1, "page_size": 10, "search": "su"})
    assert result["result"] is True
    assert result["data"]["count"] >= 15
    assert len(result["data"]["users"]) == 10


def test_get_group_id():
    g = Group.objects.create(name="GidGroup", parent_id=0)
    result = nats_api.get_group_id("GidGroup")
    assert result["result"] is True
    assert result["data"] == g.id


# ---------------------------------------------------------------------------
# get_authorized_groups_scoped / _get_actor_user_scope
# ---------------------------------------------------------------------------
def test_actor_scope_missing_username_returns_empty():
    user_obj, groups = nats_api._get_actor_user_scope({"current_team": 1})
    assert user_obj is None and groups == []


def test_actor_scope_superuser():
    g = Group.objects.create(name="SG", parent_id=0)
    User.objects.create(username="sa", password="x", display_name="sa", email="sa@x.com", domain="domain.com")
    ctx = {"username": "sa", "domain": "domain.com", "current_team": g.id, "is_superuser": True}
    user_obj, groups = nats_api._get_actor_user_scope(ctx)
    assert user_obj is not None
    assert groups == [g.id]


def test_get_authorized_groups_scoped():
    g = Group.objects.create(name="AG", parent_id=0)
    User.objects.create(username="au", password="x", display_name="au", email="au@x.com", domain="domain.com")
    ctx = {"username": "au", "domain": "domain.com", "current_team": g.id, "is_superuser": True}
    result = nats_api.get_authorized_groups_scoped(ctx)
    assert result["result"] is True
    assert result["data"] == [g.id]


def test_get_group_users_scoped_no_scope_returns_empty():
    result = nats_api.get_group_users_scoped({"username": "x"})
    assert result == {"result": True, "data": []}


# ---------------------------------------------------------------------------
# create_guest_role / create_default_rule
# ---------------------------------------------------------------------------
def test_create_guest_role_creates_groups_and_roles():
    result = nats_api.create_guest_role()
    assert result["result"] is True
    assert Group.objects.filter(name="Guest", parent_id=0).exists()
    assert Group.objects.filter(name="OpsPilotGuest", parent_id=0).exists()
    assert Role.objects.filter(name="guest", app="opspilot").exists()


def test_create_default_rule_creates_rule():
    Group.objects.create(name="OpsPilotGuest", parent_id=0)
    result = nats_api.create_default_rule(
        llm_model={"id": 1, "name": "llm"},
        ocr_model=[{"id": 2, "name": "ocr"}],
        embed_model=[{"id": 3, "name": "embed"}],
        rerank_model={"id": 4, "name": "rerank"},
    )
    assert result == {"result": True}
    rule = GroupDataRule.objects.get(name="OpsPilot内置规则", app="opspilot")
    assert rule.rules["provider"]["llm_model"][0]["id"] == 1


# ---------------------------------------------------------------------------
# get_channel_detail / search_channel_list
# ---------------------------------------------------------------------------
def test_get_channel_detail_found_and_missing():
    ch = Channel.objects.create(
        name="mychan", channel_type=ChannelChoices.EMAIL, config={"k": "v"},
        description="d", team=[1, 2],
    )
    ok = nats_api.get_channel_detail(ch.id)
    assert ok["result"] is True
    assert ok["data"]["name"] == "mychan"
    assert ok["data"]["team"] == [1, 2]
    missing = nats_api.get_channel_detail(999999)
    assert missing["result"] is False


def test_search_channel_list_empty_teams():
    result = nats_api.search_channel_list(teams=None)
    assert result == {"result": True, "data": []}


def test_search_channel_list_filters_by_team_and_type():
    Channel.objects.create(name="c1", channel_type=ChannelChoices.EMAIL, config={}, description="d", team=[5])
    Channel.objects.create(name="c2", channel_type=ChannelChoices.EMAIL, config={}, description="d", team=[6])
    result = nats_api.search_channel_list(channel_type=ChannelChoices.EMAIL, teams=[5])
    names = {c["name"] for c in result["data"]}
    assert "c1" in names and "c2" not in names


def test_search_channel_list_include_children():
    parent = Group.objects.create(name="CParent", parent_id=0)
    child = Group.objects.create(name="CChild", parent_id=parent.id)
    Channel.objects.create(name="cc", channel_type=ChannelChoices.EMAIL, config={}, description="d", team=[child.id])
    result = nats_api.search_channel_list(teams=[parent.id], include_children=True)
    names = {c["name"] for c in result["data"]}
    assert "cc" in names


# ---------------------------------------------------------------------------
# send_email_to_receiver / send_msg_with_channel
# ---------------------------------------------------------------------------
def test_send_msg_with_channel_channel_not_found():
    result = nats_api.send_msg_with_channel(999999, "title", "content", ["a@x.com"])
    assert result["result"] is False


def test_get_wechat_settings():
    # 没有 wechat 配置时仍返回标准结构
    result = nats_api.get_wechat_settings()
    assert "result" in result


# ---------------------------------------------------------------------------
# revoke_token
# ---------------------------------------------------------------------------
def test_revoke_token_invalid():
    # 非法 token，解析失败 -> result False（异常被捕获）
    result = nats_api.revoke_token("Basic not-a-real-jwt")
    assert result["result"] is False
