"""node._emit_report_event 集成测试:验证 skill 包 capability 真的驱动 dispatch。

锁定行为:
- skill 包声明 capability → _emit_report_event 调对应 renderer 产出 payload
  → dispatch_custom_event 收到 (capability_name, payload)
- skill 包未声明 → _emit_report_event 直接返回 None,dispatch 不发
- 渲染器返回 None(无效数据)→ dispatch 不发,但调用方收到 None
- 事件名 = capability 名(后端和前端、skill 包能力名三者一致)
"""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.opspilot.metis.llm.chain.k8s_report_tools import (
    RENDERER_REGISTRY,
    register_renderer,
)


pytestmark = pytest.mark.unit


def _make_node(skill_capabilities: list[str]):
    """直接构造一个 ToolsNodes 风格的 stub,只塞 _extra_config 和 capability 集合。

    ToolsNodes.__init__ 很重(建 LLM/工具),这里走 minimal 路径:
    走 ToolsNodes.__new__ 跳过 __init__,只装 _emit_report_event 用得到的属性。
    """
    from types import SimpleNamespace

    from apps.opspilot.metis.llm.chain.node import ToolsNodes

    node = ToolsNodes.__new__(ToolsNodes)
    node._skill_package_capabilities = set(skill_capabilities)
    node._extra_config = SimpleNamespace(matched_skill_packages=[])
    return node


def test_emit_report_event_returns_none_when_capability_not_declared():
    """skill 包没声明 capability 时,即使注册了渲染器,也不发事件。"""
    node = _make_node(skill_capabilities=[])  # 空

    parsed = {"cluster_name": "x", "issues_detail": [{"severity": "high", "issue": "y", "count": 1, "workloads": []}]}
    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        result = node._emit_report_event("config_analysis_report", parsed)

    assert result is None
    mock_dispatch.assert_not_called()


def test_emit_report_event_dispatches_with_capability_name_as_event():
    """skill 包声明 capability,事件名严格 = capability 名(不是 config_diff_report 这种历史名)。"""
    node = _make_node(skill_capabilities=["config_analysis_report"])
    parsed = {
        "cluster_name": "Kubernetes - 1",
        "issues_detail": [
            {"severity": "high", "issue": "未配置存活探针", "count": 7, "workloads": ["admin-panel"]}
        ],
    }
    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        result = node._emit_report_event("config_analysis_report", parsed)

    assert result is not None
    assert result  # 是 report_id 字符串
    mock_dispatch.assert_called_once()
    event_name, payload = mock_dispatch.call_args.args
    assert event_name == "config_analysis_report"  # 关键:不是 config_diff_report
    assert payload["title"].startswith("配置检查报告")
    assert payload["cluster_name"] == "Kubernetes - 1"


def test_emit_report_event_skips_when_renderer_returns_none():
    """skill 包声明了 capability 但数据无效(没有 issues_detail)→ 渲染器返 None → dispatch 不发。"""
    node = _make_node(skill_capabilities=["config_analysis_report"])
    parsed = {"cluster_name": "x"}  # 没 issues_detail

    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        result = node._emit_report_event("config_analysis_report", parsed)

    assert result is None
    mock_dispatch.assert_not_called()


def test_emit_report_event_dispatches_repair_diff_with_items_list():
    """repair_diff_report 接 list[items] shape,事件名 = repair_diff_report。"""
    node = _make_node(skill_capabilities=["repair_diff_report"])
    items = [
        {
            "workload_name": "admin-panel",
            "workload_type": "Deployment",
            "namespace": "production",
            "severity": "high",
            "summary": "缺探针",
            "before_yaml": "x: 1",
            "after_yaml": "x: 2",
        }
    ]
    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        result = node._emit_report_event("repair_diff_report", items)

    assert result is not None
    mock_dispatch.assert_called_once()
    event_name, payload = mock_dispatch.call_args.args
    assert event_name == "repair_diff_report"
    assert payload["title"].startswith("修复对比")
    assert len(payload["items"]) == 1
    assert payload["items"][0]["workload_name"] == "admin-panel"


def test_emit_report_event_skips_unknown_capability_even_if_declared():
    """skill 包声明了一个不存在的 capability(不在 RENDERER_REGISTRY 里)→ 静默跳过。"""
    node = _make_node(skill_capabilities=["future_capability_not_yet_built"])
    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        result = node._emit_report_event("future_capability_not_yet_built", {"x": 1})

    assert result is None
    mock_dispatch.assert_not_called()


