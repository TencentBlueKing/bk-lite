"""运营分析搭盘工具。检索在工具内完成，只把候选摘要交回模型。"""

import json
import os

from langchain_core.callbacks import dispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.core.logger import opspilot_logger as logger
from apps.operation_analysis.services.dashboard_builder_pipeline import (
    draft_proposal_for_requirements,
    plan_dashboard_requirements,
    unmatched_requirement_texts,
)
from apps.operation_analysis.services.dashboard_proposal_service import (
    classify_dashboard_request,
    dashboard_confirmation_intent,
    dashboard_snapshot_from_message,
    search_briefs,
)
from apps.opspilot.metis.llm.tools.dashboard_proposal_memory import (  # noqa: F401
    NO_RELIABLE_MATCH_REPLY,
    _message_from_config,
    candidates_from_tool_content,
    confirmation_reply,
    format_search_step_result,
    load_ready_proposal,
    mark_proposal_applied,
    proposal_for_apply,
    proposal_for_prepare,
    proposal_from_tool_content,
    ready_proposal_awaits_apply,
    remember_ready_proposal,
    remember_search_candidates,
    reply_from_apply_content,
    reply_from_prepare_content,
    requirements_from_tool_content,
    saved_search_candidates,
    saved_search_requirements,
)
from apps.opspilot.metis.llm.tools.monitor.utils import wrap_error, wrap_success
from apps.opspilot.services.caller_identity import CALLER_IDENTITY_CONFIG_KEY
from apps.rpc.base import AppClient, RpcClient


def _caller_identity(config: RunnableConfig | None) -> dict:
    configurable = config.get("configurable") if isinstance(config, dict) else None
    identity = (configurable or {}).get(CALLER_IDENTITY_CONFIG_KEY) if isinstance(configurable, dict) else None
    return identity if isinstance(identity, dict) else {}


def _team_id(config: RunnableConfig | None) -> int | None:
    team_id = _caller_identity(config).get("team_id")
    return int(team_id) if team_id else None


def _session_id(config: RunnableConfig | None) -> str:
    configurable = config.get("configurable") if isinstance(config, dict) else None
    if not isinstance(configurable, dict):
        return "legacy"
    return str(configurable.get("dashboard_session_id") or configurable.get("execution_id") or "legacy")


def dashboard_scope(config: RunnableConfig | None, dashboard_id: str = "current") -> tuple[int | None, str, str]:
    """方案只在组织、会话和仪表盘三重边界内可见。"""
    resolved = str(dashboard_id or "current")
    if resolved == "current":
        snapshot = dashboard_snapshot_from_message(_message_from_config(config))
        if isinstance(snapshot, dict) and snapshot.get("dashboardId") not in (None, ""):
            resolved = str(snapshot["dashboardId"])
    return _team_id(config), _session_id(config), resolved


def dynamic_param_choices(declared: dict, identity: dict | None) -> list[dict]:
    """按参数自己的动态选项源取选项。源地址来自声明，不按数据源名字分支。"""
    config = declared.get("inputConfig") if isinstance(declared.get("inputConfig"), dict) else {}
    source = config.get("optionsSource") if isinstance(config.get("optionsSource"), dict) else {}
    if source.get("type") != "dynamic":
        return []
    ref = source.get("sourceRef") if isinstance(source.get("sourceRef"), dict) else {}
    rest_api = ref.get("value") if ref.get("type") == "rest_api" else ""
    if not isinstance(rest_api, str) or "/" not in rest_api:
        return []
    namespace, path = rest_api.split("/", 1)
    caller = identity or {}
    user_info = {
        "user": caller.get("username"),
        "domain": caller.get("domain"),
        "team": caller.get("team_id"),
        "include_children": bool(caller.get("include_children")),
    }
    try:
        result = AppClient(f"apps.{namespace}.nats.nats").run(path, user_info=user_info)
    except Exception as exc:
        logger.warning(
            "event=dashboard_param_choices_read_failed failed_stage=read_param_choices error_type=%s team_id=%s",
            type(exc).__name__,
            caller.get("team_id") or "",
        )
        return []
    items = result.get("items") if isinstance(result, dict) else None
    if not isinstance(items, list):
        data = result.get("data") if isinstance(result, dict) else None
        items = data if isinstance(data, list) else []
    label_field = source.get("labelField") or "label"
    value_field = source.get("valueField") or "value"
    choices = []
    for item in items:
        if not isinstance(item, dict) or item.get(value_field) in (None, ""):
            continue
        choices.append({"label": str(item.get(label_field) or item.get(value_field)), "value": item.get(value_field)})
        if len(choices) >= 50:
            break
    return choices


