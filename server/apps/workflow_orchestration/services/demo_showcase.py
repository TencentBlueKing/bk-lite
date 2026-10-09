from __future__ import annotations

import copy
from typing import Any

from apps.workflow_orchestration.services.definitions import build_health_inspection_canvas_metadata, build_health_inspection_definition

SHOWCASE_ATOM_KEYS = (
    "bklite_document_render",
    "bklite_http_request",
    "bklite_job_execute",
    "bklite_notification",
)


def _schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


def _definition(description: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": "workflow_showcase_draft",
        "description": description,
        "version": 1,
        "schemaVersion": 2,
        "ownerEmail": "bklite@weops.com",
        "inputParameters": ["team", "actor", "execution_id"],
        "outputParameters": {},
        "tasks": tasks,
        "restartable": True,
        "workflowStatusListenerEnabled": False,
    }


def _metadata(
    *,
    triggers: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    positions: dict[str, dict[str, int]],
    node_titles: dict[str, str],
    return_nodes: list[dict[str, Any]] | None = None,
    risk_level: str = "low",
    risk_description: str = "只读演示流程。",
) -> dict[str, Any]:
    return {
        "control_flow_mode": "EDGES",
        "trigger_nodes": triggers,
        "return_nodes": return_nodes or [],
        "positions": positions,
        "node_titles": node_titles,
        "edges": edges,
        "input_schema": _schema(),
        "data_contract": {
            "version": 1,
            "systemContextVersion": 1,
            "inputs": [],
            "constants": [],
            "outputs": [],
        },
        "risk_summary": {"level": risk_level, "description": risk_description},
    }


def _notification(reference: str, *, channel_id: int, username: str, title: str, body: str) -> dict[str, Any]:
    return {
        "name": "bklite_notification",
        "taskReferenceName": reference,
        "type": "SIMPLE",
        "inputParameters": {
            "notification_type": "EMAIL",
            "channel_id": channel_id,
            "recipients": [username],
            "title": title,
            "body": body,
            "team": "${workflow.input.team}",
            "execution_id": "${workflow.input.execution_id}",
            "task_reference": reference,
        },
    }


def build_approval_workflow(*, channel_id: int, username: str) -> dict[str, Any]:
    trigger = {
        "id": "trigger_form",
        "name": "生产变更申请",
        "trigger_type": "FORM",
        "input_schema": _schema(
            {
                "change_title": {"type": "string", "title": "变更标题", "maxLength": 120},
                "change_detail": {"type": "string", "title": "变更内容", "maxLength": 1000},
            },
            ["change_title", "change_detail"],
        ),
        "config": {},
    }
    approval = {
        "name": "manual_approval",
        "taskReferenceName": "approve_change",
        "type": "HUMAN",
        "inputParameters": {
            "interactionType": "APPROVAL",
            "title": "生产变更审批",
            "description": "请确认变更范围、风险和回退方案。",
            "candidates": [username],
            "publicContext": {
                "change_title": "${workflow.input.change_title}",
                "change_detail": "${workflow.input.change_detail}",
            },
        },
    }
    approved = _notification(
        "notify_approved",
        channel_id=channel_id,
        username=username,
        title="生产变更已批准",
        body="审批已通过，可以进入后续执行窗口。",
    )
    rejected = _notification(
        "notify_rejected",
        channel_id=channel_id,
        username=username,
        title="生产变更已驳回",
        body="审批未通过，请根据审批意见修改后重新提交。",
    )
    decision = {
        "name": "approval_decision",
        "taskReferenceName": "approval_decision",
        "type": "SWITCH",
        "inputParameters": {"decision": "${approve_change.output.approved}"},
        "evaluatorType": "value-param",
        "expression": "decision",
        "decisionCases": {"true": [approved], "false": [rejected]},
        "defaultCase": [],
    }
    return {
        "key": "approval",
        "engine_name": "bklite_demo_change_approval",
        "name": "[TDD/BDD] 生产变更审批",
        "description": "表单发起生产变更，人工审批后按通过/驳回分支发送通知。",
        "definition": _definition("人工审批与互斥分支通知", [approval, decision]),
        "metadata": _metadata(
            triggers=[trigger],
            edges=[
                {"id": "trigger-approval", "source": "trigger_form", "target": "approve_change"},
                {"id": "approval-decision", "source": "approve_change", "target": "approval_decision"},
                {"id": "approved-notify", "source": "approval_decision", "target": "notify_approved", "sourceHandle": "true"},
                {"id": "rejected-notify", "source": "approval_decision", "target": "notify_rejected", "sourceHandle": "false"},
            ],
            positions={
                "trigger_form": {"x": 20, "y": 260},
                "approve_change": {"x": 290, "y": 260},
                "approval_decision": {"x": 550, "y": 260},
                "notify_approved": {"x": 840, "y": 140},
                "notify_rejected": {"x": 840, "y": 380},
            },
            node_titles={
                "approve_change": "生产变更审批",
                "approval_decision": "审批结果",
                "notify_approved": "通知变更通过",
                "notify_rejected": "通知变更驳回",
            },
            risk_level="high",
            risk_description="人工审批决定后续分支，本示例仅发送通知，不执行变更。",
        ),
    }


