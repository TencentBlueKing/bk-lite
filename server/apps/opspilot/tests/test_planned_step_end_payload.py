from langchain_core.messages import AIMessage, ToolMessage

from apps.opspilot.metis.llm.chain.node import build_planned_step_end_payload, tools_invoked_in_step


def test_overflow_empty_messages_are_skipped_not_reused():
    payload = build_planned_step_end_payload(
        step_index=1,
        total_steps=2,
        objective="查日志",
        planned_tools=["get_kubernetes_pod_logs"],
        step_messages=[],
        status="skipped_context_overflow",
    )
    assert payload["status"] == "skipped_context_overflow"
    assert payload["tools_invoked"] == []
    assert "outcome" not in payload


def test_missing_params_empty_messages_are_not_reused():
    payload = build_planned_step_end_payload(
        step_index=2,
        total_steps=2,
        objective="查指标",
        planned_tools=["monitor_query"],
        step_messages=[],
        status="missing_params",
    )
    assert payload["status"] == "missing_params"
    assert "outcome" not in payload


def test_target_unresolved_is_not_reused():
    payload = build_planned_step_end_payload(
        step_index=1,
        total_steps=3,
        objective="定位对象",
        planned_tools=["resolve_k8s_target_from_alert"],
        step_messages=[ToolMessage(content="无法定位", tool_call_id="c1", name="resolve_k8s_target_from_alert")],
        status="target_unresolved",
    )
    assert payload["status"] == "target_unresolved"
    assert payload["tools_invoked"] == ["resolve_k8s_target_from_alert"]
    assert "outcome" not in payload


def test_failed_status_is_not_reused():
    payload = build_planned_step_end_payload(
        step_index=1,
        total_steps=1,
        objective="诊断",
        planned_tools=["diagnose"],
        step_messages=[],
        status="failed_config",
        error="无法加载配置",
    )
    assert payload["status"] == "failed_config"
    assert payload["error"] == "无法加载配置"
    assert "outcome" not in payload


def test_reuse_only_when_explicitly_marked():
    payload = build_planned_step_end_payload(
        step_index=2,
        total_steps=2,
        objective="汇总",
        planned_tools=["alerts_list_alerts"],
        step_messages=[AIMessage(content="沿用上一步告警列表")],
        reused=True,
    )
    assert payload["outcome"] == "reused_prior_result"
    assert payload["tools_invoked"] == []
    assert "status" not in payload


def test_success_with_tools_has_no_reuse_outcome():
    payload = build_planned_step_end_payload(
        step_index=1,
        total_steps=1,
        objective="查告警",
        planned_tools=["alerts_list_alerts"],
        step_messages=[ToolMessage(content="ok", tool_call_id="c1", name="alerts_list_alerts")],
        reused=False,
    )
    assert payload["tools_invoked"] == ["alerts_list_alerts"]
    assert "outcome" not in payload


def test_tools_invoked_in_step_dedupes_names():
    assert tools_invoked_in_step(
        [
            ToolMessage(content="a", tool_call_id="1", name="alerts_list_alerts"),
            AIMessage(content="thinking"),
            ToolMessage(content="b", tool_call_id="2", name="alerts_list_alerts"),
            ToolMessage(content="c", tool_call_id="3", name="cmdb_search_instances"),
        ]
    ) == ["alerts_list_alerts", "cmdb_search_instances"]
