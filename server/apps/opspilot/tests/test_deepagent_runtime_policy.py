import io
import json
import logging
import traceback
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool

from apps.core.logger import SafeLogException, opspilot_logger
from apps.opspilot.metis.llm.agent.tool_execution_planner import CompletedExecutionStep, ToolExecutionPlanner
from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator
from apps.opspilot.metis.llm.middleware.token_usage import TokenUsageTrackingMiddleware
from apps.opspilot.metis.llm.middleware.tool_runtime import SkillExecutionGuardMiddleware, ToolVisibilityMiddleware

_TOOL_SECRET_SENTINEL = "kubeconfig-hunter2-not-for-logs"


@contextmanager
def _capture_opspilot_formatted_logs():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    opspilot_logger.addHandler(handler)
    try:
        yield output
    finally:
        opspilot_logger.removeHandler(handler)


pytestmark = pytest.mark.unit


def _tool(name, description=None):
    def _run():
        return name

    return StructuredTool.from_function(
        func=_run,
        name=name,
        description=description or f"{name} description",
    )


def _request(tools, messages=None):
    return ModelRequest(
        model=SimpleNamespace(),
        messages=messages or [HumanMessage(content="K8s Warning Failed on Pod/ns/pod-1")],
        system_prompt=None,
        tool_choice=None,
        tools=tools,
        response_format=None,
        state={},
        runtime=SimpleNamespace(),
        model_settings={},
    )


def test_skills_only_visibility_keeps_execute_when_fs_hidden():
    """回归：纯技能步必须把 execute 放进 always_visible。

    只从 hidden discard 不够——allow_unregistered_tools=False 时模型会看到 0 工具，
    只能空谈「需要域配置」而不会真正跑脚本。
    """
    execute = _tool("execute")
    read_file = _tool("read_file")
    write_todos = _tool("write_todos")
    middleware = ToolVisibilityMiddleware(
        business_tools=[],
        active_tools=[],
        always_visible_tools={"execute"},
        hidden_tools={"write_todos", "task"},
        allow_unregistered_tools=False,
    )
    visible = []

    def _handler(request):
        visible.append([tool.name for tool in request.tools])
        return ModelResponse(result=[AIMessage(content="ok")])

    middleware.wrap_model_call(_request([execute, read_file, write_todos]), _handler)
    assert visible == [["execute"]]


def test_visibility_wrap_tool_call_blocks_hidden_fs_tools():
    middleware = ToolVisibilityMiddleware(
        business_tools=[],
        active_tools=[],
        always_visible_tools={"execute"},
        hidden_tools={"write_todos", "task"},
        allow_unregistered_tools=False,
    )
    called = {"n": 0}

    def handler(req):
        called["n"] += 1
        return "EXECUTED"

    req = SimpleNamespace(tool_call={"name": "read_file", "args": {"file_path": "/skills/ad-domain-ops/SKILL.md"}, "id": "c1"})
    result = middleware.wrap_tool_call(req, handler)
    assert called["n"] == 0
    assert result.status == "error"
    assert "不可用" in result.content
    assert "[OPSPILOT_POLICY]" in result.content
    assert "execute 本步技能脚本" in result.content


def test_visibility_wrap_tool_call_blocks_unplanned_business_tool():
    list_pods = _tool("list_pods")
    middleware = ToolVisibilityMiddleware(
        business_tools=[list_pods],
        active_tools=[list_pods],
        always_visible_tools={"request_user_choice"},
        hidden_tools={"write_todos", "task", "execute"},
        allow_unregistered_tools=False,
    )
    called = {"n": 0}

    def handler(req):
        called["n"] += 1
        return "EXECUTED"

    req = SimpleNamespace(tool_call={"name": "delete_pod", "args": {}, "id": "c1"})
    result = middleware.wrap_tool_call(req, handler)
    assert called["n"] == 0
    assert result.status == "error"
    assert "[OPSPILOT_POLICY]" in result.content
    assert "业务工具" in result.content
    assert "execute `/skills/" not in result.content
    from apps.opspilot.metis.llm.agent.tool_execution_planner import is_tool_result_failure

    assert not is_tool_result_failure(result.content, result.status)


def test_skill_guard_blocks_read_file_and_strips_tools_after_fail_then_probe():
    execute = _tool("execute")
    read_file = _tool("read_file")
    guard = SkillExecutionGuardMiddleware(enabled=True)
    fail = ToolMessage(
        content="ldap timeout\n[OPSPILOT_SKILL_RESULT] 脚本失败。最多修正参数后重试 1 次。",
        tool_call_id="e1",
        name="execute",
    )
    probe = ToolMessage(
        content="[OPSPILOT_SKILL_RESULT] 禁止 read_file/ls/grep 扫技能包。",
        tool_call_id="r1",
        name="read_file",
        status="error",
    )
    called = {"n": 0}

    def handler(req):
        called["n"] += 1
        return "EXECUTED"

    blocked = guard.wrap_tool_call(
        SimpleNamespace(
            tool_call={"name": "read_file", "args": {"file_path": "SKILL.md"}, "id": "c2"},
            state={"messages": [fail]},
        ),
        handler,
    )
    assert called["n"] == 0
    assert "禁止 read_file" in blocked.content

    visible = []

    def model_handler(request):
        visible.append([tool.name for tool in request.tools])
        return ModelResponse(result=[AIMessage(content="ok")])

    guard.wrap_model_call(_request([execute, read_file], messages=[HumanMessage(content="查用户"), fail, probe]), model_handler)
    assert visible == [[]]


def test_skill_guard_allows_one_script_retry_after_failure():
    guard = SkillExecutionGuardMiddleware(enabled=True)
    fail = ToolMessage(
        content="timed out\n[OPSPILOT_SKILL_RESULT] 脚本失败。最多修正参数后重试 1 次。",
        tool_call_id="e1",
        name="execute",
    )
    called = {"n": 0}

    def handler(req):
        called["n"] += 1
        return "EXECUTED"

    retry = SimpleNamespace(
        tool_call={
            "name": "execute",
            "args": {"command": "python3 /skills/ad-domain-ops/scripts/ad_search.py --query '*' --attrs sAMAccountName"},
            "id": "e2",
        },
        state={"messages": [fail]},
    )
    assert guard.wrap_tool_call(retry, handler) == "EXECUTED"
    assert called["n"] == 1

    cat = SimpleNamespace(
        tool_call={"name": "execute", "args": {"command": "cat /skills/ad-domain-ops/SKILL.md"}, "id": "e3"},
        state={"messages": [fail]},
    )
    denied = guard.wrap_tool_call(cat, handler)
    assert called["n"] == 1
    assert "不要再用" in denied.content

    listing = SimpleNamespace(
        tool_call={"name": "execute", "args": {"command": "ls -la /skills/ad-domain-ops/scripts/"}, "id": "e4"},
        state={"messages": [fail]},
    )
    denied_ls = guard.wrap_tool_call(listing, handler)
    assert called["n"] == 1
    assert "不要再用" in denied_ls.content


def test_skill_guard_stops_immediately_on_auth_script_failure():
    """凭据失败与业务工具同一套分型：第一次 execute 后禁止再跑脚本。"""
    guard = SkillExecutionGuardMiddleware(enabled=True)
    fail = ToolMessage(
        content='{"ok":false,"error":"invalid credentials"}\n[OPSPILOT_SKILL_RESULT] 脚本失败。最多修正参数后重试 1 次。',
        tool_call_id="e1",
        name="execute",
    )
    called = {"n": 0}

    def handler(req):
        called["n"] += 1
        return "EXECUTED"

    retry = SimpleNamespace(
        tool_call={
            "name": "execute",
            "args": {"command": "python3 /skills/ad-domain-ops/scripts/ad_search.py --query '*' --attrs sAMAccountName"},
            "id": "e2",
        },
        state={"messages": [fail]},
    )
    denied = guard.wrap_tool_call(retry, handler)
    assert called["n"] == 0
    assert "不要再调用工具" in denied.content or "OPSPILOT_SKILL_STOP" in denied.content


def test_tool_exception_middleware_returns_error_tool_message():
    from apps.opspilot.metis.llm.middleware.tool_runtime import ToolExceptionAsResultMiddleware

    middleware = ToolExceptionAsResultMiddleware()

    def boom(_req):
        raise Exception("无法加载 Kubernetes 配置: Invalid base64-encoded string. 请检查 kubeconfig 配置内容或集群连接。")

    req = SimpleNamespace(tool_call={"name": "diagnose_kubernetes_pod_issues", "id": "c1", "args": {}})
    result = middleware.wrap_tool_call(req, boom)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.tool_call_id == "c1"
    assert "无法加载 Kubernetes 配置" in result.content
    assert "Invalid base64" in result.content


