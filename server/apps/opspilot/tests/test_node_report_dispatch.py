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


def test_deepagent_does_not_expose_internal_repair_workflow_tools():
    node = _make_node(skill_capabilities=["config_analysis_report", "repair_diff_report"])
    node.all_tools = []
    node.tools = []

    with patch.object(node, "_build_knowledge_retrieve_tool", return_value=None):
        tools = node._collect_deepagent_tools(object())

    names = {tool.name for tool in tools}
    assert names.isdisjoint({"request_user_choice", "generate_repair_report", "report_config_diff"})


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
async def test_completed_choice_deterministically_continues_to_repair_report():
    """模型在用户完成选择后停住时，后端必须继续生成修复报告，且不能再次提问。"""
    from langchain_core.messages import AIMessage, ToolMessage

    node = _make_node(skill_capabilities=["config_analysis_report", "repair_diff_report"])
    choice_tool = MagicMock()
    choice_tool.ainvoke = AsyncMock(side_effect=AssertionError("已完成选择，不应再次提问"))
    choice_tool._request_choice_func = MagicMock()
    repair_tool = MagicMock()
    repair_tool.ainvoke = AsyncMock(return_value="已生成修复对比报告")
    messages = [
        ToolMessage(
            name="analyze_deployment_configurations",
            tool_call_id="analysis-before-choice",
            content=(
                '{"cluster_name":"Kubernetes - 2","problematic":60,'
                '"issues_detail":[{"severity":"high","issue":"未配置存活探针",'
                '"count":59,"workloads":["api (prod)"]}],'
                '"_deployments_full":[{"name":"api","namespace":"prod",'
                '"issues":["未配置存活探针"]}]}'
            ),
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "request_user_choice",
                    "args": {"question": "请选择修复展示方式"},
                    "id": "choice-call",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            name="request_user_choice",
            tool_call_id="choice-call",
            content="用户回答: 按工作负载聚合。请根据用户的回答继续执行下一步操作，不要停止。",
        ),
    ]

    with (
        patch.object(node, "_build_choice_tool", return_value=choice_tool),
        patch.object(node, "_build_bulk_repair_tool", return_value=repair_tool),
    ):
        handled = await node._run_pending_k8s_repair_workflow(
            messages,
            {"configurable": {"execution_id": "exec-choice-complete"}},
        )

    assert handled is True
    choice_tool.ainvoke.assert_not_awaited()
    repair_tool.ainvoke.assert_awaited_once()
    assert repair_tool.ainvoke.await_args.args[0]["group_by"] == "target"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("choice", "expected_type", "expected_target_labels"),
    [
        ("全部一次性展示", "All", {"全部（60 个目标）"}),
        ("按空间聚合", "Scope", {"production（30 个目标）", "staging（30 个目标）"}),
        ("按风险等级聚合", "Severity", {"高危（60 个目标）"}),
    ],
)
async def test_sixty_object_choice_emits_one_repair_diff_event_from_full_cache(
    choice,
    expected_type,
    expected_target_labels,
):
    """60 对象选择完成后必须从完整缓存生成且只推送一张修复对比卡。"""
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.runnables import RunnableLambda

    from apps.opspilot.metis.llm.tools.kubernetes.analysis import _cache_k8s_analysis_details

    execution_id = f"exec-sixty-repair-event-{expected_type.lower()}"
    deployments = [
        {
            "name": f"scan-fixture-{index:03d}",
            "namespace": "production" if index % 2 else "staging",
            "issues": [f"未设置资源限制-{issue_index}" for issue_index in range(5)],
            "config_analysis": {},
        }
        for index in range(60)
    ]
    _cache_k8s_analysis_details(execution_id, deployments)
    node = _make_node(skill_capabilities=["config_analysis_report", "repair_diff_report"])
    messages = [
        ToolMessage(
            name="analyze_deployment_configurations",
            tool_call_id="analysis-sixty",
            content=(
                '{"cluster_name":"Kubernetes - 2","problematic":60,'
                '"issues_detail":[{"severity":"high","issue":"未设置资源限制",'
                '"count":60,"workloads":["scan-fixture-001 (production)"]}]}'
            ),
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "request_user_choice",
                    "args": {"question": "请选择修复展示方式"},
                    "id": "choice-sixty",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            name="request_user_choice",
            tool_call_id="choice-sixty",
            content=f"用户回答: {choice}。请根据用户的回答继续执行下一步操作，不要停止。",
        ),
    ]

    async def _pipeline(_, config):
        return await node._run_pending_k8s_repair_workflow(messages, config)

    report_events = []
    download_events = []
    async for event in RunnableLambda(_pipeline).astream_events(
        {},
        config={"configurable": {"execution_id": execution_id}},
        version="v2",
    ):
        if event.get("event") == "on_custom_event" and event.get("name") == "repair_diff_report":
            report_events.append(event["data"])
        if event.get("event") == "on_custom_event" and event.get("name") == "report_file_download":
            download_events.append(event["data"])

    assert len(report_events) == 1
    assert len(download_events) == 1
    assert download_events[0]["filename"].endswith(".docx")
    assert download_events[0]["content_base64"]
    assert {item["workload_type"] for item in report_events[0]["items"]} == {expected_type}
    assert {item["workload_name"] for item in report_events[0]["items"]} == expected_target_labels