def _rpc():
    if os.getenv("IS_LOCAL_RPC", "0") == "1":
        return AppClient("apps.operation_analysis.nats.nats")
    return RpcClient()


def _run_dashboard_rpc(method: str, **kwargs):
    from apps.operation_analysis.nats.auth import sign_dashboard_request

    kwargs.pop("_internal_auth", None)
    kwargs["_internal_auth"] = sign_dashboard_request(kwargs.get("team_id"), method)
    return _rpc().run(method, **kwargs)


def _briefs(team_id: int) -> list[dict]:
    result = _run_dashboard_rpc("list_dashboard_datasource_briefs", team_id=team_id)
    if isinstance(result, dict) and isinstance(result.get("briefs"), list):
        return result["briefs"]
    if isinstance(result, dict) and isinstance((result.get("data") or {}).get("briefs"), list):
        return result["data"]["briefs"]
    return []


@tool
def search_data_sources(requirements: list[dict], config: RunnableConfig) -> dict:
    """按数据需求检索当前用户可见的运营分析数据源。

    requirements 每项包含 text 和 purpose（visualization 或 parameter_options）。请尽量提供可选的
    domain、metric、dimension、analysisType（overview/metric/trend/distribution/detail/ranking/relationship）
    和 chartType。这些是结构化语义意图，服务端会用数据源标签、字段和图表契约再校验。
    候选 fields 的 name 是写入组件的字段 key，desc 只是说明。只返回候选摘要，不返回连接配置。
    """
    team_id, session_id, dashboard_id = dashboard_scope(config)
    if not team_id:
        return wrap_error("缺少调用者组织，无法检索数据源")
    requirements = plan_dashboard_requirements(_message_from_config(config), requirements)
    if not requirements:
        return wrap_error("没有识别到可检索的仪表盘数据目标")
    try:
        briefs = search_briefs(requirements, _briefs(team_id))
    except Exception as exc:
        return wrap_error(str(exc))
    remember_search_candidates(
        briefs,
        requirements=requirements,
        team_id=team_id,
        session_id=session_id,
        dashboard_id=dashboard_id,
    )
    return wrap_success({"requirements": requirements, "candidates": briefs})


