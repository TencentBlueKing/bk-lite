from __future__ import annotations

from typing import Any


def team_id(value: Any) -> int:
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("team 必须是单一组织 ID")
    return value


def actor_snapshot(inputs: dict[str, Any]) -> dict[str, str]:
    actor = inputs.get("actor") or {}
    if not isinstance(actor, dict) or not isinstance(actor.get("username"), str) or not actor["username"].strip():
        raise ValueError("原子缺少执行人快照")
    return {
        "username": actor["username"].strip()[:150],
        "domain": str(actor.get("domain") or "domain.com")[:255],
    }


def trusted_organization_id(inputs: dict[str, Any]) -> int:
    """Prefer Worker-injected organization, fall back to legacy input bindings."""
    context = inputs.get("__bklite_context")
    if isinstance(context, dict):
        organization_id = context.get("organization_id")
        if not isinstance(organization_id, bool) and isinstance(organization_id, int) and organization_id > 0:
            return organization_id
    return team_id(inputs.get("team"))


def trusted_execution_id(inputs: dict[str, Any], *, required: bool = True) -> str:
    """Prefer Worker-injected execution id, fall back to legacy input bindings."""
    context = inputs.get("__bklite_context")
    if isinstance(context, dict):
        execution_id = context.get("execution_id")
        if execution_id not in (None, ""):
            return str(execution_id)
    execution_id = inputs.get("execution_id")
    if execution_id not in (None, ""):
        return str(execution_id)
    if required:
        raise ValueError("原子缺少可信执行上下文")
    return ""


def trusted_execution_scope(inputs: dict[str, Any]) -> tuple[str, int]:
    return trusted_execution_id(inputs, required=True), trusted_organization_id(inputs)
