from __future__ import annotations

import json
import uuid
from typing import Any

from apps.core.utils.internal_event_auth import verify_internal_event
from apps.rpc.workflow import MANAGED_NATS_ACTOR, MANAGED_NATS_TRIGGER_SCOPE, NATS_TRIGGER_SCOPE
from apps.workflow.models import WorkflowTrigger
from apps.workflow.permissions import actor_can_access_workflow
from apps.workflow.services.definitions import DefinitionValidationError
from apps.workflow.services.triggers import TriggerConflict, invoke_trigger

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
        if type(item) is not int and not (isinstance(item, str) and item.isdecimal()):
            return set()
        try:
            normalized = int(item)
        except (TypeError, ValueError):
            return set()
        if normalized <= 0:
            return set()
        result.add(normalized)
    return result


def invoke_nats_trigger(data: dict[str, Any], actor_context: dict[str, Any], *, message_subject: str, internal_auth=None):
    """Validate the internal caller and adapt a NATS event to a workflow trigger."""
    if not isinstance(data, dict) or not isinstance(actor_context, dict):
        raise DefinitionValidationError("NATS 触发请求非法")
    authorized_team_ids = _team_ids(actor_context.get("authorized_team_ids"))
    username = actor_context.get("username")
    domain = actor_context.get("domain")
    if (
        not authorized_team_ids
        or not isinstance(username, str)
        or not username.strip()
        or len(username) > 32
        or not isinstance(domain, str)
        or not domain.strip()
        or len(domain) > 100
    ):
        raise TriggerConflict("NATS 调用方身份非法")
    try:
        (requested_team,) = _team_ids([data.get("team")])
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
    if trigger is None or requested_team not in trigger.team or requested_team not in trigger.workflow.team:
        raise TriggerConflict("NATS 触发器不存在或不可用")
    if message_subject != str(trigger.config.get("subject") or ""):
        raise TriggerConflict("NATS 消息主题与触发器不匹配")
    managed_channel = "managed_channel_id" in actor_context
    if managed_channel and (username, domain) != (MANAGED_NATS_ACTOR, "domain.com"):
        raise TriggerConflict("NATS 调用方身份非法")
    scope = MANAGED_NATS_TRIGGER_SCOPE if managed_channel else NATS_TRIGGER_SCOPE
    if not verify_internal_event(scope, {"data": data, "actor_context": actor_context}, internal_auth, caller="workflow"):
        raise TriggerConflict("NATS 调用方身份非法")
    identity = None
    if not managed_channel:
        if not actor_can_access_workflow(
            username=username, domain=domain, current_team=requested_team, workflow=trigger.workflow, require_operate=True
        ):
            raise TriggerConflict("缺少流程实例操作权限")
        identity = {"username": username, "domain": domain, "team_id": requested_team, "include_children": False}
    return invoke_trigger(
        trigger,
        inputs=inputs,
        idempotency_key=event_id,
        started_by=username,
        domain=domain,
        caller_identity=identity,
    )