def test_tool_exception_middleware_logs_once_without_exception_payload(caplog):
    from apps.opspilot.metis.llm.middleware.tool_runtime import ToolExceptionAsResultMiddleware

    middleware = ToolExceptionAsResultMiddleware()
    original = TypeError(f"cannot pickle '_thread.lock' object {_TOOL_SECRET_SENTINEL}")

    def boom(_req):
        raise original

    req = SimpleNamespace(tool_call={"name": "resolve_k8s_target_from_alert", "id": "c1", "args": {}})
    caplog.set_level(logging.ERROR, logger="opspilot")
    with _capture_opspilot_formatted_logs() as output:
        result = middleware.wrap_tool_call(req, boom)
    rendered = output.getvalue()

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.tool_call_id == "c1"
    assert result.name == "resolve_k8s_target_from_alert"
    assert _TOOL_SECRET_SENTINEL in result.content
    owned = [
        rec
        for rec in caplog.records
        if rec.name == "opspilot"
        and rec.levelno == logging.ERROR
        and rec.exc_info
        and rec.msg == "event=agent_tool_failed failed_stage=tool_call error_type=%s tool_name=%s"
    ]
    assert len(owned) == 1
    rec = owned[0]
    assert rec.args == ("TypeError", "resolve_k8s_target_from_alert")
    message = rec.getMessage()
    assert "failed_stage=tool_call" in message
    assert "error_type=TypeError" in message
    assert "tool_name=resolve_k8s_target_from_alert" in message
    assert rec.exc_info[0] is SafeLogException
    assert rec.exc_info[1] is not original
    assert rec.exc_info[2] is original.__traceback__
    assert str(rec.exc_info[1]) == "TypeError"
    assert str(original) == f"cannot pickle '_thread.lock' object {_TOOL_SECRET_SENTINEL}"
    frame_names = [frame.name for frame in traceback.extract_tb(rec.exc_info[2])]
    assert "boom" in frame_names
    assert _TOOL_SECRET_SENTINEL not in message
    assert "Traceback" in rendered
    assert "boom" in rendered
    assert _TOOL_SECRET_SENTINEL not in rendered
    traceback_errors = [r for r in caplog.records if r.name == "opspilot" and r.levelno >= logging.ERROR and r.exc_info]
    assert traceback_errors == owned


def test_dynamic_tool_visibility_exposes_step_tools_plus_always_on_fs():
    diagnose = _tool("diagnose_kubernetes_pod_issues")
    logs = _tool("get_kubernetes_pod_logs")
    events = _tool("list_kubernetes_events")
    planning = _tool("write_todos")
    task = _tool("task")
    read_file = _tool("read_file")
    choice = _tool("request_user_choice")
    active_tools = []
    middleware = ToolVisibilityMiddleware(
        business_tools=[diagnose, logs, events, choice],
        active_tools=active_tools,
        always_visible_tools={"read_file", "request_user_choice"},
        hidden_tools={"write_todos", "task", "execute"},
        allow_unregistered_tools=False,
    )
    visible_calls = []

    def _handler(request):
        visible_calls.append([tool.name for tool in request.tools])
        return ModelResponse(result=[AIMessage(content="ok")])

    all_tools = [diagnose, logs, events, planning, task, read_file, choice]
    middleware.wrap_model_call(_request(all_tools), _handler)
    active_tools[:] = [diagnose, logs]
    middleware.wrap_model_call(_request(all_tools), _handler)
    active_tools[:] = [events]
    middleware.wrap_model_call(_request(all_tools), _handler)
    active_tools.clear()
    middleware.include_always_visible = False
    middleware.wrap_model_call(_request(all_tools), _handler)

    assert visible_calls == [
        ["read_file", "request_user_choice"],
        [
            "diagnose_kubernetes_pod_issues",
            "get_kubernetes_pod_logs",
            "read_file",
            "request_user_choice",
        ],
        ["list_kubernetes_events", "read_file", "request_user_choice"],
        [],
    ]


def test_progressive_tools_env_defaults_enabled(monkeypatch):
    from apps.opspilot.metis.llm.middleware.tool_runtime import is_progressive_tools_enabled

    monkeypatch.delenv("OPSPILOT_DEEPAGENT_PROGRESSIVE_TOOLS", raising=False)
    assert is_progressive_tools_enabled() is True
    monkeypatch.setenv("OPSPILOT_DEEPAGENT_PROGRESSIVE_TOOLS", "0")
    assert is_progressive_tools_enabled() is False
    monkeypatch.setenv("OPSPILOT_DEEPAGENT_PROGRESSIVE_TOOLS", "1")
    assert is_progressive_tools_enabled() is True


def test_run_model_call_limit_env(monkeypatch):
    from apps.opspilot.metis.llm.middleware.tool_runtime import get_planned_execution_run_model_call_limit

    monkeypatch.delenv("OPSPILOT_DEEPAGENT_RUN_MODEL_CALL_LIMIT", raising=False)
    assert get_planned_execution_run_model_call_limit() == 10
    monkeypatch.setenv("OPSPILOT_DEEPAGENT_RUN_MODEL_CALL_LIMIT", "12")
    assert get_planned_execution_run_model_call_limit() == 12
    monkeypatch.setenv("OPSPILOT_DEEPAGENT_RUN_MODEL_CALL_LIMIT", "0")
    assert get_planned_execution_run_model_call_limit() == 10
    monkeypatch.setenv("OPSPILOT_DEEPAGENT_RUN_MODEL_CALL_LIMIT", "abc")
    assert get_planned_execution_run_model_call_limit() == 10


def test_max_tokens_budget_env_and_request(monkeypatch):
    from apps.opspilot.metis.llm.middleware.planned_execution_limits import (
        get_planned_execution_max_tokens_budget,
        resolve_planned_execution_token_budget,
    )

    monkeypatch.delenv("OPSPILOT_DEEPAGENT_MAX_TOKENS_BUDGET", raising=False)
    assert get_planned_execution_max_tokens_budget() == 0
    monkeypatch.setenv("OPSPILOT_DEEPAGENT_MAX_TOKENS_BUDGET", "50000")
    assert get_planned_execution_max_tokens_budget() == 50000
    assert resolve_planned_execution_token_budget(SimpleNamespace(max_tokens_budget=0)) == 50000
    assert resolve_planned_execution_token_budget(SimpleNamespace(max_tokens_budget=8000)) == 8000
    monkeypatch.setenv("OPSPILOT_DEEPAGENT_MAX_TOKENS_BUDGET", "-1")
    assert get_planned_execution_max_tokens_budget() == 0


def test_planned_execution_limit_middleware_messages_and_continue():
    from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator
    from apps.opspilot.metis.llm.middleware.planned_execution_limits import (
        LIMIT_MARKER_MODEL_CALLS,
        LIMIT_MARKER_TOKEN_BUDGET,
        PlannedExecutionLimitMiddleware,
        build_limit_exceeded_message,
        detect_limit_kind,
    )

    model_msg = build_limit_exceeded_message("model_calls", used=10, limit=10)
    assert LIMIT_MARKER_MODEL_CALLS in model_msg
    assert "模型调用次数已达上限" in model_msg
    token_msg = build_limit_exceeded_message("token_budget", used=100, limit=100)
    assert LIMIT_MARKER_TOKEN_BUDGET in token_msg

    from langchain_core.messages import AIMessage

    assert detect_limit_kind([AIMessage(content=model_msg)]) == "model_calls"
    assert detect_limit_kind([AIMessage(content=token_msg)]) == "token_budget"

    accumulator = TokenUsageAccumulator()
    accumulator.total_tokens = 100
    middleware = PlannedExecutionLimitMiddleware(
        run_limit=2,
        token_budget=100,
        soft_budget_ratio=0.8,
        accumulator=accumulator,
    )
    hard = middleware.before_model({"run_model_call_count": 0, "messages": []}, None)
    assert hard is not None
    assert hard["jump_to"] == "end"
    assert LIMIT_MARKER_TOKEN_BUDGET in hard["messages"][0].content

    middleware.enforce_limits = False
    assert middleware.before_model({"run_model_call_count": 99, "messages": []}, None) is None
    middleware.enforce_limits = True

    middleware2 = PlannedExecutionLimitMiddleware(run_limit=2, token_budget=0)
    hard2 = middleware2.before_model({"run_model_call_count": 2, "messages": []}, None)
    assert hard2 is not None
    assert LIMIT_MARKER_MODEL_CALLS in hard2["messages"][0].content

    assert middleware2.grant_continue("model_calls") is True
    assert middleware2.effective_run_limit == 4
    assert middleware2.grant_continue("model_calls") is True
    assert middleware2.grant_continue("model_calls") is True
    assert middleware2.grant_continue("model_calls") is False