@pytest.mark.asyncio
async def test_slow_docx_generation_still_emits_download_for_severity_choice():
    """下载报告是双 capability 闭环必达结果，不能因固定 5 秒阈值静默丢失。"""
    import time

    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.runnables import RunnableLambda

    from apps.opspilot.metis.llm.tools.kubernetes.analysis import _cache_k8s_analysis_details

    execution_id = "exec-slow-severity-download"
    _cache_k8s_analysis_details(
        execution_id,
        [{"name": "api", "namespace": "production", "issues": ["未设置资源限制"]}],
    )
    node = _make_node(skill_capabilities=["config_analysis_report", "repair_diff_report"])
    messages = [
        ToolMessage(
            name="analyze_deployment_configurations",
            tool_call_id="analysis-slow-download",
            content=(
                '{"cluster_name":"Kubernetes - 2","problematic":1,'
                '"issues_detail":[{"severity":"high","issue":"未设置资源限制",'
                '"count":1,"workloads":["api (production)"]}]}'
            ),
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "request_user_choice",
                    "args": {"question": "请选择修复展示方式"},
                    "id": "choice-slow-download",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            name="request_user_choice",
            tool_call_id="choice-slow-download",
            content="用户回答: 按风险等级聚合。请继续。",
        ),
    ]

    def _slow_generate_docx(_):
        time.sleep(5.1)
        return b"docx"

    async def _pipeline(_, config):
        return await node._run_pending_k8s_repair_workflow(messages, config)

    event_names = []
    with patch(
        "apps.opspilot.metis.llm.tools.kubernetes.report_generator.generate_k8s_report_docx",
        side_effect=_slow_generate_docx,
    ):
        async for event in RunnableLambda(_pipeline).astream_events(
            {},
            config={"configurable": {"execution_id": execution_id}},
            version="v2",
        ):
            if event.get("event") == "on_custom_event":
                event_names.append(event.get("name"))

    assert "repair_diff_report" in event_names
    assert "report_file_download" in event_names


@pytest.mark.asyncio
async def test_deep_wrapper_checks_pending_repair_against_full_message_history():
    """HITL 恢复后分析在旧消息、选择在新消息时，状态机仍必须看到完整历史。"""
    from types import SimpleNamespace

    from langchain_core.messages import AIMessage, ToolMessage

    node = _make_node(skill_capabilities=["config_analysis_report", "repair_diff_report"])
    graph_builder = MagicMock()
    analysis = ToolMessage(
        name="analyze_deployment_configurations",
        tool_call_id="analysis-before-resume",
        content='{"problematic":60,"issues_detail":[{"severity":"high","issue":"缺探针","count":60}]}',
    )
    choice = ToolMessage(
        name="request_user_choice",
        tool_call_id="choice-after-resume",
        content="用户回答: 全部一次性展示。请继续。",
    )
    final_answer = AIMessage(content="已处理用户选择")
    final_messages = [analysis, choice, final_answer]
    deep_agent = MagicMock()
    deep_agent.ainvoke = AsyncMock(return_value={"messages": final_messages})
    node._run_pending_k8s_repair_workflow = AsyncMock(return_value=True)
    node._post_process_tool_results = MagicMock()
    node.get_llm_client = MagicMock(return_value=object())
    node._collect_deepagent_tools = MagicMock(return_value=[])
    node._build_skill_backend_and_sources = MagicMock(return_value=(None, [], None))
    node._build_interrupt_on = MagicMock(return_value=None)
    graph_request = SimpleNamespace(system_message_prompt="", skill_id=1)

    with (
        patch("apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template", return_value="system"),
        patch("apps.opspilot.metis.llm.chain.node.create_deep_agent", return_value=deep_agent),
    ):
        await node.build_deepagent_nodes(graph_builder)
        wrapper = graph_builder.add_node.call_args.args[1]
        await wrapper(
            {"messages": [analysis, choice]},
            {"configurable": {"graph_request": graph_request, "execution_id": "resume-full-history"}},
        )

    workflow_messages = node._run_pending_k8s_repair_workflow.await_args.args[0]
    assert workflow_messages == final_messages