def test_dispatch_isolates_two_capabilities():
    """声明了 config_analysis_report 但没声明 repair_diff_report → 只前者能发,后者不响。"""
    node = _make_node(skill_capabilities=["config_analysis_report"])

    parsed_analysis = {
        "cluster_name": "c",
        "issues_detail": [{"severity": "high", "issue": "i", "count": 1, "workloads": []}],
    }
    items_diff = [
        {
            "workload_name": "x",
            "workload_type": "Deployment",
            "namespace": "n",
            "severity": "high",
            "summary": "s",
            "before_yaml": "",
            "after_yaml": "",
        }
    ]

    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        r1 = node._emit_report_event("config_analysis_report", parsed_analysis)
        r2 = node._emit_report_event("repair_diff_report", items_diff)

    assert r1 is not None  # declared → emitted
    assert r2 is None      # NOT declared → skipped
    # 只发了一次,且是 config_analysis_report
    assert mock_dispatch.call_count == 1
    assert mock_dispatch.call_args.args[0] == "config_analysis_report"


def test_deepagent_exposes_repair_workflow_tools_only_with_both_capabilities():
    node = _make_node(skill_capabilities=["config_analysis_report", "repair_diff_report"])
    node.all_tools = []
    node.tools = []

    with patch.object(node, "_build_knowledge_retrieve_tool", return_value=None):
        tools = node._collect_deepagent_tools(object())

    names = {tool.name for tool in tools}
    assert {"request_user_choice", "generate_repair_report", "report_config_diff"} <= names


@pytest.mark.parametrize("capability", ["config_analysis_report", "repair_diff_report"])
def test_deepagent_does_not_expose_repair_workflow_tools_for_single_capability(capability):
    node = _make_node(skill_capabilities=[capability])
    node.all_tools = []
    node.tools = []

    with patch.object(node, "_build_knowledge_retrieve_tool", return_value=None):
        tools = node._collect_deepagent_tools(object())

    names = {tool.name for tool in tools}
    assert names.isdisjoint({"request_user_choice", "generate_repair_report", "report_config_diff"})


@pytest.mark.asyncio
async def test_pending_analysis_deterministically_runs_choice_then_repair_report():
    from langchain_core.messages import ToolMessage

    node = _make_node(skill_capabilities=["config_analysis_report", "repair_diff_report"])
    choice_tool = MagicMock()
    choice_tool.ainvoke = AsyncMock(return_value="用户回答: 按问题类别聚合。请继续执行。")
    choice_tool._request_choice_func = MagicMock()
    repair_tool = MagicMock()
    repair_tool.ainvoke = AsyncMock(return_value="已生成修复对比报告")
    deployments = [{"name": "api", "namespace": "default", "issues": ["未配置资源限制"]}]
    messages = [
        ToolMessage(
            name="analyze_deployment_configurations",
            tool_call_id="analysis-1",
            content=(
                '{"cluster_name":"Kubernetes - 1","problematic":1,'
                '"issues_detail":[{"severity":"high","issue":"未配置资源限制","count":1,"workloads":["api"]}],'
                '"_deployments_full":[{"name":"api","namespace":"default","issues":["未配置资源限制"]}]}'
            ),
        )
    ]

    with (
        patch.object(node, "_build_choice_tool", return_value=choice_tool),
        patch.object(node, "_build_bulk_repair_tool", return_value=repair_tool) as build_repair,
    ):
        handled = await node._run_pending_k8s_repair_workflow(messages, {"configurable": {"execution_id": "exec-1"}})

    assert handled is True
    choice_tool.ainvoke.assert_awaited_once()
    assert choice_tool._request_choice_func._node_id == "skill_test"
    build_repair.assert_called_once_with({"deployments": deployments, "cluster_name": "Kubernetes - 1"})
    repair_args = repair_tool.ainvoke.await_args.args[0]
    assert repair_args["group_by"] == "category"
    assert repair_args["items"] == []