@pytest.mark.asyncio
async def test_planner_uses_compact_catalog_and_normalizes_tool_plan():
    long_description = "诊断 Pod 故障。" + "不要把这段完整说明发给规划模型。" * 100
    tools = [
        _tool("current_time"),
        _tool("diagnose_pod", long_description),
        _tool("list_events"),
        _tool("get_logs"),
        _tool("get_yaml"),
    ]

    class FakeLLM:
        def __init__(self):
            self.messages = None

        async def ainvoke(self, messages, config=None):
            self.messages = messages
            return AIMessage(
                content="""{
                    "goal": "定位告警根因",
                    "steps": [
                        {"objective": "确认时间", "tools": ["current_time", "current_time", "missing"]},
                        {"objective": "诊断 Pod", "tools": ["diagnose_pod", "list_events", "get_logs", "get_yaml"]},
                        {"objective": "分析证据", "tools": []},
                        {"objective": "补充 YAML", "tools": ["get_yaml"]},
                        {"objective": "补充日志", "tools": ["get_logs"]},
                        {"objective": "不应保留", "tools": ["get_logs"]}
                    ]
                }""",
                usage_metadata={
                    "input_tokens": 400,
                    "output_tokens": 100,
                    "total_tokens": 500,
                },
            )

    llm = FakeLLM()
    accumulator = TokenUsageAccumulator()
    planner = ToolExecutionPlanner(
        llm,
        accumulator=accumulator,
        max_steps=4,
        max_tools_per_step=3,
        catalog_description_limit=80,
    )

    plan = await planner.plan(
        "K8s Pod 告警",
        tools,
        completed_steps=[CompletedExecutionStep(objective="读取告警", result="已确认 Pod 名称")],
    )

    assert plan.goal == "定位告警根因"
    assert [step.objective for step in plan.steps] == [
        "确认时间",
        "诊断 Pod",
        "补充 YAML",
        "补充日志",
    ]
    assert plan.steps[0].tools == ["current_time"]
    assert plan.steps[1].tools == ["diagnose_pod", "list_events", "get_logs"]
    planner_prompt = "\n".join(str(message.content) for message in llm.messages)
    assert long_description not in planner_prompt
    assert "已确认 Pod 名称" in planner_prompt
    assert accumulator.call_count == 1
    assert accumulator.as_call_details()[0]["visible_tools"] == []