def build_webhook_workflow() -> dict[str, Any]:
    trigger = {
        "id": "trigger_webhook",
        "name": "同步 Webhook",
        "trigger_type": "WEBHOOK",
        "input_schema": _schema({"message": {"type": "string", "title": "请求内容"}}, ["message"]),
        "config": {"response_mode": "WAIT"},
    }
    request = {
        "name": "bklite_http_request",
        "taskReferenceName": "lookup_service",
        "type": "SIMPLE",
        "inputParameters": {
            "method": "GET",
            "url": "https://example.com/",
            "timeout": 15,
            "response_format": "TEXT",
            "success_status_codes": [],
            "team": "${workflow.input.team}",
        },
    }
    response = {
        "id": "webhook_response",
        "name": "Webhook 响应",
        "return_type": "WEBHOOK",
        "config": {"body": "${lookup_service.output}"},
    }
    return {
        "key": "webhook",
        "engine_name": "bklite_demo_webhook_sync",
        "name": "[TDD/BDD] Webhook 同步响应",
        "description": "Webhook 等待流程完成，经过 HTTP 节点后由响应节点返回。",
        "definition": _definition("Webhook 等待模式与显式响应", [request]),
        "metadata": _metadata(
            triggers=[trigger],
            return_nodes=[response],
            edges=[
                {"id": "webhook-http", "source": "trigger_webhook", "target": "lookup_service"},
                {"id": "http-response", "source": "lookup_service", "target": "webhook_response"},
            ],
            positions={
                "trigger_webhook": {"x": 20, "y": 260},
                "lookup_service": {"x": 330, "y": 260},
                "webhook_response": {"x": 650, "y": 260},
            },
            node_titles={"lookup_service": "调用 HTTP 服务"},
            risk_level="medium",
            risk_description="向已配置的 HTTP URL 发起只读请求。",
        ),
    }


def build_scheduled_http_workflow(*, channel_id: int, username: str) -> dict[str, Any]:
    trigger = {
        "id": "trigger_schedule",
        "name": "每日接口检查",
        "trigger_type": "SCHEDULE",
        "input_schema": _schema(),
        "config": {"expression": "0 9 * * *", "timezone": "Asia/Shanghai"},
    }
    request = {
        "name": "bklite_http_request",
        "taskReferenceName": "check_endpoint",
        "type": "SIMPLE",
        "inputParameters": {
            "method": "GET",
            "url": "https://example.com/",
            "timeout": 15,
            "response_format": "TEXT",
            "success_status_codes": [],
            "team": "${workflow.input.team}",
        },
    }
    notify = _notification(
        "notify_http_result",
        channel_id=channel_id,
        username=username,
        title="每日 HTTP 检查完成",
        body="HTTP 端点已完成检查，请在执行记录中查看响应。",
    )
    return {
        "key": "scheduled_http",
        "engine_name": "bklite_demo_scheduled_http",
        "name": "[TDD/BDD] 定时 HTTP 检查",
        "description": "定时调用 HTTP URL，完成后发送通知。",
        "definition": _definition("定时 HTTP 检查与通知", [request, notify]),
        "metadata": _metadata(
            triggers=[trigger],
            edges=[
                {"id": "schedule-http", "source": "trigger_schedule", "target": "check_endpoint"},
                {"id": "http-notify", "source": "check_endpoint", "target": "notify_http_result"},
            ],
            positions={
                "trigger_schedule": {"x": 20, "y": 260},
                "check_endpoint": {"x": 330, "y": 260},
                "notify_http_result": {"x": 650, "y": 260},
            },
            node_titles={"check_endpoint": "检查 HTTP 端点", "notify_http_result": "发送检查结果"},
            risk_level="medium",
            risk_description="定时向已配置的 HTTP URL 发起只读 GET，随后发送内部通知。",
        ),
    }


def build_nats_workflow(*, channel_id: int, username: str) -> dict[str, Any]:
    trigger = {
        "id": "trigger_nats",
        "name": "运维事件触发器",
        "trigger_type": "NATS",
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": True},
        "config": {},
    }
    notify = _notification(
        "notify_event",
        channel_id=channel_id,
        username=username,
        title="收到内部运维事件",
        body="${workflow.input.message}",
    )
    return {
        "key": "nats",
        "engine_name": "bklite_demo_nats_event",
        "name": "[TDD/BDD] NATS 事件通知",
        "description": "使用标准事件信封接收 NATS 事件，event_id 固定用作幂等键。",
        "definition": _definition("NATS 标准事件信封与通知", [notify]),
        "metadata": _metadata(
            triggers=[trigger],
            edges=[{"id": "nats-notify", "source": "trigger_nats", "target": "notify_event"}],
            positions={"trigger_nats": {"x": 20, "y": 260}, "notify_event": {"x": 350, "y": 260}},
            node_titles={"notify_event": "通知事件"},
        ),
    }


