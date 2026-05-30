"""CMDB 配置采集 BDD（中文 Gherkin）。

对照 spec/prd/CMDB·资产采集：
- 调试态机的拥有者抽取与访问决策；
- 节点权限上下文（current_team / include_children cookie 解析）；
- 调度参数 format_params 与调度变化判断 is_schedule_config_changed；
- get_timeout 走 TIMEOUT_MAP 白名单回落；
- build_error_result 携带 stage/summary/meta。

3 happy + 6 corner，全部走纯函数 / 小桩，不连真实 Stargazer。
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from apps.cmdb.services.collect_service import CollectModelService
from apps.cmdb.services.collect_tool_service import CollectToolService

FEATURE = str(Path(__file__).parent / "collect.feature")
scenarios(FEATURE)


@pytest.fixture
def ctx():
    return {
        "request": None,
        "result": None,
        "state": None,
        "old": None,
        "new": None,
        "payload": None,
    }


def _make_request(username="", domain="", cookies=None):
    return SimpleNamespace(
        user=SimpleNamespace(username=username, domain=domain),
        COOKIES=cookies or {},
    )


# ---------------------------------------------------------------------------
# 假设
# ---------------------------------------------------------------------------

@given(parsers.parse('一个调试请求由用户 "{username}"@"{domain}" 发起'))
def _seed_request(ctx, username, domain):
    ctx["request"] = _make_request(username=username, domain=domain)


@given(parsers.re(
    r'一个调试请求由用户 "(?P<username>[^"]+)"@"(?P<domain>[^"]+)" 发起，cookies=(?P<cookies>\{.*\})$'
))
def _seed_request_with_cookies(ctx, username, domain, cookies):
    ctx["request"] = _make_request(username=username, domain=domain, cookies=json.loads(cookies))


@given(parsers.re(
    r'一个采集任务请求体 name="(?P<name>[^"]+)" task_type="(?P<task_type>[^"]+)" driver_type="(?P<driver_type>[^"]+)" '
    r'model_id="(?P<model_id>[^"]+)" timeout=(?P<timeout>\d+) input_method="(?P<input_method>[^"]+)" '
    r'scan_cycle_type="(?P<cycle_type>[^"]+)" scan_cycle_value="(?P<cycle_value>[^"]*)" team=(?P<team>\[[^\]]*\])'
))
def _seed_task_body(ctx, name, task_type, driver_type, model_id, timeout, input_method, cycle_type, cycle_value, team):
    ctx["payload"] = {
        "name": name,
        "task_type": task_type,
        "driver_type": driver_type,
        "model_id": model_id,
        "timeout": int(timeout),
        "input_method": input_method,
        "scan_cycle": {"value_type": cycle_type, "value": cycle_value},
        "team": json.loads(team),
    }


@given(parsers.parse("当前调试状态的 owner 为 {raw}"))
def _seed_state(ctx, raw):
    ctx["state"] = {"owner": json.loads(raw)}


@given(parsers.parse('当前请求来自用户 "{username}"@"{domain}"'))
def _seed_caller(ctx, username, domain):
    ctx["request"] = _make_request(username=username, domain=domain)


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


@given(parsers.re(
    r'一份采集 payload protocol="(?P<protocol>[^"]+)" action="(?P<action>[^"]+)" '
    r'target="(?P<target>[^"]+)" port=(?P<port>\d+)'
))
def _seed_collect_payload(ctx, protocol, action, target, port):
    ctx["payload"] = {"protocol": protocol, "action": action, "target": target, "port": int(port)}


# ---------------------------------------------------------------------------
# 当
# ---------------------------------------------------------------------------

@when("我调用 build_debug_owner")
def _call_build_owner(ctx):
    ctx["result"] = CollectToolService.build_debug_owner(ctx["request"])


@when("我调用 build_node_permission_data")
def _call_node_perm(ctx):
    ctx["result"] = CollectToolService.build_node_permission_data(ctx["request"])


@when("我调用 format_params")
def _call_format_params(ctx):
    params, _is_interval, _scan_cycle = CollectModelService.format_params(ctx["payload"])
    ctx["result"] = params


@when("我调用 can_access_debug_state")
def _call_can_access(ctx):
    ctx["result"] = CollectToolService.can_access_debug_state(ctx["state"], ctx["request"])


@when(parsers.parse('我调用 get_timeout 参数为 "{action}"'))
def _call_get_timeout(ctx, action):
    ctx["result"] = CollectToolService.get_timeout(action)


@when("我调用 is_schedule_config_changed")
def _call_is_changed(ctx):
    ctx["result"] = CollectModelService.is_schedule_config_changed(ctx["old"], ctx["new"])


@when(parsers.parse('我以 stage="{stage}" summary="{summary}" 调用 build_error_result'))
def _call_build_error(ctx, stage, summary):
    ctx["result"] = CollectToolService.build_error_result(
        debug_id="dbg_x", payload=ctx["payload"], stage=stage, summary=summary
    )


# ---------------------------------------------------------------------------
# 那么
# ---------------------------------------------------------------------------

@then(parsers.parse("owner 应当为 {raw}"))
def _owner_eq(ctx, raw):
    assert ctx["result"] == json.loads(raw)


@then(parsers.parse("节点权限上下文 include_children 应当为 {flag}"))
def _node_include_children(ctx, flag):
    assert ctx["result"]["include_children"] is (flag.lower() == "true")


@then(parsers.parse('节点权限上下文 current_team 应当为 "{value}"'))
def _node_team(ctx, value):
    assert ctx["result"]["current_team"] == value


@then(parsers.parse("格式化结果的 is_interval 应当为 {flag}"))
def _is_interval(ctx, flag):
    assert ctx["result"]["is_interval"] is (flag.lower() == "true")


@then(parsers.parse('格式化结果的 cycle_value 应当为 "{value}"'))
def _cycle_value(ctx, value):
    assert ctx["result"]["cycle_value"] == value


@then(parsers.parse('格式化结果的 cycle_value_type 应当为 "{value}"'))
def _cycle_value_type(ctx, value):
    assert ctx["result"]["cycle_value_type"] == value


@then(parsers.parse('格式化结果的 scan_cycle 应当为 "{value}"'))
def _scan_cycle(ctx, value):
    assert ctx["result"]["scan_cycle"] == value


@then(parsers.parse("访问决策应当为 {flag}"))
def _access_flag(ctx, flag):
    assert ctx["result"] is (flag.lower() == "true")


@then(parsers.parse("超时秒数应当为 {n:d}"))
def _timeout_n(ctx, n):
    assert ctx["result"] == n


@then(parsers.parse("调度变化结果应当为 {flag}"))
def _schedule_flag(ctx, flag):
    assert ctx["result"] is (flag.lower() == "true")


@then(parsers.parse("错误结果的 success 字段应当为 {flag}"))
def _err_success(ctx, flag):
    assert ctx["result"]["success"] is (flag.lower() == "true")


@then(parsers.parse('错误结果的 stage 字段应当为 "{value}"'))
def _err_stage(ctx, value):
    assert ctx["result"]["stage"] == value


@then(parsers.parse('错误结果的 summary 字段应当为 "{value}"'))
def _err_summary(ctx, value):
    assert ctx["result"]["summary"] == value


@then(parsers.parse('错误结果的 meta.target 字段应当为 "{value}"'))
def _err_meta_target(ctx, value):
    assert ctx["result"]["meta"]["target"] == value
