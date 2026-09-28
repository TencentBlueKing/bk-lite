from __future__ import annotations

import re
import time
from copy import deepcopy
from typing import Any

from django.conf import settings

from apps.workflow_orchestration.models import WorkflowExecution, WorkflowTrigger, WorkflowVersion
from apps.workflow_orchestration.services.conductor import ConductorClient
from apps.workflow_orchestration.services.executions import TERMINAL_STATUSES, apply_remote_execution

WEBHOOK_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "body": {
            "type": "object",
            "title": "请求正文",
            "properties": {},
            "additionalProperties": True,
        }
    },
    "required": ["body"],
    "additionalProperties": False,
}

_OUTPUT_REFERENCE = re.compile(r"^\$\{(?P<reference>[A-Za-z][A-Za-z0-9_-]{0,99})\.output(?:\.(?P<path>[^{}]+))?}$")


class WebhookResponseError(ValueError):
    pass


def webhook_input_schema() -> dict[str, Any]:
    return deepcopy(WEBHOOK_INPUT_SCHEMA)


def _response_reference(trigger: WorkflowTrigger, metadata: dict[str, Any]) -> str:
    trigger_nodes = metadata.get("trigger_nodes") or []
    trigger_node = next((item for item in trigger_nodes if isinstance(item, dict) and item.get("id") == trigger.node_key), None)
    if trigger_node is None:
        raise WebhookResponseError("已发布版本中找不到 Webhook 触发节点")

    adjacency: dict[str, set[str]] = {}
    for edge in metadata.get("edges") or []:
        if isinstance(edge, dict) and isinstance(edge.get("source"), str) and isinstance(edge.get("target"), str):
            adjacency.setdefault(edge["source"], set()).add(edge["target"])
    reachable = {trigger.node_key}
    pending = [trigger.node_key]
    while pending:
        current = pending.pop()
        for target in adjacency.get(current, set()):
            if target not in reachable:
                reachable.add(target)
                pending.append(target)

    responses = [
        item
        for item in metadata.get("return_nodes") or []
        if isinstance(item, dict) and item.get("id") in reachable and item.get("return_type") == "WEBHOOK"
    ]
    if len(responses) != 1:
        raise WebhookResponseError("等待模式必须且只能到达一个 Webhook 响应节点")
    body = (responses[0].get("config") or {}).get("body")
    if not isinstance(body, str) or not _OUTPUT_REFERENCE.fullmatch(body.strip()):
        raise WebhookResponseError("Webhook 响应节点必须选择一个结构化节点输出")
    return body.strip()


def _value_at_path(value: Any, path: str | None) -> Any:
    current = value
    for segment in (path or "").split(".") if path else ():
        if not isinstance(current, dict) or segment not in current:
            raise WebhookResponseError(f"Webhook 返回数据不存在字段 {path}")
        current = current[segment]
    return current


def _resolve_response(reference: str, remote: dict[str, Any]) -> Any:
    matched = _OUTPUT_REFERENCE.fullmatch(reference)
    if matched is None:
        raise WebhookResponseError("Webhook 响应引用非法")
    task = next(
        (
            item
            for item in remote.get("tasks") or []
            if isinstance(item, dict) and item.get("referenceTaskName") == matched.group("reference") and item.get("status") == "COMPLETED"
        ),
        None,
    )
    if task is None:
        raise WebhookResponseError("Webhook 响应引用的节点未成功完成")
    output = task.get("outputData") if isinstance(task.get("outputData"), dict) else {}
    return _value_at_path(output, matched.group("path"))


def wait_for_webhook_response(
    execution: WorkflowExecution,
    trigger: WorkflowTrigger,
    *,
    client: ConductorClient | None = None,
    timeout_seconds: float | None = None,
    poll_interval: float = 0.25,
) -> Any:
    if not execution.conductor_workflow_id:
        raise WebhookResponseError("流程执行尚未提交到执行引擎")
    version = WorkflowVersion.objects.get(workflow_id=trigger.workflow_id, version=execution.workflow_version)
    reference = _response_reference(trigger, version.canvas_metadata or {})
    configured_timeout = float(getattr(settings, "WORKFLOW_WEBHOOK_WAIT_TIMEOUT_SECONDS", 60) or 60)
    timeout = max(0.1, min(float(timeout_seconds if timeout_seconds is not None else configured_timeout), 60.0))
    deadline = time.monotonic() + timeout
    conductor = client or ConductorClient()

    while True:
        remote = conductor.get_execution(execution.conductor_workflow_id)
        apply_remote_execution(execution, remote)
        if execution.status in TERMINAL_STATUSES:
            if execution.status != WorkflowExecution.Status.SUCCEEDED:
                detail = execution.error_message or execution.get_status_display()
                raise WebhookResponseError(f"流程未成功完成：{detail}")
            return _resolve_response(reference, remote)
        if time.monotonic() >= deadline:
            raise WebhookResponseError(f"等待流程结果超时，流程仍在后台执行（execution_id={execution.id}）")
        time.sleep(max(0.01, min(poll_interval, deadline - time.monotonic())))