@tool
def prepare_dashboard_proposal(proposal: dict, config: RunnableConfig) -> dict:
    """校验并补全仪表盘方案。通过后保留 JSON，供后续工具直接应用。"""
    team_id, session_id, dashboard_id = dashboard_scope(config)
    if not team_id:
        return wrap_error("缺少调用者组织，无法校验方案")
    user_message = _message_from_config(config)
    candidates = saved_search_candidates(team_id=team_id, session_id=session_id, dashboard_id=dashboard_id)
    requirements = saved_search_requirements(team_id=team_id, session_id=session_id, dashboard_id=dashboard_id)
    kind = classify_dashboard_request(user_message)
    unmatched = unmatched_requirement_texts(requirements, candidates) if kind in {"build", "extend"} else []
    coverage_note = f"未加入（没有找到语义和图表契约都匹配的数据源）：{'\u3001'.join(unmatched)}" if unmatched else ""
    revising = kind == "revise"
    if revising:
        revised = proposal_for_prepare(
            team_id,
            user_message,
            session_id=session_id,
            dashboard_id=dashboard_id,
        )
        if isinstance(revised, dict) and revised.get("reply") and not revised.get("schemaVersion"):
            return wrap_success({"ok": False, "reply": revised["reply"]})
        if revised:
            proposal = revised
    elif kind in {"build", "extend"}:
        drafted = proposal_for_prepare(
            team_id,
            user_message,
            candidates,
            requirements=requirements,
            session_id=session_id,
            dashboard_id=dashboard_id,
        )
        if isinstance(drafted, dict) and drafted.get("reply") and not drafted.get("schemaVersion"):
            return wrap_success({"ok": False, "reason": "no_reliable_match", "reply": drafted["reply"]})
        if not drafted:
            return wrap_success(
                {
                    "ok": False,
                    "reason": "no_reliable_match",
                    "reply": NO_RELIABLE_MATCH_REPLY,
                }
            )
        proposal = drafted
    else:
        from apps.operation_analysis.services.dashboard_proposal_service import proposal_has_param_gaps

        stored = load_ready_proposal(team_id, dashboard_id, session_id=session_id)
        if stored and proposal_has_param_gaps(stored):
            proposal = stored
    try:
        result = _run_dashboard_rpc("prepare_dashboard_proposal", proposal=proposal, team_id=team_id)
    except Exception as exc:
        return wrap_error(str(exc))
    data = result if isinstance(result, dict) else {"ok": False, "reason": "invalid_response"}
    if data.get("ok") is not True and not revising:
        draft = (
            proposal
            if kind in {"build", "extend"}
            else draft_proposal_for_requirements(requirements or plan_dashboard_requirements(user_message), candidates)
        )
        if draft:
            try:
                retried = _run_dashboard_rpc("prepare_dashboard_proposal", proposal=draft, team_id=team_id)
            except Exception as exc:
                return wrap_error(str(exc))
            if isinstance(retried, dict) and retried.get("ok") is True:
                data = retried
    proposal_body = data.get("proposal") if isinstance(data, dict) else None
    if not isinstance(proposal_body, dict):
        proposal_body = proposal if isinstance(proposal, dict) else None
    if isinstance(proposal_body, dict) and (data.get("ok") is True or data.get("reason") == "pending"):
        from apps.operation_analysis.services.dashboard_proposal_service import fill_confirmed_param_values, param_filled_reply, param_gap_reply

        filled, gaps, notes = fill_confirmed_param_values(
            proposal_body,
            _briefs(team_id),
            user_message,
            choice_loader=lambda declared: dynamic_param_choices(declared, _caller_identity(config)),
        )
        if gaps:
            remember_ready_proposal(team_id, dashboard_id, filled, session_id=session_id)
            return wrap_success({"ok": False, "reason": "pending", "reply": param_gap_reply(gaps, notes), "proposal": filled})
        if notes:
            try:
                retried = _run_dashboard_rpc("prepare_dashboard_proposal", proposal=filled, team_id=team_id)
            except Exception as exc:
                return wrap_error(str(exc))
            if isinstance(retried, dict) and retried.get("ok") is True and isinstance(retried.get("proposal"), dict):
                filled = retried["proposal"]
                data = retried
            remember_ready_proposal(team_id, dashboard_id, filled, session_id=session_id)
            scheme = confirmation_reply(filled) if kind in {"build", "extend"} else ""
            data = {
                **data,
                "ok": True,
                "proposal": filled,
                "reply": "\n\n".join(part for part in (scheme, coverage_note, param_filled_reply(notes)) if part),
            }
            return wrap_success(data)
    if isinstance(data, dict) and data.get("ok") is True and isinstance(proposal_body, dict):
        remember_ready_proposal(team_id, dashboard_id, proposal_body, session_id=session_id)
        scheme = confirmation_reply(proposal_body) if kind in {"build", "extend"} else ""
        data = {**data, "reply": "\n\n".join(part for part in (scheme or confirmation_reply(proposal_body), coverage_note) if part)}
    return wrap_success(data)