def build_multi_trigger_workflow(*, channel_id: int, username: str) -> dict[str, Any]:
    triggers = [
        {
            "id": "trigger_form",
            "name": "人工触发",
            "trigger_type": "FORM",
            "input_schema": _schema(),
            "config": {},
        },
        {
            "id": "trigger_webhook",
            "name": "告警 Webhook",
            "trigger_type": "WEBHOOK",
            "input_schema": _schema(),
            "config": {"response_mode": "IMMEDIATE"},
        },
        {
            "id": "trigger_schedule",
            "name": "每六小时巡检",
            "trigger_type": "SCHEDULE",
            "input_schema": _schema(),
            "config": {"expression": "0 */6 * * *", "timezone": "Asia/Shanghai"},
        },
    ]
    notify = _notification(
        "notify_trigger_result",
        channel_id=channel_id,
        username=username,
        title="多入口流程已触发",
        body="本次事件已从其中一个入口创建独立执行记录。",
    )
    return {
        "key": "multi_trigger",
        "engine_name": "bklite_demo_multi_trigger",
        "name": "[TDD/BDD] 多入口通知",
        "description": "表单、Webhook 与定时入口同时生效，每次触发生成独立执行记录。",
        "definition": _definition("同一流程的多个独立触发入口", [notify]),
        "metadata": _metadata(
            triggers=triggers,
            edges=[
                {"id": "form-notify", "source": "trigger_form", "target": "notify_trigger_result"},
                {"id": "webhook-notify", "source": "trigger_webhook", "target": "notify_trigger_result"},
                {"id": "schedule-notify", "source": "trigger_schedule", "target": "notify_trigger_result"},
            ],
            positions={
                "trigger_form": {"x": 20, "y": 100},
                "trigger_webhook": {"x": 20, "y": 260},
                "trigger_schedule": {"x": 20, "y": 420},
                "notify_trigger_result": {"x": 390, "y": 260},
            },
            node_titles={"notify_trigger_result": "通知触发结果"},
        ),
    }


def build_health_inspection_showcase_workflow(
    *,
    team_id: int,
    channel_id: int,
    username: str,
    fmt: str,
    template_snapshot: dict[str, Any],
    script_type: str,
    script_content: str,
) -> dict[str, Any]:
    normalized = str(fmt or "").lower()
    if normalized not in {"docx", "xlsx"}:
        raise ValueError("健康巡检演示流程只支持 docx 或 xlsx")
    if not isinstance(template_snapshot, dict) or template_snapshot.get("format") != normalized:
        raise ValueError("健康巡检模板快照与目标格式不一致")
    label = "Word" if normalized == "docx" else "Excel"
    definition = build_health_inspection_definition()
    definition["description"] = f"主机健康巡检（{label}）：授权主机采集后生成 {label} 报告并通知"
    scan = definition["tasks"][0]["inputParameters"]
    scan.update(
        {
            "script_type": script_type,
            "script_content": script_content,
            "execution_params": "",
            "timeout_seconds": 600,
        }
    )
    report = definition["tasks"][1]["inputParameters"]
    report["template_snapshot"] = copy.deepcopy(template_snapshot)
    notify = definition["tasks"][2]["inputParameters"]
    notify.update(
        {
            "channel_id": channel_id,
            "recipients": [username],
            "title": f"主机健康巡检报告（{label}）",
            "body": f"主机健康巡检已完成，请下载 {label} 报告。",
        }
    )
    metadata = build_health_inspection_canvas_metadata()
    metadata["node_titles"] = {
        **metadata.get("node_titles", {}),
        "scan": "作业执行",
        "report": f"生成{label}报告",
        "notify": "发送巡检通知",
    }
    metadata["risk_summary"] = {
        "level": "low",
        "description": f"在授权主机上执行只读健康采集并生成 {label} 巡检报告。",
    }
    return {
        "key": f"health_{normalized}",
        "engine_name": f"bklite_demo_health_inspection_{normalized}_team_{team_id}",
        "name": f"[TDD/BDD] 主机健康巡检 {label}",
        "description": f"用户选择授权主机，按发布版本中的脚本和 {label} 模板生成报告并通知。",
        "definition": definition,
        "metadata": metadata,
    }


def build_additional_showcase_workflows(*, team_id: int, channel_id: int, username: str) -> list[dict[str, Any]]:
    workflows = [
        build_approval_workflow(channel_id=channel_id, username=username),
        build_webhook_workflow(),
        build_scheduled_http_workflow(channel_id=channel_id, username=username),
        build_nats_workflow(channel_id=channel_id, username=username),
        build_multi_trigger_workflow(channel_id=channel_id, username=username),
    ]
    for item in workflows:
        item["engine_name"] = f"{item['engine_name']}_team_{team_id}"
    return workflows
