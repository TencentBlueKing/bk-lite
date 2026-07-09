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
from unittest.mock import patch

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