@pytest.mark.asyncio
async def test_planner_catalog_prepends_k8s_namespace_lookup_hint():
    tools = [
        _tool("resolve_k8s_target_from_alert", "从告警解析目标"),
        _tool("diagnose_kubernetes_pod_issues", "诊断 Pod"),
        _tool("list_kubernetes_pods", "列出 Pod"),
    ]

    class FakeLLM:
        def __init__(self):
            self.messages = None

        async def ainvoke(self, messages, config=None):
            self.messages = messages
            return AIMessage(
                content=json.dumps(
                    {
                        "goal": "定位 Pod 告警",
                        "steps": [
                            {
                                "objective": "反查命名空间",
                                "tools": ["resolve_k8s_target_from_alert", "list_kubernetes_pods"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            )

    llm = FakeLLM()
    plan = await ToolExecutionPlanner(llm).plan(
        "告警：Unhealthy server-5b8fb979d7-csdcc Startup probe failed",
        tools,
    )
    prompt = "\n".join(str(message.content) for message in llm.messages)
    assert "缺 namespace" in prompt or "反查" in prompt
    assert "diagnose_kubernetes_pod_issues" in prompt
    assert "禁止用 list_kubernetes_pods" in prompt
    assert "namespace 留空" not in prompt
    assert "只需规划 resolve_k8s_target_from_alert" not in prompt
    assert "不要只规划反查就结束" in prompt
    assert plan.steps[0].tools == ["resolve_k8s_target_from_alert"]


@pytest.mark.asyncio
async def test_planner_catalog_prepends_known_pod_restart_rca_hint():
    tools = [
        _tool("diagnose_kubernetes_pod_issues", "诊断 Pod"),
        _tool("get_kubernetes_previous_pod_logs", "上一轮日志"),
        _tool("get_resource_events_timeline", "事件时间线"),
        _tool("analyze_pod_restart_pattern", "扫描重启模式"),
        _tool("describe_kubernetes_resource", "描述资源"),
        _tool("list_kubernetes_pods", "列出 Pod"),
        _tool("list_kubernetes_events", "列出事件"),
    ]

    class FakeLLM:
        def __init__(self):
            self.messages = None

        async def ainvoke(self, messages, config=None):
            self.messages = messages
            return AIMessage(
                content=json.dumps(
                    {
                        "goal": "分析指定 Pod 重启原因",
                        "steps": [
                            {
                                "objective": "诊断",
                                "tools": [
                                    "diagnose_kubernetes_pod_issues",
                                    "analyze_pod_restart_pattern",
                                    "describe_kubernetes_resource",
                                    "list_kubernetes_events",
                                ],
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            )

    llm = FakeLLM()
    plan = await ToolExecutionPlanner(llm).plan("分析 kube-system/coredns-xxx 频繁重启的原因", tools)
    prompt = "\n".join(str(message.content) for message in llm.messages)
    assert "已指定具体 Pod 问重启原因" in prompt
    assert "get_kubernetes_previous_pod_logs" in prompt
    assert "禁止降低 lines" in prompt
    assert "没有 previous" in prompt or "无 previous" in prompt or "没有可用的 previous" in prompt
    assert "禁止 analyze_pod_restart_pattern" in prompt
    assert "describe_kubernetes_resource" in prompt
    assert [step.tools for step in plan.steps] == [["diagnose_kubernetes_pod_issues"]]


@pytest.mark.asyncio
async def test_planner_collapses_restart_reason_to_evidence_tool():
    tools = [
        _tool("diagnose_kubernetes_pod_issues", "诊断 Pod"),
        _tool("get_kubernetes_pod_logs", "当前日志"),
        _tool("get_kubernetes_previous_pod_logs", "上一轮日志"),
        _tool("get_resource_events_timeline", "事件时间线"),
        _tool("collect_pod_restart_evidence", "重启取证包"),
        _tool("current_time", "当前时间"),
    ]

    class FakeLLM:
        def __init__(self):
            self.messages = None

        async def ainvoke(self, messages, config=None):
            self.messages = messages
            return AIMessage(
                content=json.dumps(
                    {
                        "goal": "分析指定 Pod 重启原因",
                        "steps": [
                            {"objective": "对时", "tools": ["current_time"]},
                            {
                                "objective": "诊断和日志",
                                "tools": [
                                    "diagnose_kubernetes_pod_issues",
                                    "get_kubernetes_pod_logs",
                                    "get_kubernetes_previous_pod_logs",
                                ],
                            },
                        ],
                    },
                    ensure_ascii=False,
                )
            )

    llm = FakeLLM()
    plan = await ToolExecutionPlanner(llm).plan("分析 argocd/argocd-repo-server 频繁重启的原因", tools)
    prompt = "\n".join(str(message.content) for message in llm.messages)
    assert "collect_pod_restart_evidence" in prompt
    assert "只规划 collect_pod_restart_evidence" in prompt
    assert "禁止再规划 diagnose_kubernetes_pod_issues" in prompt
    assert [step.tools for step in plan.steps] == [["current_time"], ["collect_pod_restart_evidence"]]


@pytest.mark.asyncio
async def test_planner_does_not_collapse_alert_rca_when_evidence_tool_present():
    tools = [
        _tool("diagnose_kubernetes_pod_issues", "诊断 Pod"),
        _tool("get_kubernetes_pod_logs", "当前日志"),
        _tool("get_kubernetes_previous_pod_logs", "上一轮日志"),
        _tool("get_resource_events_timeline", "事件时间线"),
        _tool("collect_pod_restart_evidence", "重启取证包"),
        _tool("resolve_k8s_target_from_alert", "反查 namespace"),
    ]

    class FakeLLM:
        def __init__(self):
            self.messages = None

        async def ainvoke(self, messages, config=None):
            self.messages = messages
            return AIMessage(
                content=json.dumps(
                    {
                        "goal": "告警 RCA",
                        "steps": [
                            {"objective": "反查", "tools": ["resolve_k8s_target_from_alert"]},
                            {
                                "objective": "诊断",
                                "tools": ["diagnose_kubernetes_pod_issues", "get_kubernetes_pod_logs"],
                            },
                        ],
                    },
                    ensure_ascii=False,
                )
            )

    llm = FakeLLM()
    plan = await ToolExecutionPlanner(llm).plan(
        "告警：Unhealthy（kubernetes，bk-lite-k3s，nacos-0） 检测到异常\nReadiness probe failed",
        tools,
        agent_system_prompt="你是 Kubernetes 集群 RCA 助手。\n## 告警怎么读\n",
    )
    prompt = "\n".join(str(message.content) for message in llm.messages)
    assert "只规划 collect_pod_restart_evidence" not in prompt
    assert [step.tools for step in plan.steps] == [
        ["resolve_k8s_target_from_alert"],
        ["diagnose_kubernetes_pod_issues", "get_kubernetes_pod_logs"],
    ]


@pytest.mark.asyncio
async def test_planner_catalog_prepends_restart_time_sort_hint():
    tools = [
        _tool("get_high_restart_kubernetes_pods", "发现频繁重启的不稳定Pod"),
        _tool("get_recently_restarted_kubernetes_pods", "按最近一次重启时间列出最近重启过的 Pod"),
    ]

    class FakeLLM:
        def __init__(self):
            self.messages = None

        async def ainvoke(self, messages, config=None):
            self.messages = messages
            return AIMessage(
                content=json.dumps(
                    {
                        "goal": "按重启时间列最近 Pod",
                        "steps": [{"objective": "累计高重启", "tools": ["get_high_restart_kubernetes_pods"]}],
                    },
                    ensure_ascii=False,
                )
            )

    llm = FakeLLM()
    plan = await ToolExecutionPlanner(llm).plan(
        "按照重启时间排序，列出最近的 10 个重启的 pod，并展示重启时间和次数",
        tools,
    )
    prompt = "\n".join(str(message.content) for message in llm.messages)
    assert "必须规划 get_recently_restarted_kubernetes_pods" in prompt
    assert "禁止 get_high_restart_kubernetes_pods" in prompt
    assert [step.tools for step in plan.steps] == [["get_recently_restarted_kubernetes_pods"]]


@pytest.mark.asyncio
async def test_planner_task_prompt_includes_agent_system_prompt():
    tools = [
        _tool("resolve_k8s_target_from_alert", "从告警解析目标"),
        _tool("diagnose_kubernetes_pod_issues", "诊断 Pod"),
        _tool("get_kubernetes_pod_logs", "查日志"),
    ]

    class FakeLLM:
        def __init__(self):
            self.messages = None

        async def ainvoke(self, messages, config=None):
            self.messages = messages
            return AIMessage(
                content=json.dumps(
                    {
                        "goal": "复盘告警",
                        "steps": [
                            {"objective": "反查命名空间", "tools": ["resolve_k8s_target_from_alert"]},
                            {"objective": "取证诊断", "tools": ["diagnose_kubernetes_pod_issues", "get_kubernetes_pod_logs"]},
                        ],
                    },
                    ensure_ascii=False,
                )
            )

    llm = FakeLLM()
    plan = await ToolExecutionPlanner(llm).plan(
        "告警：Unhealthy（kubernetes，minikube，kube-scheduler-minikube）",
        tools,
        agent_system_prompt=("你是 Kubernetes 集群 RCA 助手。目标是证据闭环。" "单次任务：解析告警 → 有界反查 → 仅对象仍在时按需取证 → 写报告。" "【附件生成强制规则】这段模板不应进入规划器任务说明。"),
    )
    prompt = "\n".join(str(message.content) for message in llm.messages)
    assert "助手任务说明" in prompt
    assert "有界反查" in prompt
    assert "按需取证" in prompt
    assert "规划须对齐「助手任务说明」" in prompt
    assert "附件生成强制规则" not in prompt
    assert [step.tools for step in plan.steps] == [
        ["resolve_k8s_target_from_alert"],
        ["diagnose_kubernetes_pod_issues", "get_kubernetes_pod_logs"],
    ]


def test_agent_task_brief_strips_attachment_rule_and_truncates():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import _agent_task_brief

    brief = _agent_task_brief("角色说明：取证后写报告\n【附件生成强制规则】这段是模板")
    assert "取证后写报告" in brief
    assert "附件生成强制规则" not in brief
    truncated = _agent_task_brief("目标" + ("取证" * 2000), limit=40)
    assert len(truncated) <= 41
    assert truncated.endswith("…")


@pytest.mark.asyncio
async def test_planner_catalog_prepends_monitor_capability_hint():
    tools = [
        _tool("monitor_list_objects", "列出对象"),
        _tool("monitor_query_metric_data", "查时序"),
        _tool("other_tool", "无关工具"),
    ]

    class FakeLLM:
        def __init__(self):
            self.messages = None

        async def ainvoke(self, messages, config=None):
            self.messages = messages
            return AIMessage(content='{"goal":"查CPU","steps":[{"objective":"列对象","tools":["monitor_list_objects"]}]}')

    llm = FakeLLM()
    planner = ToolExecutionPlanner(llm)
    plan = await planner.plan("检查主机 boxxxxx 的CPU使用率", tools)

    assert plan.steps[0].tools == ["monitor_list_objects"]
    prompt = "\n".join(str(message.content) for message in llm.messages)
    assert "能力导读" in prompt
    assert "CPU使用率" in prompt
    assert "禁止返回空 steps" in prompt
    assert "monitor_list_objects→monitor_list_object_instances" in prompt
    assert "必须规划对应 monitor_* 步骤" in prompt


def test_parse_tool_execution_plan_payload_accepts_markdown_and_step_list():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolPlanningError, parse_tool_execution_plan_payload

    fenced = parse_tool_execution_plan_payload(
        """好的，计划如下：
```json
{"goal":"定位 Pod 告警","steps":[{"objective":"查事件","tools":["list_events"]}]}
```
"""
    )
    assert fenced["goal"] == "定位 Pod 告警"
    assert fenced["steps"][0]["tools"] == ["list_events"]

    as_list = parse_tool_execution_plan_payload('[{"objective":"查日志","tools":["get_logs"]},{"objective":"查YAML","tools":["get_yaml"]}]')
    assert as_list["goal"] == ""
    assert len(as_list["steps"]) == 2

    with pytest.raises(ToolPlanningError, match="规划模型未返回 JSON 对象"):
        parse_tool_execution_plan_payload("我先分析一下告警原因，稍后再给计划。")


@pytest.mark.asyncio
async def test_planner_recovers_from_markdown_wrapped_plan():
    tools = [_tool("list_events"), _tool("get_logs")]

    class FakeLLM:
        async def ainvoke(self, messages, config=None):
            return AIMessage(
                content=(
                    "Here is the plan:\n"
                    "```json\n"
                    '{"goal":"排查 Unhealthy","steps":[{"objective":"查事件","tools":["list_events","get_logs"]}]}\n'
                    "```\n"
                )
            )

    plan = await ToolExecutionPlanner(FakeLLM()).plan("Unhealthy startup probe", tools)
    assert plan.goal == "排查 Unhealthy"
    assert plan.steps[0].tools == ["list_events", "get_logs"]


@pytest.mark.asyncio
async def test_planner_retries_when_model_claims_empty_message():
    tools = [_tool("list_events"), _tool("get_logs")]
    calls = []

    class FakeLLM:
        async def ainvoke(self, messages, config=None):
            calls.append(messages)
            if len(calls) == 1:
                return AIMessage(content="It looks like your message came through empty! How can I help you today?")
            return AIMessage(content='{"goal":"排查探针失败","steps":[{"objective":"查事件","tools":["list_events","get_logs"]}]}')

    plan = await ToolExecutionPlanner(FakeLLM()).plan(
        "告警：Unhealthy startup probe failed connection refused",
        tools,
    )
    assert len(calls) == 2
    assert plan.goal == "排查探针失败"
    assert plan.steps[0].tools == ["list_events", "get_logs"]
    # 重试应把指令与任务合并到单条 user，降低空消息误判
    assert len(calls[1]) == 1
    assert "告警：Unhealthy" in str(calls[1][0].content)
    assert "只输出一个 JSON 对象" in str(calls[1][0].content)


@pytest.mark.asyncio
async def test_planner_catalog_respects_char_budget():
    tools = [_tool(f"tool_{i}", "很长的工具描述" * 40) for i in range(40)]

    class FakeLLM:
        def __init__(self):
            self.messages = None

        async def ainvoke(self, messages, config=None):
            self.messages = messages
            return AIMessage(content='{"goal":"g","steps":[{"objective":"o","tools":["tool_0"]}]}')

    llm = FakeLLM()
    planner = ToolExecutionPlanner(llm, catalog_description_limit=48, catalog_char_budget=800)
    await planner.plan("查一下", tools)
    catalog = "\n".join(str(message.content) for message in llm.messages)
    # 预算内不应接近旧版 61 工具 × 120 字那种近万字符目录
    assert "紧凑工具目录" in catalog
    assert catalog.count("- tool_") == 40
    assert len(catalog) < 2500


def test_is_context_size_error_detects_provider_messages():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import is_context_size_error

    assert is_context_size_error("BadRequestError: request (9132 tokens) exceeds the available context size (8192 tokens)")
    assert is_context_size_error({"error": {"type": "exceed_context_size_error"}})
    assert not is_context_size_error("connection refused")


def test_is_tool_result_failure_detects_json_error_payload():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import is_tool_result_failure

    assert is_tool_result_failure('{"error": "Pod x 在命名空间 y 中不存在"}')
    assert is_tool_result_failure({"error": "not found"})
    assert is_tool_result_failure("error: boom")
    assert is_tool_result_failure("ok", status="error")
    assert not is_tool_result_failure('{"phase": "Running"}')
    assert not is_tool_result_failure("connection refused detail")
    assert not is_tool_result_failure(
        "工具 glob 当前不可用。不要用 read_file/ls/grep 扫技能包；直接 execute `/skills/<包名>/scripts/...`。",
        status="error",
    )
    assert not is_tool_result_failure(
        "[OPSPILOT_SKILL_RESULT] 脚本不存在，不要 ls/glob/read_file。请直接改跑：python3 /skills/ad-domain-ops/scripts/ad_search.py",
        status="error",
    )
    assert not is_tool_result_failure(
        "[OPSPILOT_POLICY] 工具 delete_pod 当前不可用。只调用本步骤可见的业务工具。",
        status="error",
    )


def test_classify_tool_failure_kind_separates_auth_from_retryable():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import (
        TOOL_FAILURE_AUTHN,
        TOOL_FAILURE_AUTHZ,
        TOOL_FAILURE_CONFIG,
        TOOL_FAILURE_INTERNAL,
        TOOL_FAILURE_OTHER,
        classify_tool_failure_kind,
        is_non_replanable_tool_failure,
        is_tool_result_failure,
    )
    from apps.opspilot.metis.llm.common.tool_failure import unrecoverable_skill_result_hint

    assert classify_tool_failure_kind('{"error": "获取Pod列表失败: (401)\\nReason: Unauthorized"}') == TOOL_FAILURE_AUTHN
    assert classify_tool_failure_kind("无法加载 Kubernetes 配置: invalid certificate") == TOOL_FAILURE_AUTHN
    assert classify_tool_failure_kind('{"error": "获取Deployment列表失败: (403)\\nReason: Forbidden"}') == TOOL_FAILURE_AUTHZ
    assert (
        classify_tool_failure_kind(
            {"error": "connection_failed", "message": "无法连接 Kubernetes 集群"},
            status="success",
        )
        == TOOL_FAILURE_CONFIG
    )
    assert classify_tool_failure_kind("MySQL host is required", status="error") == TOOL_FAILURE_CONFIG
    assert classify_tool_failure_kind("Failed to decrypt field 'value': InvalidToken", status="error") == TOOL_FAILURE_CONFIG
    assert (
        classify_tool_failure_kind(
            "AttributeError: 'NoneType' object has no attribute 'items'",
            status="error",
        )
        == TOOL_FAILURE_INTERNAL
    )
    assert classify_tool_failure_kind('{"error": "Pod x 在命名空间 y 中不存在"}') == TOOL_FAILURE_OTHER
    assert classify_tool_failure_kind("connection refused", status="error") == TOOL_FAILURE_OTHER
    assert classify_tool_failure_kind("namespace is required", status="error") == TOOL_FAILURE_OTHER
    assert classify_tool_failure_kind('{"phase": "Running"}') == TOOL_FAILURE_OTHER
    assert is_non_replanable_tool_failure('{"error": "401 Unauthorized"}')
    assert is_non_replanable_tool_failure('{"error": "403 Forbidden"}')
    assert is_non_replanable_tool_failure('{"error": "connection_failed"}')
    assert is_non_replanable_tool_failure("CredentialValidationError: Redis host/url is required")
    assert is_non_replanable_tool_failure("AttributeError: 'NoneType' object has no attribute 'metadata'", status="error")
    assert not is_non_replanable_tool_failure('{"error": "Pod x 在命名空间 y 中不存在"}')
    assert not is_non_replanable_tool_failure("connection refused", status="error")
    assert not is_non_replanable_tool_failure("namespace is required", status="error")
    assert not is_non_replanable_tool_failure(
        "[OPSPILOT_POLICY] 工具 delete_pod 当前不可用。只调用本步骤可见的业务工具。",
        status="error",
    )
    skill_auth = '{"ok":false,"error":"invalid credentials"}\n[OPSPILOT_SKILL_RESULT] 脚本失败。最多修正参数后重试 1 次。'
    skill_auth_stop = '{"ok":false,"error":"invalid credentials"}\n' "[OPSPILOT_SKILL_RESULT] 连接、凭据、权限或脚本实现失败，禁止重试。" "把错误原样告诉用户并结束，不要改参，不要 read_file。"
    skill_timeout = "timed out\n[OPSPILOT_SKILL_RESULT] 脚本失败。最多修正参数后重试 1 次。"
    skill_missing = "[OPSPILOT_SKILL_RESULT] 脚本不存在，不要 ls/glob/read_file。请直接改跑：python3 /skills/ad-domain-ops/scripts/ad_search.py"
    skill_args = "[OPSPILOT_SKILL_RESULT] 参数错误，禁止 read_file。立刻再 execute 一次"
    assert classify_tool_failure_kind(skill_auth) == TOOL_FAILURE_AUTHN
    assert is_non_replanable_tool_failure(skill_auth)
    assert classify_tool_failure_kind(skill_auth_stop) == TOOL_FAILURE_AUTHN
    assert is_non_replanable_tool_failure(skill_auth_stop)
    assert classify_tool_failure_kind(skill_timeout) == TOOL_FAILURE_OTHER
    assert not is_non_replanable_tool_failure(skill_timeout)
    assert not is_non_replanable_tool_failure(skill_missing, status="error")
    assert not is_non_replanable_tool_failure(skill_args, status="error")
    hint = unrecoverable_skill_result_hint('{"ok":false,"error":"invalid credentials"}')
    assert hint is not None and "禁止重试" in hint
    assert unrecoverable_skill_result_hint("timed out") is None
    assert unrecoverable_skill_result_hint('{"ok":false,"error":{"code":6,"message":"Cannot reach"}}') is None
    app_previous_log = (
        "Traceback (most recent call last):\n"
        '  File "/usr/local/lib/python3.12/site-packages/mlflow/store/model_registry/base_rest_store.py", line 42, in _call_endpoint\n'
        "mlflow.exceptions.RestException: RESOURCE_DOES_NOT_EXIST: Registered Model with name=classification_XGBoost_1.1 not found"
    )
    assert classify_tool_failure_kind(app_previous_log) == TOOL_FAILURE_OTHER
    assert not is_tool_result_failure(app_previous_log)
    assert not is_non_replanable_tool_failure(app_previous_log)


def test_resolve_planned_execution_compact_limits_scales_with_working_budget():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import (
        planned_execution_compact_limits_for_request,
        resolve_planned_execution_compact_limits,
    )

    assert resolve_planned_execution_compact_limits() == (1500, 1000)
    assert resolve_planned_execution_compact_limits(input_working_tokens=None) == (1500, 1000)
    assert resolve_planned_execution_compact_limits(input_working_tokens=0) == (1500, 1000)
    assert resolve_planned_execution_compact_limits(input_working_tokens=6800) == (1500, 1000)

    tool_chars, ai_chars = resolve_planned_execution_compact_limits(input_working_tokens=186_000)
    assert tool_chars == 37_200
    assert ai_chars == 27_352
    assert tool_chars > 1500
    assert ai_chars > 1000

    request = SimpleNamespace(
        extra_config={"input_working_tokens": 186_000},
        message_trim_config={"max_single_message_tokens": 37_200},
    )
    assert planned_execution_compact_limits_for_request(request) == (37_200, 27_352)
    assert planned_execution_compact_limits_for_request(SimpleNamespace(extra_config={})) == (1500, 1000)


def test_compact_planned_execution_messages_truncates_tool_and_ai_text():
    from langchain_core.messages import AIMessage, ToolMessage

    from apps.opspilot.metis.llm.agent.tool_execution_planner import compact_planned_execution_messages

    messages = [
        ToolMessage(content="t" * 5000, tool_call_id="c1", name="diagnose_kubernetes_pod_issues"),
        AIMessage(content="a" * 3000),
        AIMessage(content="keep tool call", tool_calls=[{"id": "1", "name": "x", "args": {}}]),
    ]
    out = compact_planned_execution_messages(messages, max_tool_chars=120, max_ai_chars=80)
    assert len(out[0].content) <= 120
    assert out[0].content.endswith("...(truncated)")
    assert len(out[1].content) <= 80
    assert out[2].content == "keep tool call"


def test_compact_pod_logs_keeps_tail_error_and_forbids_retry():
    from langchain_core.messages import ToolMessage

    from apps.opspilot.metis.llm.agent.tool_execution_planner import compact_planned_execution_messages

    body = ("INFO heartbeat " + ("x" * 40) + "\n") * 80 + "ERROR boom RESOURCE_DOES_NOT_EXIST"
    out = compact_planned_execution_messages(
        [ToolMessage(content=body, tool_call_id="c1", name="get_kubernetes_pod_logs")],
        max_tool_chars=180,
        max_ai_chars=80,
    )
    text = out[0].content
    assert len(text) <= 180
    assert "RESOURCE_DOES_NOT_EXIST" in text
    assert "禁止" in text
    assert not text.endswith("...(truncated)")


def test_compact_pod_restart_evidence_keeps_previous_tail():
    import json

    from langchain_core.messages import ToolMessage

    from apps.opspilot.metis.llm.agent.tool_execution_planner import compact_planned_execution_messages

    payload = {
        "pod_name": "px",
        "namespace": "ns",
        "clock": {"finished_at": "2026-09-04T05:00:00+00:00", "started_at": "2026-09-04T05:01:00+00:00"},
        "last_state": {"reason": "Error", "exit_code": 1},
        "events": [{"reason": "BackOff", "message": "x" * 400}],
        "logs": {
            "previous_tail": {"available": True, "content": ("INFO " + "y" * 80 + "\n") * 40 + "ERROR boom RESOURCE_DOES_NOT_EXIST"},
            "current_tail": {"skipped": True},
            "current_head": {"skipped": True},
        },
        "missing": [],
    }
    out = compact_planned_execution_messages(
        [ToolMessage(content=json.dumps(payload, ensure_ascii=False), tool_call_id="c1", name="collect_pod_restart_evidence")],
        max_tool_chars=1800,
        max_ai_chars=80,
    )
    parsed = json.loads(out[0].content)
    assert parsed["clock"]["finished_at"].startswith("2026-09-04T05:00:00")
    assert "RESOURCE_DOES_NOT_EXIST" in parsed["logs"]["previous_tail"]["content"]


def test_compact_execute_skill_json_keeps_all_entries_under_budget():
    """AD 列举结果被 1500 字预算压缩后仍应保留全部 sAMAccountName。"""
    import json

    from langchain_core.messages import ToolMessage

    from apps.opspilot.metis.llm.agent.tool_execution_planner import compact_planned_execution_messages

    entries = []
    for index in range(10):
        entries.append(
            {
                "sAMAccountName": f"user{index:02d}",
                "displayName": f"User {index:02d}",
                "mail": f"user{index:02d}@bktest.com.cn",
                "distinguishedName": f"CN=User{index:02d},CN=Users,DC=bktest,DC=com,DC=cn",
                "userAccountControl": 512,
                "description": "很长的描述" * 40,
                "lastLogonTimestamp": "2026-08-13 09:59:33.351587+00:00",
                "whenCreated": "2024-05-24 01:27:18+00:00",
                "whenChanged": "2026-08-13 09:59:33+00:00",
                "userPrincipalName": f"user{index:02d}@bktest.com.cn",
                "department": [],
                "title": [],
            }
        )
    payload = {
        "ok": True,
        "data": {
            "type": "user",
            "query": "*",
            "base_dn": "DC=bktest,DC=com,DC=cn",
            "count": 10,
            "entries": entries,
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    assert len(raw) > 1500
    out = compact_planned_execution_messages(
        [ToolMessage(content=raw, tool_call_id="c1", name="execute")],
        max_tool_chars=1500,
    )
    parsed = json.loads(out[0].content)
    assert parsed["ok"] is True
    assert parsed["data"]["count"] == 10
    assert len(parsed["data"]["entries"]) == 10
    names = [(item.get("sAMAccountName") if isinstance(item, dict) else item) for item in parsed["data"]["entries"]]
    assert names[0] == "user00"
    assert names[4] == "user04"
    assert names[9] == "user09"


def test_compact_analyze_deployment_keeps_parseable_issues_detail_under_budget():
    """60 对象分析结果被模型侧压缩后仍须可 JSON 解析，且保留 issues_detail。"""
    import json

    from langchain_core.messages import ToolMessage

    from apps.opspilot.metis.llm.agent.tool_execution_planner import compact_planned_execution_messages

    issues_detail = [
        {
            "severity": "high",
            "issue": f"未配置探针-{index}",
            "count": 59,
            "workloads": [f"scan-fixture-{i:03d} (bk-lite-scan-fixtures)" for i in range(59)],
        }
        for index in range(12)
    ]
    payload = {
        "cluster_name": "Kubernetes - 2",
        "total": 60,
        "healthy": 0,
        "problematic": 60,
        "issues_detail": issues_detail,
        "_report_emitted_capability": "config_analysis_report",
        "_next_step_hint": "结构化配置检查报告已通过界面卡片展示。",
        "_deployments_full": [{"name": f"d-{i}", "namespace": "ns", "issues": ["x"]} for i in range(60)],
    }
    raw = json.dumps(payload, ensure_ascii=False)
    assert len(raw) > 1500

    out = compact_planned_execution_messages(
        [ToolMessage(content=raw, tool_call_id="a1", name="analyze_deployment_configurations")],
        max_tool_chars=1500,
    )
    compact = json.loads(out[0].content)
    assert compact["problematic"] == 60
    assert compact.get("issues_detail")
    assert compact.get("_deployments_full_omitted") is True
    assert "不要因 workloads 列表缩短而重跑" in compact["_next_step_hint"]
    assert len(out[0].content) <= 1500


def test_enforce_k8s_namespace_lookup_first_prepends_resolve_step():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionPlan, ToolExecutionStep, enforce_k8s_namespace_lookup_first

    plan = ToolExecutionPlan(
        goal="RCA",
        steps=[ToolExecutionStep(objective="诊断 Pod", tools=["diagnose_kubernetes_pod_issues"])],
    )
    fixed = enforce_k8s_namespace_lookup_first(
        plan,
        {
            "resolve_k8s_target_from_alert",
            "diagnose_kubernetes_pod_issues",
            "get_kubernetes_pod_logs",
        },
        max_steps=4,
    )
    assert fixed.steps[0].tools == ["resolve_k8s_target_from_alert"]
    assert fixed.steps[1].tools == ["diagnose_kubernetes_pod_issues"]

    with_prep = ToolExecutionPlan(
        goal="RCA",
        steps=[
            ToolExecutionStep(objective="确认时间", tools=["current_time"]),
            ToolExecutionStep(objective="诊断 Pod", tools=["diagnose_kubernetes_pod_issues"]),
        ],
    )
    fixed_mid = enforce_k8s_namespace_lookup_first(
        with_prep,
        {"resolve_k8s_target_from_alert", "current_time", "diagnose_kubernetes_pod_issues"},
        max_steps=4,
    )
    assert [step.tools for step in fixed_mid.steps] == [
        ["current_time"],
        ["resolve_k8s_target_from_alert"],
        ["diagnose_kubernetes_pod_issues"],
    ]


def test_enforce_k8s_namespace_lookup_strips_cluster_wide_scans():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionPlan, ToolExecutionStep, enforce_k8s_namespace_lookup_first

    packed = ToolExecutionPlan(
        goal="RCA",
        steps=[
            ToolExecutionStep(
                objective="定位 Pod",
                tools=["resolve_k8s_target_from_alert", "list_kubernetes_pods", "list_kubernetes_events"],
            )
        ],
    )
    fixed_packed = enforce_k8s_namespace_lookup_first(
        packed,
        {
            "resolve_k8s_target_from_alert",
            "list_kubernetes_pods",
            "list_kubernetes_events",
            "diagnose_kubernetes_pod_issues",
        },
        max_steps=4,
    )
    assert [step.tools for step in fixed_packed.steps] == [["resolve_k8s_target_from_alert"]]

    scanned = ToolExecutionPlan(
        goal="RCA",
        steps=[
            ToolExecutionStep(objective="扫全集群", tools=["list_kubernetes_pods", "list_kubernetes_events"]),
            ToolExecutionStep(objective="诊断 Pod", tools=["diagnose_kubernetes_pod_issues"]),
        ],
    )
    fixed_scanned = enforce_k8s_namespace_lookup_first(
        scanned,
        {
            "resolve_k8s_target_from_alert",
            "list_kubernetes_pods",
            "list_kubernetes_events",
            "diagnose_kubernetes_pod_issues",
        },
        max_steps=4,
    )
    assert [step.tools for step in fixed_scanned.steps] == [
        ["resolve_k8s_target_from_alert"],
        ["diagnose_kubernetes_pod_issues"],
    ]


def test_enforce_k8s_namespace_lookup_skips_resolve_after_cluster_discovery(caplog):
    import logging

    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionPlan, ToolExecutionStep, enforce_k8s_namespace_lookup_first

    caplog.set_level(logging.INFO, logger="opspilot")
    plan = ToolExecutionPlan(
        goal="统计今天重启",
        steps=[
            ToolExecutionStep(objective="找高频重启", tools=["get_high_restart_kubernetes_pods"]),
            ToolExecutionStep(objective="事件时间线", tools=["get_resource_events_timeline"]),
        ],
    )
    fixed = enforce_k8s_namespace_lookup_first(
        plan,
        {
            "resolve_k8s_target_from_alert",
            "get_high_restart_kubernetes_pods",
            "get_resource_events_timeline",
        },
        max_steps=4,
    )
    assert [step.tools for step in fixed.steps] == [
        ["get_high_restart_kubernetes_pods"],
        ["get_resource_events_timeline"],
    ]
    records = [rec for rec in caplog.records if rec.name == "opspilot" and rec.msg.startswith("DeepAgent 规划硬校验：前置发现工具已带 namespace，跳过插入反查")]
    assert len(records) == 1
    assert records[0].args == (["get_high_restart_kubernetes_pods"],)
    assert "get_high_restart_kubernetes_pods" in records[0].getMessage()


def test_drop_cluster_scan_tools_for_known_pod_diagnose():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import (
        ToolExecutionPlan,
        ToolExecutionStep,
        drop_cluster_scan_tools_for_known_pod_diagnose,
    )

    plan = ToolExecutionPlan(
        goal="分析指定 Pod 重启",
        steps=[
            ToolExecutionStep(
                objective="诊断",
                tools=["diagnose_kubernetes_pod_issues", "list_kubernetes_events", "describe_kubernetes_resource"],
            ),
            ToolExecutionStep(objective="扫集群", tools=["analyze_pod_restart_pattern", "list_kubernetes_pods"]),
            ToolExecutionStep(objective="上一轮日志", tools=["get_kubernetes_previous_pod_logs"]),
        ],
    )
    fixed = drop_cluster_scan_tools_for_known_pod_diagnose(plan)
    assert [step.tools for step in fixed.steps] == [
        ["diagnose_kubernetes_pod_issues"],
        ["get_kubernetes_previous_pod_logs"],
    ]

    mixed = ToolExecutionPlan(
        goal="先巡检再诊断",
        steps=[
            ToolExecutionStep(objective="高重启名单", tools=["get_high_restart_kubernetes_pods"]),
            ToolExecutionStep(objective="诊断", tools=["diagnose_kubernetes_pod_issues"]),
        ],
    )
    kept = drop_cluster_scan_tools_for_known_pod_diagnose(mixed)
    assert [step.tools for step in kept.steps] == [
        ["get_high_restart_kubernetes_pods"],
        ["diagnose_kubernetes_pod_issues"],
    ]


def test_collapse_known_pod_restart_to_evidence_tool_only_for_restart_reason():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import (
        ToolExecutionPlan,
        ToolExecutionStep,
        collapse_known_pod_restart_to_evidence_tool,
        is_pod_restart_reason_query,
    )

    available = {
        "current_time",
        "resolve_k8s_target_from_alert",
        "diagnose_kubernetes_pod_issues",
        "get_kubernetes_pod_logs",
        "get_kubernetes_previous_pod_logs",
        "get_resource_events_timeline",
        "collect_pod_restart_evidence",
    }
    noisy = ToolExecutionPlan(
        goal="分析重启",
        steps=[
            ToolExecutionStep(objective="对时", tools=["current_time"]),
            ToolExecutionStep(objective="反查", tools=["resolve_k8s_target_from_alert"]),
            ToolExecutionStep(objective="诊断", tools=["diagnose_kubernetes_pod_issues"]),
            ToolExecutionStep(objective="当前日志", tools=["get_kubernetes_pod_logs"]),
            ToolExecutionStep(objective="上一轮日志", tools=["get_kubernetes_previous_pod_logs"]),
            ToolExecutionStep(objective="事件", tools=["get_resource_events_timeline"]),
        ],
    )
    restart_q = "分析 argocd/argocd-repo-server-f6d44484c-kkss8 频繁重启的原因"
    assert is_pod_restart_reason_query(restart_q) is True
    collapsed = collapse_known_pod_restart_to_evidence_tool(noisy, available, user_message=restart_q)
    assert [step.tools for step in collapsed.steps] == [
        ["current_time"],
        ["resolve_k8s_target_from_alert"],
        ["collect_pod_restart_evidence"],
    ]

    alert_q = "告警：Unhealthy（kubernetes，bk-lite-k3s，nacos-0） 检测到异常\nReadiness probe failed"
    assert is_pod_restart_reason_query(alert_q) is False
    kept_alert = collapse_known_pod_restart_to_evidence_tool(noisy, available, user_message=alert_q)
    assert [step.tools for step in kept_alert.steps] == [step.tools for step in noisy.steps]

    rca_prompt = "你是 Kubernetes 集群 RCA 助手。\n## 告警怎么读\n"
    kept_prompt = collapse_known_pod_restart_to_evidence_tool(
        noisy,
        available,
        user_message="这个 Pod 为什么重启",
        agent_system_prompt=rca_prompt,
    )
    assert [step.tools for step in kept_prompt.steps] == [step.tools for step in noisy.steps]

    assert is_pod_restart_reason_query("看看 argocd-repo-server 当前日志") is False
    assert is_pod_restart_reason_query("按重启时间列出最近 10 个重启的 Pod") is False
    assert is_pod_restart_reason_query("巡检 Deployment 探针配置") is False
    kept_logs = collapse_known_pod_restart_to_evidence_tool(
        noisy,
        available,
        user_message="看看 argocd-repo-server 当前日志",
    )
    assert [step.tools for step in kept_logs.steps] == [step.tools for step in noisy.steps]


def test_rewrite_high_restart_to_recent_for_time_sort():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import (
        ToolExecutionPlan,
        ToolExecutionStep,
        rewrite_high_restart_to_recent_for_time_sort,
    )

    available = {"get_high_restart_kubernetes_pods", "get_recently_restarted_kubernetes_pods"}
    plan = ToolExecutionPlan(
        goal="按重启时间列最近 Pod",
        steps=[ToolExecutionStep(objective="找高频重启", tools=["get_high_restart_kubernetes_pods"])],
    )
    fixed = rewrite_high_restart_to_recent_for_time_sort(
        plan,
        available,
        user_message="按照重启时间排序，列出最近的 10 个重启的 pod，并展示重启时间和次数",
    )
    assert [step.tools for step in fixed.steps] == [["get_recently_restarted_kubernetes_pods"]]

    count_only = rewrite_high_restart_to_recent_for_time_sort(
        plan,
        available,
        user_message="找出累计重启次数很高的不稳定 Pod",
    )
    assert [step.tools for step in count_only.steps] == [["get_high_restart_kubernetes_pods"]]

    mixed = ToolExecutionPlan(
        goal="先名单再诊断",
        steps=[
            ToolExecutionStep(objective="高重启名单", tools=["get_high_restart_kubernetes_pods"]),
            ToolExecutionStep(objective="诊断", tools=["diagnose_kubernetes_pod_issues"]),
        ],
    )
    kept = rewrite_high_restart_to_recent_for_time_sort(
        mixed,
        available | {"diagnose_kubernetes_pod_issues"},
        user_message="按照重启时间排序，列出最近的 10 个重启的 pod",
    )
    assert [step.tools for step in kept.steps] == [
        ["get_high_restart_kubernetes_pods"],
        ["diagnose_kubernetes_pod_issues"],
    ]


def test_enforce_k8s_namespace_lookup_first_prepends_for_previous_logs():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionPlan, ToolExecutionStep, enforce_k8s_namespace_lookup_first

    plan = ToolExecutionPlan(
        goal="上一轮日志",
        steps=[ToolExecutionStep(objective="取 previous 日志", tools=["get_kubernetes_previous_pod_logs"])],
    )
    fixed = enforce_k8s_namespace_lookup_first(
        plan,
        {"resolve_k8s_target_from_alert", "get_kubernetes_previous_pod_logs"},
        max_steps=4,
    )
    assert [step.tools for step in fixed.steps] == [
        ["resolve_k8s_target_from_alert"],
        ["get_kubernetes_previous_pod_logs"],
    ]


def test_drop_k8s_followup_steps_after_unresolved_target():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionStep, drop_k8s_followup_steps_after_unresolved_target

    kept = drop_k8s_followup_steps_after_unresolved_target(
        [
            ToolExecutionStep(objective="诊断", tools=["diagnose_kubernetes_pod_issues"]),
            ToolExecutionStep(objective="反查", tools=["resolve_k8s_target_from_alert"]),
            ToolExecutionStep(objective="写报告", tools=["generate_attachment_file"]),
        ]
    )
    assert [step.tools for step in kept] == [["generate_attachment_file"]]


def test_merge_replanned_pending_steps_keeps_uncovered_followups():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionStep, merge_replanned_pending_steps

    merged = merge_replanned_pending_steps(
        [ToolExecutionStep(objective="获取集群节点列表", tools=["list_kubernetes_nodes"])],
        [
            ToolExecutionStep(objective="检查 PVC", tools=["check_pvc_capacity"]),
            ToolExecutionStep(objective="评估业务影响", tools=["list_kubernetes_events"]),
        ],
    )
    assert [step.tools for step in merged] == [
        ["list_kubernetes_nodes"],
        ["check_pvc_capacity"],
        ["list_kubernetes_events"],
    ]


def test_merge_replanned_pending_steps_skips_already_covered_followups():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionStep, merge_replanned_pending_steps

    merged = merge_replanned_pending_steps(
        [
            ToolExecutionStep(objective="检查存储", tools=["check_pvc_capacity", "list_kubernetes_events"]),
        ],
        [
            ToolExecutionStep(objective="检查 PVC", tools=["check_pvc_capacity"]),
            ToolExecutionStep(objective="评估业务影响", tools=["list_kubernetes_events"]),
        ],
    )
    assert [step.tools for step in merged] == [["check_pvc_capacity", "list_kubernetes_events"]]


@pytest.mark.asyncio
async def test_planner_normalize_hard_enforces_namespace_lookup():
    tools = [
        _tool("resolve_k8s_target_from_alert", "反查"),
        _tool("diagnose_kubernetes_pod_issues", "诊断"),
    ]

    class FakeLLM:
        async def ainvoke(self, messages, config=None):
            return AIMessage(
                content=json.dumps(
                    {
                        "goal": "定位",
                        "steps": [{"objective": "直接诊断", "tools": ["diagnose_kubernetes_pod_issues"]}],
                    },
                    ensure_ascii=False,
                )
            )

    plan = await ToolExecutionPlanner(FakeLLM()).plan("Unhealthy server-xxx", tools)
    assert plan.steps[0].tools == ["resolve_k8s_target_from_alert"]
    assert plan.steps[1].tools == ["diagnose_kubernetes_pod_issues"]


@pytest.mark.asyncio
async def test_planner_keeps_use_skills_sentinel_when_packages_present():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import USE_SKILLS_TOOL_NAME

    tools = [_tool("shell", "执行命令")]
    packages = [{"name": "kubernetes-specialist", "description": "排查 K8s Pod / Event"}]

    class FakeLLM:
        def __init__(self):
            self.messages = None

        async def ainvoke(self, messages, config=None):
            self.messages = messages
            return AIMessage(
                content=json.dumps(
                    {
                        "goal": "按技能排查",
                        "steps": [{"objective": "读取技能并执行", "tools": [USE_SKILLS_TOOL_NAME]}],
                    },
                    ensure_ascii=False,
                )
            )

    llm = FakeLLM()
    plan = await ToolExecutionPlanner(llm).plan("用 k8s 技能排查 Pod", tools, skill_packages=packages)
    assert plan.steps[0].tools == [USE_SKILLS_TOOL_NAME]
    prompt = "\n".join(str(message.content) for message in llm.messages)
    assert "可用技能包" in prompt
    assert "kubernetes-specialist" in prompt
    assert USE_SKILLS_TOOL_NAME in prompt


@pytest.mark.asyncio
async def test_planner_drops_use_skills_without_packages():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import USE_SKILLS_TOOL_NAME

    tools = [_tool("shell", "执行命令")]

    class FakeLLM:
        async def ainvoke(self, messages, config=None):
            return AIMessage(
                content=json.dumps(
                    {
                        "goal": "闲聊",
                        "steps": [{"objective": "误挂技能", "tools": [USE_SKILLS_TOOL_NAME]}],
                    },
                    ensure_ascii=False,
                )
            )

    plan = await ToolExecutionPlanner(FakeLLM()).plan("你好", tools, skill_packages=[])
    assert plan.steps == []


def test_enforce_generate_attachment_file_injects_when_empty_plan():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import (
        GENERATE_ATTACHMENT_FILE_TOOL_NAME,
        ToolExecutionPlan,
        enforce_generate_attachment_file,
        looks_like_attachment_file_task,
    )

    assert looks_like_attachment_file_task("RC 数据", "你是月报生成器，输出 .md 文件") is True
    assert looks_like_attachment_file_task("你好", "月报生成器") is False
    # chat_service 注入的强制规则模板不得单独触发硬注入
    force_rule = "【附件生成强制规则 - 最高优先级，不可违反】\n" "当前工作流已配置文件生成工具 generate_attachment_file。\n" "必须调用 generate_attachment_file 工具把完整内容写入可下载文件"
    assert looks_like_attachment_file_task("今天天气怎么样", force_rule) is False
    assert looks_like_attachment_file_task("写一份运维月报", force_rule) is True

    fixed = enforce_generate_attachment_file(
        ToolExecutionPlan(goal="写月报", steps=[]),
        {GENERATE_ATTACHMENT_FILE_TOOL_NAME},
        user_message='{"root_causes":[]}',
        agent_system_prompt="生成 K8s 集群运维月报，内容放在 .md 文件",
    )
    assert len(fixed.steps) == 1
    assert fixed.steps[0].tools == [GENERATE_ATTACHMENT_FILE_TOOL_NAME]


@pytest.mark.asyncio
async def test_planner_forces_attachment_tool_when_model_returns_empty_steps():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import GENERATE_ATTACHMENT_FILE_TOOL_NAME

    tools = [_tool(GENERATE_ATTACHMENT_FILE_TOOL_NAME, "生成可下载附件")]

    class FakeLLM:
        def __init__(self):
            self.messages = None

        async def ainvoke(self, messages, config=None):
            self.messages = messages
            return AIMessage(content='{"goal":"写月报","steps":[]}')

    llm = FakeLLM()
    plan = await ToolExecutionPlanner(llm).plan(
        "month=2026-06 root_causes=[...]",
        tools,
        agent_system_prompt="你是 OpsPilot K8s 月报生成器，月报是一个 .md 报告文件。",
    )
    assert plan.steps
    assert GENERATE_ATTACHMENT_FILE_TOOL_NAME in plan.steps[0].tools
    prompt = "\n".join(str(message.content) for message in llm.messages)
    assert "generate_attachment_file" in prompt
    assert "禁止返回空 steps" in prompt or "禁止空 steps" in prompt


@pytest.mark.asyncio
async def test_planner_aligns_use_skills_to_declared_source_tool():
    """技能包声明 source_tool 后，纯 __use_skills__ 步应对齐到业务工具。"""
    from apps.opspilot.metis.llm.agent.tool_execution_planner import (
        ANALYZE_DEPLOYMENT_CONFIGURATIONS_TOOL_NAME,
        USE_SKILLS_TOOL_NAME,
        ToolExecutionPlanner,
    )

    tools = [_tool(ANALYZE_DEPLOYMENT_CONFIGURATIONS_TOOL_NAME, "分析 Deployment 配置")]
    skill_packages = [
        {
            "name": "kubernetes-configuration",
            "description": "K8s 配置检查",
            "capabilities": ["config_analysis_report", "repair_diff_report"],
            "reports": {
                "config_analysis": {
                    "source_tool": ANALYZE_DEPLOYMENT_CONFIGURATIONS_TOOL_NAME,
                    "event": "config_analysis_report",
                }
            },
        }
    ]

    class FakeLLM:
        async def ainvoke(self, messages, config=None):
            return AIMessage(content=('{"goal":"检查配置","steps":[{"objective":"按技能包检查","tools":["' + USE_SKILLS_TOOL_NAME + '"]}]}'))

    plan = await ToolExecutionPlanner(FakeLLM()).plan(
        "使用技能查看 k8s 集群下所有的工作负载有没有配置问题",
        tools,
        skill_packages=skill_packages,
    )
    assert plan.steps
    assert plan.steps[0].tools == [ANALYZE_DEPLOYMENT_CONFIGURATIONS_TOOL_NAME]
    assert USE_SKILLS_TOOL_NAME not in plan.steps[0].tools


def test_enforce_source_tool_rewrites_bare_use_skills_only():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import (
        ANALYZE_DEPLOYMENT_CONFIGURATIONS_TOOL_NAME,
        USE_SKILLS_TOOL_NAME,
        ToolExecutionPlan,
        ToolExecutionStep,
        enforce_skill_report_source_tools,
    )

    plan = ToolExecutionPlan(
        goal="检查配置",
        steps=[ToolExecutionStep(objective="读技能包", tools=[USE_SKILLS_TOOL_NAME])],
    )
    fixed = enforce_skill_report_source_tools(
        plan,
        {ANALYZE_DEPLOYMENT_CONFIGURATIONS_TOOL_NAME, USE_SKILLS_TOOL_NAME},
        skill_packages=[{"capabilities": ["config_analysis_report"]}],
    )
    assert fixed.steps[0].tools == [ANALYZE_DEPLOYMENT_CONFIGURATIONS_TOOL_NAME]


def test_enforce_source_tool_does_not_inject_when_plan_has_business_tools():
    """有列表等业务工具时只去掉哨兵，不硬塞 analyze。"""
    from apps.opspilot.metis.llm.agent.tool_execution_planner import (
        ANALYZE_DEPLOYMENT_CONFIGURATIONS_TOOL_NAME,
        USE_SKILLS_TOOL_NAME,
        ToolExecutionPlan,
        ToolExecutionStep,
        enforce_skill_report_source_tools,
    )

    plan = ToolExecutionPlan(
        goal="列工作负载",
        steps=[
            ToolExecutionStep(objective="列出 Deployment", tools=["list_kubernetes_deployments", USE_SKILLS_TOOL_NAME]),
        ],
    )
    fixed = enforce_skill_report_source_tools(
        plan,
        {
            ANALYZE_DEPLOYMENT_CONFIGURATIONS_TOOL_NAME,
            USE_SKILLS_TOOL_NAME,
            "list_kubernetes_deployments",
        },
        skill_packages=[{"capabilities": ["config_analysis_report"]}],
    )
    assert fixed.steps == [
        ToolExecutionStep(objective="列出 Deployment", tools=["list_kubernetes_deployments"]),
    ]


def test_token_usage_middleware_records_each_model_call_and_visible_tools():
    accumulator = TokenUsageAccumulator()
    middleware = TokenUsageTrackingMiddleware(accumulator)
    request = _request(
        [
            _tool("diagnose_kubernetes_pod_issues"),
            _tool("list_kubernetes_events"),
        ]
    )
    responses = iter(
        [
            AIMessage(
                content="调用诊断工具",
                usage_metadata={
                    "input_tokens": 1200,
                    "output_tokens": 80,
                    "total_tokens": 1280,
                },
            ),
            AIMessage(
                content="根因分析完成",
                usage_metadata={
                    "input_tokens": 1800,
                    "output_tokens": 220,
                    "total_tokens": 2020,
                },
            ),
        ]
    )

    def _handler(_request):
        return ModelResponse(result=[next(responses)])

    middleware.wrap_model_call(request, _handler)
    middleware.wrap_model_call(request, _handler)

    assert accumulator.as_openai_usage() == {
        "prompt_tokens": 3000,
        "completion_tokens": 300,
        "total_tokens": 3300,
    }
    assert accumulator.call_count == 2
    assert accumulator.as_call_details() == [
        {
            "call_index": 1,
            "prompt_tokens": 1200,
            "completion_tokens": 80,
            "total_tokens": 1280,
            "reported": True,
            "visible_tool_count": 2,
            "visible_tools": [
                "diagnose_kubernetes_pod_issues",
                "list_kubernetes_events",
            ],
        },
        {
            "call_index": 2,
            "prompt_tokens": 1800,
            "completion_tokens": 220,
            "total_tokens": 2020,
            "reported": True,
            "visible_tool_count": 2,
            "visible_tools": [
                "diagnose_kubernetes_pod_issues",
                "list_kubernetes_events",
            ],
        },
    ]
