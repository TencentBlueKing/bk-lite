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