@pytest.mark.asyncio
async def test_deep_wrapper_emits_config_choice_and_repair_events_in_order():
    """覆盖线上完整顺序：附加检查工具不能吞掉分析后的选择与修复报告。"""
    from types import SimpleNamespace

    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.runnables import RunnableLambda

    from apps.opspilot.metis.llm.tools.kubernetes.analysis import _cache_k8s_analysis_details

    execution_id = "exec-full-k8s-report-flow"
    deployments = [
        {
            "name": f"scan-fixture-{index:03d}",
            "namespace": "production" if index % 2 else "staging",
            "issues": ["未设置资源限制"],
            "config_analysis": {},
        }
        for index in range(60)
    ]
    _cache_k8s_analysis_details(execution_id, deployments)
    node = _make_node(skill_capabilities=["config_analysis_report", "repair_diff_report"])
    graph_builder = MagicMock()
    analysis = ToolMessage(
        name="analyze_deployment_configurations",
        tool_call_id="analysis-full-flow",
        content=(
            '{"cluster_name":"Kubernetes - 2","total":60,"problematic":60,"healthy":0,'
            '"issues_detail":[{"severity":"high","issue":"未设置资源限制",'
            '"count":60,"workloads":["scan-fixture-001 (production)"]}]}'
        ),
    )
    final_messages = [
        analysis,
        ToolMessage(name="check_kubernetes_statefulsets", tool_call_id="statefulsets", content="[]"),
        ToolMessage(name="check_kubernetes_daemonsets", tool_call_id="daemonsets", content="[]"),
        AIMessage(content="已通过结构化卡片展示详细报告。"),
    ]
    deep_agent = MagicMock()
    deep_agent.ainvoke = AsyncMock(return_value={"messages": final_messages})
    node.get_llm_client = MagicMock(return_value=object())
    node._collect_deepagent_tools = MagicMock(return_value=[])
    node._build_skill_backend_and_sources = MagicMock(return_value=(None, [], None))
    node._build_interrupt_on = MagicMock(return_value=None)
    graph_request = SimpleNamespace(system_message_prompt="", skill_id=1)

    with (
        patch("apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template", return_value="system"),
        patch("apps.opspilot.metis.llm.chain.node.create_deep_agent", return_value=deep_agent),
        patch(
            "apps.opspilot.metis.llm.chain.node.wait_for_choice",
            new=AsyncMock(return_value={"selected": ["全部一次性展示"], "source": "user"}),
        ),
    ):
        await node.build_deepagent_nodes(graph_builder)
        wrapper = graph_builder.add_node.call_args.args[1]

        async def _run_wrapper(_, config):
            return await wrapper({"messages": []}, config)

        event_names = []
        async for event in RunnableLambda(_run_wrapper).astream_events(
            {},
            config={
                "configurable": {
                    "graph_request": graph_request,
                    "execution_id": execution_id,
                }
            },
            version="v2",
        ):
            if event.get("event") == "on_custom_event":
                event_names.append(event.get("name"))

    assert event_names.count("config_analysis_report") == 1
    assert event_names.count("user_choice_request") == 1
    assert event_names.count("user_choice_result") == 1
    assert event_names.count("repair_diff_report") == 1
    assert event_names.index("config_analysis_report") < event_names.index("user_choice_request")
    assert event_names.index("user_choice_result") < event_names.index("repair_diff_report")


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


@pytest.mark.asyncio
async def test_choice_custom_events_are_visible_in_real_async_event_stream():
    """确定性修复状态机在异步节点中提问时，前端必须收到选择请求事件。"""
    from langchain_core.runnables import RunnableLambda

    node = _make_node(skill_capabilities=["config_analysis_report", "repair_diff_report"])
    choice_tool = node._build_choice_tool()
    choice_func = choice_tool._request_choice_func
    choice_func._configurable = {}
    choice_func._execution_id = "exec-choice-stream"
    choice_func._node_id = "repair-flow"

    async def _invoke_choice(_, config):
        return await choice_func(
            question="请选择修复展示方式",
            question_type="single_select",
            options=["全部一次性展示", "按空间聚合", "按风险等级聚合"],
            config=config,
        )

    event_names = []
    with patch(
        "apps.opspilot.metis.llm.chain.node.wait_for_choice",
        new=AsyncMock(return_value={"selected": ["全部一次性展示"], "source": "user"}),
    ):
        async for event in RunnableLambda(_invoke_choice).astream_events(
            {},
            config={"configurable": {"execution_id": "exec-choice-stream"}},
            version="v2",
        ):
            if event.get("event") == "on_custom_event":
                event_names.append(event.get("name"))

    assert event_names == ["user_choice_request", "user_choice_result"]


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


def test_post_process_tool_results_does_not_emit_immediate_report_twice():
    from langchain_core.messages import ToolMessage

    node = _make_node(skill_capabilities=["config_analysis_report"])
    tool_message = ToolMessage(
        name="analyze_deployment_configurations",
        content=(
            '{"cluster_name":"Kubernetes - 1","total":60,"problematic":60,'
            '"issues_detail":[{"severity":"high","issue":"缺探针","count":59,"workloads":[]}],'
            '"_report_emitted_capability":"config_analysis_report"}'
        ),
        tool_call_id="call-immediate",
    )

    with patch("langchain_core.callbacks.dispatch_custom_event") as dispatch:
        node._post_process_tool_results([tool_message])

    dispatch.assert_not_called()


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
