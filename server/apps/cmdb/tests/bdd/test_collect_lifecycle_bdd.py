"""CMDB 采集任务调试状态机 BDD（中文 Gherkin）。

对照 spec/prd/CMDB·配置采集·调试：
- save_debug_state / get_debug_state 状态读写与 TTL；
- can_access_debug_state owner 鉴权；
- 状态流转中 owner 的保留语义；
- is_schedule_config_changed 触发条件。
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from pytest_bdd import given, parsers, scenarios, then, when

from apps.cmdb.services.collect_service import CollectModelService
from apps.cmdb.services.collect_tool_service import CollectToolService

FEATURE = str(Path(__file__).parent / "collect_lifecycle.feature")
scenarios(FEATURE)


@pytest.fixture
def ctx():
    return {"state": None, "result": None, "request": None, "old": None, "new": None}


@pytest.fixture(autouse=True)
def _patch_cache(monkeypatch):
    """用内存字典模拟 Django cache 接口，避开 dummy backend 写不进去的问题。"""
    store: dict = {}

    def _get(key, default=None):
        return store.get(key, default)

    def _set(key, value, timeout=None):
        store[key] = value

    def _delete(key):
        store.pop(key, None)

    monkeypatch.setattr(cache, "get", _get)
    monkeypatch.setattr(cache, "set", _set)
    monkeypatch.setattr(cache, "delete", _delete)


# ---------------------------------------------------------------------------
# 假设
# ---------------------------------------------------------------------------

@given(parsers.re(r'已存在 debug 状态 owner=(?P<owner>\{.*\}) status="(?P<status>[^"]+)"'))
def _seed_existing_state(ctx, owner, status):
    debug_id = "dbg_seed"
    CollectToolService.save_debug_state(debug_id, status, owner=json.loads(owner))
    ctx["state"] = CollectToolService.get_debug_state(debug_id)
    ctx["_seed_debug_id"] = debug_id


@given(parsers.re(
    r'旧任务 is_interval=(?P<ii>true|false) cycle_value="(?P<cv>[^"]*)" '
    r'cycle_value_type="(?P<cvt>[^"]*)" scan_cycle="(?P<sc>[^"]*)"'
))
def _seed_old(ctx, ii, cv, cvt, sc):
    ctx["old"] = SimpleNamespace(is_interval=(ii == "true"), cycle_value=cv, cycle_value_type=cvt, scan_cycle=sc)


@given(parsers.re(
    r'新任务 is_interval=(?P<ii>true|false) cycle_value="(?P<cv>[^"]*)" '
    r'cycle_value_type="(?P<cvt>[^"]*)" scan_cycle="(?P<sc>[^"]*)"'
))
def _seed_new(ctx, ii, cv, cvt, sc):
    ctx["new"] = SimpleNamespace(is_interval=(ii == "true"), cycle_value=cv, cycle_value_type=cvt, scan_cycle=sc)


# ---------------------------------------------------------------------------
# 当
# ---------------------------------------------------------------------------

@when(parsers.re(
    r'我以 owner=(?P<owner>\{.*\}) 保存 debug 状态 status="(?P<status>[^"]+)"'
))
def _save_state_new(ctx, owner, status):
    debug_id = "dbg_x"
    CollectToolService.save_debug_state(debug_id, status, owner=json.loads(owner))
    ctx["_debug_id"] = debug_id


@when(parsers.re(r'我以 result=(?P<result>\{.*\}) 保存 debug 状态 status="(?P<status>[^"]+)"'))
def _save_state_result(ctx, result, status):
    debug_id = ctx.get("_seed_debug_id", "dbg_x")
    CollectToolService.save_debug_state(debug_id, status, result=json.loads(result))
    ctx["_debug_id"] = debug_id


@when(parsers.parse('我构造 submit_response debug_id="{debug_id}" status="{status}"'))
def _build_submit(ctx, debug_id, status):
    ctx["result"] = CollectToolService.build_submit_response(debug_id, status)


@when(parsers.parse('我读取 debug 状态 debug_id="{debug_id}"'))
def _read_state(ctx, debug_id):
    ctx["result"] = CollectToolService.get_debug_state(debug_id)


@when(parsers.parse('用户 "{username}"@"{domain}" 尝试访问该状态'))
def _access(ctx, username, domain):
    request = SimpleNamespace(user=SimpleNamespace(username=username, domain=domain), COOKIES={})
    ctx["result"] = CollectToolService.can_access_debug_state(ctx["state"], request)


@when("我调用 is_schedule_config_changed")
def _schedule_changed(ctx):
    ctx["result"] = CollectModelService.is_schedule_config_changed(ctx["old"], ctx["new"])


# ---------------------------------------------------------------------------
# 那么
# ---------------------------------------------------------------------------

def _get_state(ctx):
    debug_id = ctx.get("_debug_id", ctx.get("_seed_debug_id"))
    return CollectToolService.get_debug_state(debug_id)


@then(parsers.parse('回读的 debug 状态 status 应当为 "{status}"'))
def _state_status(ctx, status):
    assert _get_state(ctx)["status"] == status


@then(parsers.parse('回读的 debug 状态 owner.username 应当为 "{value}"'))
def _state_owner_user(ctx, value):
    assert _get_state(ctx)["owner"]["username"] == value


@then(parsers.parse("回读的 debug 状态 result.ok 应当为 {flag}"))
def _state_result_ok(ctx, flag):
    assert _get_state(ctx)["result"]["ok"] is (flag.lower() == "true")


@then(parsers.parse('响应的 debug_id 应当为 "{value}"'))
def _resp_id(ctx, value):
    assert ctx["result"]["debug_id"] == value


@then(parsers.parse('响应的 status 应当为 "{value}"'))
def _resp_status(ctx, value):
    assert ctx["result"]["status"] == value


@then(parsers.parse('响应应当包含字段 "{key}"'))
def _resp_has(ctx, key):
    assert key in ctx["result"]


@then("回读结果应当为空")
def _state_none(ctx):
    assert ctx["result"] is None


@then(parsers.parse("访问决策应当为 {flag}"))
def _access_flag(ctx, flag):
    assert ctx["result"] is (flag.lower() == "true")


@then(parsers.parse("调度变化结果应当为 {flag}"))
def _schedule_flag(ctx, flag):
    assert ctx["result"] is (flag.lower() == "true")
