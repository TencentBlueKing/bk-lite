"""MemoryViewSet.list 个人记忆可见性过滤 + MemorySpaceViewSet.workflow_options 真实测试。

直接调用 @HasPermission 包裹保留的 __wrapped__ 原函数（绕过权限装饰器），
viewset 用真实 DRF 装配（request/kwargs/format_kwarg + 真实分页/序列化器），
真实落 PG 隔离库，断言：

MemoryViewSet.list：
  - 团队空间(scope=team)记忆对任意用户可见；
  - 个人空间(scope=personal)记忆仅 owner_username+owner_domain 匹配的用户可见；
  - 非匹配用户看不到他人个人记忆；
  - filterset_fields=memory_space 真实生效（按空间过滤）。

MemorySpaceViewSet.workflow_options：
  - 返回全部记忆空间(不按 team 过滤)，仅含 id/name/scope/default_model 字段，按 -id。
"""
import pydantic.root_model  # noqa  预热避免 mcp 导入崩溃

import json
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory

from apps.opspilot.models.memory_mgmt import Memory, MemorySpace
from apps.opspilot.viewsets.memory_view import MemorySpaceViewSet, MemoryViewSet

pytestmark = pytest.mark.django_db

_list = MemoryViewSet.list.__wrapped__
_workflow_options = MemorySpaceViewSet.workflow_options.__wrapped__

_factory = APIRequestFactory()


def _make_list_viewset(user, query_params=None):
    vs = MemoryViewSet()
    vs.action_map = {"get": "list"}
    vs.kwargs = {}
    vs.format_kwarg = None
    drf_request = vs.initialize_request(_factory.get("/", query_params or {}))
    drf_request.user = user
    vs.request = drf_request
    return vs


def _user(username, domain):
    return SimpleNamespace(username=username, domain=domain, is_superuser=True)


def _resp_data(response):
    """list 返回可能是 JsonResponse 或 DRF 分页 Response。"""
    if hasattr(response, "content"):
        body = json.loads(response.content.decode("utf-8"))
        return body.get("data", body)
    return response.data


# ---------------------------------------------------------------------------
# 数据准备
# ---------------------------------------------------------------------------
@pytest.fixture
def spaces_and_memories():
    team_space = MemorySpace.objects.create(name="团队空间", scope=MemorySpace.SCOPE_TEAM, team=[1])
    personal_space = MemorySpace.objects.create(name="个人空间", scope=MemorySpace.SCOPE_PERSONAL, team=[1])

    team_mem = Memory.objects.create(
        memory_space=team_space, title="团队记忆", content="c", owner_username="alice", owner_domain="d.com"
    )
    alice_mem = Memory.objects.create(
        memory_space=personal_space, title="Alice个人记忆", content="c", owner_username="alice", owner_domain="d.com"
    )
    bob_mem = Memory.objects.create(
        memory_space=personal_space, title="Bob个人记忆", content="c", owner_username="bob", owner_domain="d.com"
    )
    return SimpleNamespace(
        team_space=team_space,
        personal_space=personal_space,
        team_mem=team_mem,
        alice_mem=alice_mem,
        bob_mem=bob_mem,
    )


def test_list_alice_sees_team_and_own_personal_only(spaces_and_memories):
    vs = _make_list_viewset(_user("alice", "d.com"))
    resp = _list(vs, vs.request)
    data = _resp_data(resp)
    titles = {m["title"] for m in data}
    # 团队记忆 + 自己的个人记忆可见；他人个人记忆不可见
    assert "团队记忆" in titles
    assert "Alice个人记忆" in titles
    assert "Bob个人记忆" not in titles


def test_list_bob_cannot_see_alice_personal(spaces_and_memories):
    vs = _make_list_viewset(_user("bob", "d.com"))
    data = _resp_data(_list(vs, vs.request))
    titles = {m["title"] for m in data}
    assert "团队记忆" in titles
    assert "Bob个人记忆" in titles
    assert "Alice个人记忆" not in titles


def test_list_domain_mismatch_hides_personal(spaces_and_memories):
    """同名不同域不应看到他域的个人记忆。"""
    vs = _make_list_viewset(_user("alice", "other.com"))
    data = _resp_data(_list(vs, vs.request))
    titles = {m["title"] for m in data}
    assert "团队记忆" in titles  # 团队记忆与域无关
    assert "Alice个人记忆" not in titles  # alice@d.com 的记忆对 alice@other.com 不可见


def test_list_filter_by_memory_space(spaces_and_memories):
    """filterset_fields=memory_space 真实过滤：只看团队空间时只剩团队记忆。"""
    vs = _make_list_viewset(
        _user("alice", "d.com"), query_params={"memory_space": spaces_and_memories.team_space.id}
    )
    data = _resp_data(_list(vs, vs.request))
    titles = {m["title"] for m in data}
    assert titles == {"团队记忆"}


def test_list_user_without_domain_attr_uses_empty(spaces_and_memories):
    """用户对象无 domain 属性时按空域处理，匹配 owner_domain='' 的个人记忆。"""
    empty_domain_space = spaces_and_memories.personal_space
    Memory.objects.create(
        memory_space=empty_domain_space, title="无域个人记忆", content="c", owner_username="carol", owner_domain=""
    )
    user = SimpleNamespace(username="carol", is_superuser=True)  # 无 domain 属性
    vs = _make_list_viewset(user)
    data = _resp_data(_list(vs, vs.request))
    titles = {m["title"] for m in data}
    assert "无域个人记忆" in titles
    assert "Alice个人记忆" not in titles


# ---------------------------------------------------------------------------
# workflow_options
# ---------------------------------------------------------------------------
def test_workflow_options_returns_all_spaces_minimal_fields(spaces_and_memories):
    vs = MemorySpaceViewSet()
    vs.action_map = {"get": "workflow_options"}
    request = vs.initialize_request(_factory.get("/"))
    resp = _workflow_options(vs, request)

    body = json.loads(resp.content.decode("utf-8"))
    assert body["result"] is True
    data = body["data"]
    # 两个空间都返回（不按 team 过滤）
    names = {s["name"] for s in data}
    assert {"团队空间", "个人空间"}.issubset(names)
    # 仅暴露最小字段集
    assert set(data[0].keys()) == {"id", "name", "scope", "default_model"}
    # 按 -id 倒序
    ids = [s["id"] for s in data]
    assert ids == sorted(ids, reverse=True)