@pytest.mark.asyncio
async def test_pending_analysis_uses_full_details_from_runnable_config_cache():
    from langchain_core.messages import ToolMessage

    node = _make_node(skill_capabilities=["config_analysis_report", "repair_diff_report"])
    choice_tool = MagicMock()
    choice_tool.ainvoke = AsyncMock(return_value="全部一次性展示")
    choice_tool._request_choice_func = MagicMock()
    repair_tool = MagicMock()
    repair_tool.ainvoke = AsyncMock(return_value="已生成修复对比报告")
    deployments = [{"name": "api", "namespace": "default", "issues": ["未配置资源限制"]}]
    messages = [
        ToolMessage(
            name="analyze_deployment_configurations",
            tool_call_id="analysis-large",
            content=(
                '{"cluster_name":"Kubernetes - 1","problematic":1,'
                '"issues_detail":[{"severity":"high","issue":"未配置资源限制",'
                '"count":1,"workloads":["api"]}]}'
            ),
        )
    ]
    config = {"configurable": {"execution_id": "exec-large"}}

    with (
        patch(
            "apps.opspilot.metis.llm.tools.kubernetes.analysis._take_cached_k8s_analysis_details",
            return_value=deployments,
        ),
        patch.object(node, "_build_choice_tool", return_value=choice_tool),
        patch.object(node, "_build_bulk_repair_tool", return_value=repair_tool) as build_repair,
    ):
        handled = await node._run_pending_k8s_repair_workflow(messages, config)

    assert handled is True
    build_repair.assert_called_once_with({"deployments": deployments, "cluster_name": "Kubernetes - 1"})


@pytest.mark.asyncio
async def test_pending_analysis_does_not_run_workflow_for_single_capability():
    node = _make_node(skill_capabilities=["config_analysis_report"])

    handled = await node._run_pending_k8s_repair_workflow([], {"configurable": {}})

    assert handled is False


@pytest.mark.asyncio
async def test_choice_custom_events_use_explicit_runnable_config():
    node = _make_node(skill_capabilities=["config_analysis_report", "repair_diff_report"])
    choice_tool = node._build_choice_tool()
    choice_func = choice_tool._request_choice_func
    choice_func._configurable = {}
    choice_func._execution_id = "exec-1"
    choice_func._node_id = "repair-flow"
    runnable_config = {"configurable": {"execution_id": "exec-1"}}

    with (
        patch("apps.opspilot.metis.llm.chain.node.wait_for_choice", new=AsyncMock(return_value={"selected": ["按问题类别聚合"], "source": "user"})),
        patch("apps.opspilot.metis.llm.chain.node.dispatch_custom_event") as dispatch,
    ):
        await choice_func(
            question="请选择修复展示方式",
            question_type="single_select",
            options=["按问题类别聚合", "按工作负载聚合"],
            config=runnable_config,
        )

    assert dispatch.call_count == 2
    assert all(call.kwargs["config"] is runnable_config for call in dispatch.call_args_list)


def test_post_process_tool_results_dispatches_mapped_tool():
    """ToolMessage.name 命中 TOOL_RESULT_TO_CAPABILITY 时,自动 dispatch 对应 capability。"""
    from langchain_core.messages import ToolMessage

    from apps.opspilot.metis.llm.chain.k8s_report_tools import (
        TOOL_RESULT_TO_CAPABILITY,
    )

    node = _make_node(skill_capabilities=["config_analysis_report"])
    assert TOOL_RESULT_TO_CAPABILITY.get("analyze_deployment_configurations") == "config_analysis_report"

    tool_message = ToolMessage(
        name="analyze_deployment_configurations",
        content=(
            '{"cluster_name": "Kubernetes - 1", "total": 9, "problematic": 9, '
            '"issues_detail": [{"severity": "high", "issue": "缺探针", '
            '"count": 7, "workloads": ["admin-panel"]}]}'
        ),
        tool_call_id="call-1",
    )

    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        node._post_process_tool_results([tool_message])

    assert mock_dispatch.call_count == 1
    event_name, payload = mock_dispatch.call_args.args
    assert event_name == "config_analysis_report"
    assert payload["title"].startswith("配置检查报告")


def test_post_process_tool_results_skips_unmapped_tool():
    """未在 TOOL_RESULT_TO_CAPABILITY 里的 tool → 完全静默,不 dispatch。"""
    from langchain_core.messages import ToolMessage

    node = _make_node(skill_capabilities=["config_analysis_report"])
    tool_message = ToolMessage(
        name="some_unrelated_tool",
        content='{"x": 1}',
        tool_call_id="call-1",
    )

    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        node._post_process_tool_results([tool_message])

    mock_dispatch.assert_not_called()


