"""Tests for system_mgmt NATS handler `get_user_group_tree`.

覆盖 11 条用例,直接走 @nats_client.register 暴露的入口 + RPC 客户端。

NOTE: handler 通过 `from .common import *` 拿到 `User` / `Group` / `GroupUtils` /
`logger` / `_collect_ancestor_group_ids`,此处直接 import handler 函数本体。
"""

import logging

import pytest
from django.contrib.auth.hashers import make_password

from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import Group, IntegrationInstance, User, UserSyncSource
from apps.system_mgmt.models.integration_instance import IntegrationInstanceStatusChoices
from apps.system_mgmt.nats.users import get_user_group_tree

logger = logging.getLogger(__name__)


# ----------------------------- 工具函数 ---------------------------------- #


def _make_integration_instance(name="ldap-test", provider_key="ldap"):
    """UserSyncSource 需要 IntegrationInstance 作为 FK。"""
    return IntegrationInstance.objects.create(
        name=name,
        provider_key=provider_key,
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"user_sync": "ready"},
        capability_enabled={"user_sync": True},
        enabled=True,
    )


def _make_sync_source(instance=None, name="ad-source"):
    instance = instance or _make_integration_instance()
    return UserSyncSource.objects.create(
        name=name,
        integration_instance=instance,
        enabled=True,
        root_group_name="Default",
    )


def _make_user(username, group_list=None, sync_source=None, domain="domain.com"):
    return User.objects.create(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        password=make_password("password123"),
        domain=domain,
        group_list=group_list or [],
        sync_source=sync_source,
    )


# 树节点字段白名单
ALLOWED_TREE_KEYS = {"id", "name", "subGroupCount", "subGroups", "hasAuth", "role_ids", "is_virtual", "parentId"}


def _collect_tree_keys(nodes, acc):
    for n in nodes:
        acc.update(n.keys())
        _collect_tree_keys(n.get("subGroups") or [], acc)


# ----------------------------- 用例 --------------------------------------- #


@pytest.mark.django_db
def test_case_01_normal_returns_tree_with_auth_leaf():
    """用例 1:单一命中,group_list 包含 1 个组,该组父级也在树中,叶子 hasAuth=True,父级 False。"""
    src = _make_sync_source()
    parent = Group.objects.create(name="Default", parent_id=0)
    child = Group.objects.create(name="Ops", parent_id=parent.id)
    user = _make_user("alice", group_list=[child.id], sync_source=src)

    res = get_user_group_tree("alice", src.id)

    assert res["result"] is True
    data = res["data"]
    assert data["user_id"] == user.id
    assert data["username"] == "alice"
    assert data["domain"] == "domain.com"
    assert data["group_list"] == [child.id]
    # 树中应该包含父级和叶子
    assert len(data["group_tree"]) == 1
    root = data["group_tree"][0]
    assert root["id"] == parent.id
    assert root["hasAuth"] is False
    assert len(root["subGroups"]) == 1
    leaf = root["subGroups"][0]
    assert leaf["id"] == child.id
    assert leaf["hasAuth"] is True


@pytest.mark.django_db
def test_case_02_empty_group_list_returns_empty_tree():
    """用例 2:group_list=[] 时 group_tree=[]。"""
    src = _make_sync_source()
    _make_user("bob", group_list=[], sync_source=src)

    res = get_user_group_tree("bob", src.id)

    assert res["result"] is True
    assert res["data"]["group_list"] == []
    assert res["data"]["group_tree"] == []


@pytest.mark.django_db
def test_case_03_user_not_found():
    """用例 3:用户不存在。"""
    src = _make_sync_source()
    _make_user("carol", sync_source=src)

    res = get_user_group_tree("ghost", src.id)

    assert res["result"] is False
    assert res["message"] == "user not found"


@pytest.mark.django_db
def test_case_04_multiple_users_match_returns_error_with_count():
    """用例 4:多个用户匹配(同 username + sync_source_id)。"""
    src = _make_sync_source()
    # User 的 unique_together=("username","domain"),同 domain 下只能唯一;
    # 通过不同 domain 制造两个同名同 sync_source_id 的记录
    _make_user("dave", sync_source=src, domain="domain.com")
    _make_user("dave", sync_source=src, domain="other.com")

    res = get_user_group_tree("dave", src.id)

    assert res["result"] is False
    assert "got 2" in res["message"]


@pytest.mark.django_db
def test_case_05_missing_username():
    """用例 5:username 缺失/空串。"""
    src = _make_sync_source()

    for bad in (None, ""):
        res = get_user_group_tree(bad, src.id)
        assert res["result"] is False
        assert res["message"] == "username is required"


@pytest.mark.django_db
def test_case_06_invalid_sync_source_id():
    """用例 6/7:sync_source_id 非整数强转失败;字符串数字应被接受。"""
    src = _make_sync_source()
    Group.objects.create(name="X", parent_id=0)
    _make_user("eve", group_list=[], sync_source=src)

    res_bad = get_user_group_tree("eve", "abc")
    assert res_bad["result"] is False
    assert res_bad["message"] == "invalid sync_source_id"

    # 用例 7:字符串数字应被接受
    res_str = get_user_group_tree("eve", str(src.id))
    assert res_str["result"] is True
    assert res_str["data"]["username"] == "eve"


