"""仪表盘方案在一次会话里的缓存，以及工具结果里的短回复。"""

from __future__ import annotations

import json
import os
from hashlib import sha256

from django.core.cache import cache
from langchain_core.runnables import RunnableConfig

from apps.operation_analysis.services.dashboard_builder_pipeline import draft_proposal_for_requirements, plan_dashboard_requirements
from apps.operation_analysis.services.dashboard_proposal_service import (
    append_dashboard_widgets,
    classify_dashboard_request,
    current_dashboard_proposal,
    format_proposal_inventory,
    revise_dashboard_proposal,
    should_keep_existing_widgets,
)

DASHBOARD_PROPOSAL_TTL = int(os.getenv("DASHBOARD_PROPOSAL_TTL", "900"))
NO_RELIABLE_MATCH_REPLY = "没有找到能够可靠回答这个需求的数据源，所以这次没有生成仪表盘方案。请补充想看的业务对象或指标。"


def _state_key(kind: str, team_id: int | None, session_id: str, dashboard_id: str = "") -> str:
    scope = json.dumps([team_id or 0, session_id or "legacy", dashboard_id or "current"], ensure_ascii=False)
    return f"ops-analysis-dashboard:{kind}:{sha256(scope.encode('utf-8')).hexdigest()}"


def dashboard_ready_key(team_id: int | None, dashboard_id: str, session_id: str = "legacy") -> str:
    return _state_key("proposal", team_id, session_id, dashboard_id)


def remember_ready_proposal(
    team_id: int | None,
    dashboard_id: str,
    proposal: dict,
    *,
    session_id: str = "legacy",
) -> None:
    if isinstance(proposal, dict) and proposal.get("schemaVersion"):
        cache.set(
            dashboard_ready_key(team_id, dashboard_id, session_id),
            {"proposal": proposal, "applied": False},
            timeout=DASHBOARD_PROPOSAL_TTL,
        )


def remember_search_candidates(
    candidates: list,
    *,
    requirements: list[dict] | None = None,
    team_id: int | None = None,
    session_id: str = "legacy",
    dashboard_id: str = "current",
) -> None:
    # 新检索表示用户已开始另一个方案；旧方案不能再被后续步骤误应用。
    cache.delete(dashboard_ready_key(team_id, dashboard_id, session_id))
    kept = [item for item in candidates or [] if isinstance(item, dict)]
    planned = [item for item in requirements or [] if isinstance(item, dict)]
    cache.set(
        _state_key("candidates", team_id, session_id, dashboard_id),
        {"candidates": kept, "requirements": planned},
        timeout=DASHBOARD_PROPOSAL_TTL,
    )


def saved_search_candidates(
    *,
    team_id: int | None = None,
    session_id: str = "legacy",
    dashboard_id: str = "current",
) -> list[dict]:
    context = cache.get(_state_key("candidates", team_id, session_id, dashboard_id))
    candidates = context.get("candidates") if isinstance(context, dict) else context
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def saved_search_requirements(
    *,
    team_id: int | None = None,
    session_id: str = "legacy",
    dashboard_id: str = "current",
) -> list[dict]:
    context = cache.get(_state_key("candidates", team_id, session_id, dashboard_id))
    requirements = context.get("requirements") if isinstance(context, dict) else None
    return [item for item in requirements if isinstance(item, dict)] if isinstance(requirements, list) else []


def load_ready_proposal(
    team_id: int | None,
    dashboard_id: str,
    *,
    session_id: str = "legacy",
    pending_only: bool = False,
) -> dict | None:
    state = cache.get(dashboard_ready_key(team_id, dashboard_id, session_id))
    if not isinstance(state, dict) or (pending_only and state.get("applied") is True):
        return None
    proposal = state.get("proposal")
    return proposal if isinstance(proposal, dict) else None


def has_ready_proposal(
    dashboard_id: str,
    *,
    team_id: int | None = None,
    session_id: str = "legacy",
) -> bool:
    return load_ready_proposal(team_id, dashboard_id, session_id=session_id) is not None


def mark_proposal_applied(
    team_id: int | None,
    dashboard_id: str,
    *,
    session_id: str = "legacy",
) -> None:
    key = dashboard_ready_key(team_id, dashboard_id, session_id)
    state = cache.get(key)
    if isinstance(state, dict) and isinstance(state.get("proposal"), dict):
        cache.set(key, {**state, "applied": True}, timeout=DASHBOARD_PROPOSAL_TTL)


def ready_proposal_awaits_apply(
    dashboard_id: str,
    *,
    team_id: int | None = None,
    session_id: str = "legacy",
) -> bool:
    return load_ready_proposal(team_id, dashboard_id, session_id=session_id, pending_only=True) is not None


def _message_from_config(config: RunnableConfig | None) -> str:
    configurable = config.get("configurable") if isinstance(config, dict) else None
    if not isinstance(configurable, dict):
        return ""
    if configurable.get("dashboard_user_message"):
        return str(configurable["dashboard_user_message"])
    request = configurable.get("graph_request")
    return str(getattr(request, "user_message", "") or getattr(request, "graph_user_message", "") or "")