def _proposal_payload(proposal, dashboard_id: str) -> dict:
    if isinstance(proposal, str):
        proposal = json.loads(proposal)
    if not isinstance(proposal, dict):
        raise ValueError("方案必须是 JSON 对象")
    inner = proposal.get("data") if isinstance(proposal.get("data"), dict) else proposal
    nested = inner.get("proposal") if isinstance(inner, dict) else None
    if isinstance(nested, dict) and "schemaVersion" not in inner:
        inner = nested
    if not isinstance(inner, dict) or "schemaVersion" not in inner:
        raise ValueError("方案缺少 schemaVersion")
    if not isinstance(inner.get("filters"), list):
        inner = {**inner, "filters": []}
    layout = []
    for item in inner.get("layout") or []:
        if not isinstance(item, dict):
            layout.append(item)
            continue
        widget_id = item.get("i") or item.get("id")
        layout.append({**item, "i": widget_id} if widget_id else item)
    return {"dashboardId": dashboard_id or "current", "proposal": {**inner, "layout": layout}}


@tool
def apply_dashboard_proposal(proposal: dict | str, dashboard_id: str = "current", config: RunnableConfig = None) -> dict:
    """把已经 prepare 校验通过的方案直接应用到当前仪表盘。"""
    team_id, session_id, dashboard_id = dashboard_scope(config, dashboard_id)
    if not team_id:
        return wrap_error("缺少调用者组织，无法应用方案")
    if dashboard_confirmation_intent(_message_from_config(config)) == "cancel":
        return wrap_error("用户已取消应用")
    proposal = proposal_for_apply(proposal, team_id, dashboard_id, session_id=session_id)
    if not isinstance(proposal, dict):
        return wrap_error("没有当前会话中已准备的仪表盘方案")
    try:
        payload = _proposal_payload(proposal, dashboard_id)
    except (TypeError, ValueError, json.JSONDecodeError):
        return wrap_error("已准备方案缺少 schemaVersion")
    try:
        prepared = _run_dashboard_rpc("prepare_dashboard_proposal", proposal=payload["proposal"], team_id=team_id)
    except Exception as exc:
        return wrap_error(str(exc))
    if not isinstance(prepared, dict) or not prepared.get("ok") or not isinstance(prepared.get("proposal"), dict):
        from apps.operation_analysis.services.dashboard_proposal_service import fill_confirmed_param_values, param_gap_reply

        pending = prepared.get("pending") if isinstance(prepared, dict) else None
        only_missing_params = (
            isinstance(pending, list) and pending and all(isinstance(item, dict) and item.get("reason") == "required_param" for item in pending)
        )
        if only_missing_params:
            filled, gaps, notes = fill_confirmed_param_values(
                payload["proposal"],
                _briefs(team_id),
                _message_from_config(config),
                choice_loader=lambda declared: dynamic_param_choices(declared, _caller_identity(config)),
            )
            if gaps:
                remember_ready_proposal(
                    team_id,
                    dashboard_id,
                    filled if isinstance(filled, dict) else payload["proposal"],
                    session_id=session_id,
                )
                return wrap_success({"ok": False, "applied": False, "reply": param_gap_reply(gaps, notes)})
            if not notes:
                return wrap_success(prepared)
            try:
                prepared = _run_dashboard_rpc("prepare_dashboard_proposal", proposal=filled, team_id=team_id)
            except Exception as exc:
                return wrap_error(str(exc))
            payload = {"dashboardId": dashboard_id or "current", "proposal": filled}
    if not isinstance(prepared, dict) or not prepared.get("ok") or not isinstance(prepared.get("proposal"), dict):
        return wrap_success(prepared if isinstance(prepared, dict) else {"ok": False, "reason": "invalid_response"})
    event = {"dashboardId": payload["dashboardId"], "proposal": prepared["proposal"]}
    _publish_apply_event(config, event)
    mark_proposal_applied(team_id, dashboard_id, session_id=session_id)
    return wrap_success({"applied": True, "dashboardId": event["dashboardId"], "reply": "已应用到当前编辑中的仪表盘。"})


def _publish_apply_event(config: RunnableConfig | None, event: dict) -> None:
    """DeepAgent 计划步骤会摘掉父级流回调，自定义事件要先写入本请求队列。"""
    from apps.opspilot.metis.llm.chain.nested_stream import publish_owned_custom_event

    if publish_owned_custom_event(config, "dashboard_config_apply", event):
        return
    dispatch_custom_event("dashboard_config_apply", event, config=config)


__all__ = ["search_data_sources", "prepare_dashboard_proposal", "apply_dashboard_proposal"]
