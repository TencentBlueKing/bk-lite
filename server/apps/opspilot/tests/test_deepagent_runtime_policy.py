import json
from types import SimpleNamespace

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool

from apps.opspilot.metis.llm.agent.tool_execution_planner import CompletedExecutionStep, ToolExecutionPlanner
from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator
from apps.opspilot.metis.llm.middleware.token_usage import TokenUsageTrackingMiddleware
from apps.opspilot.metis.llm.middleware.tool_runtime import ToolVisibilityMiddleware

pytestmark = pytest.mark.unit


def _tool(name, description=None):
    def _run():
        return name

    return StructuredTool.from_function(
        func=_run,
        name=name,
        description=description or f"{name} description",
    )


def _request(tools):
    return ModelRequest(
        model=SimpleNamespace(),
        messages=[HumanMessage(content="K8s Warning Failed on Pod/ns/pod-1")],
        system_prompt=None,
        tool_choice=None,
        tools=tools,
        response_format=None,
        state={},
        runtime=SimpleNamespace(),
        model_settings={},
    )


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


@pytest.mark.asyncio
async def test_ask_limit_continue_defaults_node_id_to_skill_test(mocker):
    """无工作流 node_id 时必须发 skill_test，否则 submit_choice 会 404。"""
    from apps.opspilot.metis.llm.middleware.planned_execution_limits import ask_limit_continue

    captured = {}

    def _dispatch(name, data, config=None):
        captured["event"] = data

    async def _wait(**kwargs):
        captured["wait"] = kwargs
        return {"selected": ["continue"]}

    mocker.patch(
        "apps.opspilot.metis.llm.chain.report_renderers.k8s.build_a2ui_report_contract",
        return_value={"component": "user-choice"},
    )
    mocker.patch(
        "apps.opspilot.metis.llm.middleware.planned_execution_limits.dispatch_custom_event",
        side_effect=_dispatch,
    )
    mocker.patch("apps.opspilot.utils.user_choice.wait_for_choice", side_effect=_wait)

    ok = await ask_limit_continue(
        kind="model_calls",
        step_objective="排查",
        config={"configurable": {"execution_id": "exec-1"}},
    )
    assert ok is True
    assert captured["event"]["node_id"] == "skill_test"
    assert captured["event"]["execution_id"] == "exec-1"
    assert captured["wait"]["node_id"] == "skill_test"


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
    assert plan.steps[0].tools[0] == "resolve_k8s_target_from_alert"


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