def proposal_for_prepare(
    team_id: int | None,
    user_message: str,
    candidates: list[dict] | None = None,
    *,
    requirements: list[dict] | None = None,
    session_id: str = "legacy",
    dashboard_id: str = "current",
) -> dict | None:
    """修订当前画布；新搭才用检索候选起草。认不出目标时返回 reply。"""
    kind = classify_dashboard_request(user_message)
    if kind == "revise":
        current = current_dashboard_proposal(
            user_message,
            load_ready_proposal(team_id, dashboard_id, session_id=session_id),
        )
        revised = revise_dashboard_proposal(current, user_message)
        if revised.get("reply"):
            return revised
        return revised
    chosen_candidates = (
        candidates if candidates is not None else saved_search_candidates(team_id=team_id, session_id=session_id, dashboard_id=dashboard_id)
    )
    planned = requirements or saved_search_requirements(team_id=team_id, session_id=session_id, dashboard_id=dashboard_id)
    draft = draft_proposal_for_requirements(
        planned or plan_dashboard_requirements(user_message),
        chosen_candidates,
    )
    current = current_dashboard_proposal(
        user_message,
        load_ready_proposal(team_id, dashboard_id, session_id=session_id),
    )
    if draft and (kind == "extend" or should_keep_existing_widgets(user_message, current)):
        combined = append_dashboard_widgets(current, draft)
        if kind == "extend":
            return combined or {"reply": "还看不到当前画布，不能安全追加图表。"}
        if combined:
            return combined
    return draft or {"reply": NO_RELIABLE_MATCH_REPLY}


def confirmation_reply(proposal: dict) -> str:
    return format_proposal_inventory(proposal)


def proposal_for_apply(
    proposal,
    team_id: int | None,
    dashboard_id: str,
    *,
    session_id: str = "legacy",
):
    """只返回当前会话、当前仪表盘上已准备且未应用的方案。"""
    del proposal  # 模型入参不能绕过 prepare 阶段成为可执行方案。
    return load_ready_proposal(team_id, dashboard_id, session_id=session_id, pending_only=True)


def proposal_from_tool_content(content) -> dict | None:
    """从上一轮 prepare 的工具结果里取出方案。进程内记忆丢失时仍能直接套上画布。"""
    payload = content
    if isinstance(content, str):
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    proposal = data.get("proposal") if isinstance(data, dict) else None
    if isinstance(proposal, dict) and proposal.get("schemaVersion") and isinstance(proposal.get("layout"), list) and proposal.get("layout"):
        return proposal
    return None


def _load_mapping(content):
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        content = "".join(str(item.get("text") or "") if isinstance(item, dict) else str(item) for item in content)
    if not isinstance(content, str) or not content.strip():
        return None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        return payload
    if content[:1] in "{[":
        import ast

        try:
            payload = ast.literal_eval(content)
        except (SyntaxError, ValueError):
            return None
    return payload if isinstance(payload, dict) else None


def reply_from_apply_content(content) -> str:
    payload = _load_mapping(content)
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if not isinstance(data, dict):
        return ""
    reply = data.get("reply")
    if isinstance(reply, str) and reply.startswith(("已应用到当前编辑中的仪表盘", "还要先定这些参数", "已把参数写进方案")):
        return reply
    if data.get("applied") is True:
        return "已应用到当前编辑中的仪表盘。"
    return ""


def reply_from_prepare_content(content) -> str:
    payload = _load_mapping(content)
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else None
    reply = data.get("reply") if isinstance(data, dict) else None
    if isinstance(reply, str) and (reply.startswith(("还要先定这些参数", "已把参数写进方案")) or data.get("reason") == "no_reliable_match"):
        return reply.strip()
    if not isinstance(data, dict) or data.get("ok") is not True:
        return ""
    reply = data.get("reply")
    if isinstance(reply, str) and reply.strip():
        return reply.strip()
    proposal = data.get("proposal")
    return confirmation_reply(proposal) if isinstance(proposal, dict) else ""


def candidates_from_tool_content(content) -> list[dict]:
    payload = content
    if isinstance(content, str):
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return []
    data = payload.get("data") if isinstance(payload, dict) else None
    candidates = data.get("candidates") if isinstance(data, dict) else None
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def requirements_from_tool_content(content) -> list[dict]:
    payload = _load_mapping(content)
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    requirements = data.get("requirements") if isinstance(data, dict) else None
    return [item for item in requirements if isinstance(item, dict)] if isinstance(requirements, list) else []


def format_search_step_result(result: dict) -> str:
    """把检索结果压成后续步骤能读完的短摘要。"""
    if not isinstance(result, dict) or result.get("success") is False:
        return "search_data_sources: 检索失败"
    data = result.get("data") if isinstance(result, dict) else None
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(candidates, list) or not candidates:
        return "search_data_sources: 没有匹配的数据源"
    lines = []
    for item in candidates[:5]:
        fields = ",".join(str(field.get("name") or "") for field in (item.get("fields") or [])[:6] if isinstance(field, dict) and field.get("name"))
        charts = ",".join(str(chart) for chart in (item.get("chart_type") or [])[:4])
        lines.append(f"id={item.get('id')} name={item.get('name')} charts={charts} fields={fields}")
    return ("search_data_sources:\n" + "\n".join(lines))[:400]