@pytest.mark.django_db
def test_case_08_group_list_with_string_numbers_is_coerced():
    """用例 8:group_list 含 str 数字(JSONField 脏数据),应被强转后命中。"""
    src = _make_sync_source()
    g = Group.objects.create(name="Coerce", parent_id=0)
    # JSONField 直接存字符串数字
    _make_user("frank", group_list=[str(g.id)], sync_source=src)

    res = get_user_group_tree("frank", src.id)

    assert res["result"] is True
    assert res["data"]["group_list"] == [g.id]
    assert any(node["id"] == g.id for node in res["data"]["group_tree"])


@pytest.mark.django_db
def test_case_09_exception_is_swallowed_and_logged(monkeypatch, caplog):
    """用例 9:数据库异常被兜底,result=False 且 logger.exception 被调用。"""
    src = _make_sync_source()
    parent = Group.objects.create(name="P", parent_id=0)
    _make_user("grace", group_list=[parent.id], sync_source=src)

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    # 直接在 handler 内部命名空间上替换 GroupUtils.build_group_tree,
    # 触达 try/except 内部异常分支
    from apps.system_mgmt.nats import users as users_module

    monkeypatch.setattr(users_module.GroupUtils, "build_group_tree", boom)

    with caplog.at_level(logging.ERROR, logger="system_mgmt"):
        res = get_user_group_tree("grace", src.id)

    assert res["result"] is False
    assert "internal error" in res["message"]
    # logger.exception 至少产生一条 ERROR 记录
    assert any("db down" in rec.getMessage() or "db down" in str(rec.exc_info) for rec in caplog.records)


@pytest.mark.django_db
def test_case_local_user_with_none_sync_source_id():
    """新增:本地用户 sync_source=None,接口同步支持 sync_source_id=None 走 sync_source__isnull=True。"""
    parent = Group.objects.create(name="LocalParent", parent_id=0)
    child = Group.objects.create(name="LocalChild", parent_id=parent.id)
    # _make_user 的 sync_source 缺省 = None,模拟本地用户
    user = _make_user("localuser", group_list=[child.id])

    # 显式 None
    res_none = get_user_group_tree("localuser", None)
    assert res_none["result"] is True
    assert res_none["data"]["user_id"] == user.id
    assert res_none["data"]["group_list"] == [child.id]
    assert len(res_none["data"]["group_tree"]) == 1
    assert res_none["data"]["group_tree"][0]["subGroups"][0]["id"] == child.id

    # 不传 sync_source_id(走默认 None)
    res_default = get_user_group_tree("localuser")
    assert res_default["result"] is True
    assert res_default["data"]["user_id"] == user.id

    # 显式空串 —— 与 None 等价
    res_empty = get_user_group_tree("localuser", "")
    assert res_empty["result"] is True
    assert res_empty["data"]["user_id"] == user.id
    assert res_empty["data"]["group_list"] == [child.id]
    assert len(res_empty["data"]["group_tree"]) == 1
    assert res_empty["data"]["group_tree"][0]["subGroups"][0]["id"] == child.id

    # 同步源用户不能用 None/空串命中(避免跨源冲突)
    src = _make_sync_source()
    _make_user("synced", group_list=[], sync_source=src)
    res_miss = get_user_group_tree("synced", None)
    assert res_miss["result"] is False
    assert res_miss["message"] == "user not found"
    res_miss_empty = get_user_group_tree("synced", "")
    assert res_miss_empty["result"] is False
    assert res_miss_empty["message"] == "user not found"


@pytest.mark.django_db
def test_case_10_tree_node_keys_are_whitelisted():
    """用例 10:group_tree 节点字段白名单(防止 GroupUtils 改动扩散)。"""
    src = _make_sync_source()
    parent = Group.objects.create(name="P", parent_id=0)
    child = Group.objects.create(name="C", parent_id=parent.id)
    _make_user("helen", group_list=[child.id], sync_source=src)

    res = get_user_group_tree("helen", src.id)
    assert res["result"] is True

    keys = set()
    _collect_tree_keys(res["data"]["group_tree"], keys)
    assert keys.issubset(ALLOWED_TREE_KEYS), f"unexpected keys: {keys - ALLOWED_TREE_KEYS}"


@pytest.mark.django_db
def test_case_11_rpc_get_user_group_tree_passes_kwargs(monkeypatch):
    """用例 11:RPC 入口 SystemMgmt.get_user_group_tree 关键字透传到 NATS 主题。"""
    src = _make_sync_source()
    _make_user("ivan", sync_source=src)

    captured = {}

    def fake_run(self, subject, **kwargs):
        captured["subject"] = subject
        captured["kwargs"] = kwargs
        return {"result": True, "data": {"echo": True}}

    # monkeypatch AppClient.run 拦截 RPC 调用
    from apps.rpc import base as rpc_base

    monkeypatch.setattr(rpc_base.AppClient, "run", fake_run)

    rpc = SystemMgmt(is_local_client=False)
    out = rpc.get_user_group_tree("ivan", src.id)

    assert out == {"result": True, "data": {"echo": True}}
    assert captured["subject"] == "get_user_group_tree"
    assert captured["kwargs"] == {"username": "ivan", "sync_source_id": src.id}
