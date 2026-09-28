from __future__ import annotations

import json
import uuid
from typing import Any

from apps.workflow_orchestration.models import WorkflowTrigger
from apps.workflow_orchestration.services.definitions import DefinitionValidationError
from apps.workflow_orchestration.services.triggers import TriggerConflict, invoke_trigger

MAX_NATS_INPUT_BYTES = 1024 * 1024


def validate_nats_event(event: Any) -> tuple[dict[str, Any], str, dict[str, Any]]:
    if not isinstance(event, dict):
        raise DefinitionValidationError("NATS 标准事件信封必须是 JSON 对象")
    if set(event) != {"event_id", "occurred_at", "producer", "payload"}:
        raise DefinitionValidationError("NATS 事件必须包含 event_id、occurred_at、producer 和 payload")
    event_id = event.get("event_id")
    occurred_at = event.get("occurred_at")
    producer = event.get("producer")
    inputs = event.get("payload")
    if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 128:
        raise DefinitionValidationError("NATS event_id 必须是非空字符串")
    if not isinstance(occurred_at, str) or not occurred_at.strip() or len(occurred_at) > 64:
        raise DefinitionValidationError("NATS occurred_at 必须是非空时间字符串")
    if not isinstance(producer, str) or not producer.strip() or len(producer) > 100:
        raise DefinitionValidationError("NATS producer 必须是非空字符串")
    if not isinstance(inputs, dict):
        raise DefinitionValidationError("NATS payload 必须是 JSON 对象")
    try:
        payload_size = len(json.dumps(inputs, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError) as error:
        raise DefinitionValidationError("NATS inputs 不是合法 JSON") from error
    if payload_size > MAX_NATS_INPUT_BYTES:
        raise DefinitionValidationError("NATS inputs 最大 1 MiB")
    return event, event_id, inputs


def _team_ids(value: Any) -> set[int]:
    if not isinstance(value, (list, tuple, set)) or len(value) > 100:
        return set()
    result: set[int] = set()
    for item in value:
        if isinstance(item, bool):
            return set()
        try:
            normalized = int(item)
        except (TypeError, ValueError):
            return set()
        if normalized <= 0:
            return set()
        result.add(normalized)
    return result


def invoke_nats_trigger(data: dict[str, Any], actor_context: dict[str, Any], *, message_subject: str):
    """Validate the internal caller and adapt a NATS event to a workflow trigger."""
    if not isinstance(data, dict) or not isinstance(actor_context, dict):
        raise DefinitionValidationError("NATS 触发请求非法")
    authorized_team_ids = _team_ids(actor_context.get("authorized_team_ids"))
    username = str(actor_context.get("username") or "").strip()
    domain = str(actor_context.get("domain") or "").strip()
    if not authorized_team_ids or not username or len(username) > 32 or not domain or len(domain) > 100:
        raise TriggerConflict("NATS 调用方身份非法")
    try:
        requested_team = int(data.get("team"))
        trigger_id = uuid.UUID(str(data.get("trigger_id") or ""))
    except (TypeError, ValueError, AttributeError) as error:
        raise DefinitionValidationError("NATS 触发参数非法") from error
    if requested_team not in authorized_team_ids:
        raise TriggerConflict("NATS 触发超出授权组织范围")
    _, event_id, inputs = validate_nats_event(data.get("event", data.get("inputs", {})))
    trigger = (
        WorkflowTrigger.objects.select_related("workflow")
        .filter(
            pk=trigger_id,
            trigger_type=WorkflowTrigger.Type.NATS,
        )
        .first()
    )
    if trigger is None or requested_team not in {int(item) for item in trigger.team}:
        raise TriggerConflict("NATS 触发器不存在或不可用")
    if message_subject != str(trigger.config.get("subject") or ""):
        raise TriggerConflict("NATS 消息主题与触发器不匹配")
    return invoke_trigger(
        trigger,
        inputs=inputs,
        idempotency_key=event_id,
        started_by=username,
        domain=domain,
    )