def test_post_process_tool_results_handles_invalid_json():
    """ToolMessage.content 不是合法 JSON → 跳过该条,不抛异常。"""
    from langchain_core.messages import ToolMessage

    node = _make_node(skill_capabilities=["config_analysis_report"])
    tool_message = ToolMessage(
        name="analyze_deployment_configurations",
        content="not a valid json {{",
        tool_call_id="call-1",
    )

    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        # 不应抛异常
        node._post_process_tool_results([tool_message])

    mock_dispatch.assert_not_called()


def test_post_process_tool_results_skips_when_capability_not_declared():
    """tool name 命中映射,但 skill 包没声明该 capability → 仍然静默。"""
    from langchain_core.messages import ToolMessage

    node = _make_node(skill_capabilities=[])  # 空,什么都不声明
    tool_message = ToolMessage(
        name="analyze_deployment_configurations",
        content='{"cluster_name": "x", "issues_detail": [{"severity": "high", "issue": "i", "count": 1, "workloads": []}]}',
        tool_call_id="call-1",
    )

    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        node._post_process_tool_results([tool_message])

    # renderer 返 None(因为 should_emit_config_analysis_report 失败)或 emit 跳过
    mock_dispatch.assert_not_called()


def test_post_process_tool_results_iterates_only_tool_messages():
    """非 ToolMessage(AIMessage / HumanMessage / SystemMessage)直接忽略。"""
    from langchain_core.messages import AIMessage, HumanMessage

    node = _make_node(skill_capabilities=["config_analysis_report"])

    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        node._post_process_tool_results([
            HumanMessage(content="hi"),
            AIMessage(content="thinking"),
        ])

    mock_dispatch.assert_not_called()


def test_post_process_tool_results_coalesces_multiple_calls_into_one_card():
    """LLM 多次调 analyze_deployment_configurations(每 namespace 一次)时,
    只 emit 一张合并后的卡,而不是 N 张(用户反馈:7 个 namespace 出了 7 张卡)。"""
    from langchain_core.messages import ToolMessage

    node = _make_node(skill_capabilities=["config_analysis_report"])
    tool_messages = []
    for i, (ns, total) in enumerate([("production", 9), ("dev", 10), ("staging", 8), ("search", 1), ("order", 1), ("payment", 1), ("gateway", 1)]):
        tool_messages.append(
            ToolMessage(
                name="analyze_deployment_configurations",
                content=(
                    f'{{"cluster_name": "Kubernetes - 1", "namespace": "{ns}", "total": {total}, '
                    f'"problematic": {total}, "issues_detail": [{{"severity": "high", "issue": "缺探针 {ns}", '
                    f'"count": 1, "workloads": ["{ns}-pod"]}}]}}'
                ),
                tool_call_id=f"call-{i}",
            )
        )

    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        node._post_process_tool_results(tool_messages)

    # 关键断言:7 次调用,只 emit 1 张卡
    assert mock_dispatch.call_count == 1, (
        f"Expected 1 merged report, got {mock_dispatch.call_count} cards"
    )
    event_name, payload = mock_dispatch.call_args.args
    assert event_name == "config_analysis_report"
    # total / problematic 累加后写到 summary
    assert payload["summary"]["total"] == 31
    assert payload["summary"]["problematic"] == 31
    # 7 个 namespace 的 issues 合并到 severity_sections(单 severity "high" 段下挂着 7 条)
    high_section = next(s for s in payload["severity_sections"] if s["severity"] == "high")
    assert len(high_section["issues"]) == 7


def test_post_process_tool_results_waits_for_user_choice_before_repair_diff():
    """双 capability 也必须先让用户选择，分析后不得自动发修复对比。"""
    from langchain_core.messages import ToolMessage

    node = _make_node(
        skill_capabilities=["config_analysis_report", "repair_diff_report"],
    )

    tool_message = ToolMessage(
        name="analyze_deployment_configurations",
        content=(
            '{"cluster_name": "Kubernetes - 1", "total": 3, "problematic": 2, '
            '"issues_detail": [{"severity": "high", "issue": "缺存活探针", '
            '"count": 2, "workloads": ["admin-panel", "api-gateway"]}]}'
        ),
        tool_call_id="call-1",
    )

    with patch("langchain_core.callbacks.dispatch_custom_event") as mock_dispatch:
        node._post_process_tool_results([tool_message], skill_id=42)

    assert mock_dispatch.call_count == 1
    event_name, _ = mock_dispatch.call_args.args
    assert event_name == "config_analysis_report"
