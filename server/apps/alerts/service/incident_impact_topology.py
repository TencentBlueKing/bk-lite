"""事故影响拓扑的告警侧入口。只通过 CMDB RPC 取关系，不触碰 CMDB 服务。"""

from nats.errors import NoRespondersError

from apps.alerts.utils.i18n import alerts_message
from apps.core.logger import alert_logger as logger
from apps.core.logger import safe_exception_info
from apps.core.utils.team_utils import get_current_team
from apps.rpc.cmdb import CMDB


def collect_incident_seed_uuids(alerts, requested):
    """按告警顺序收集 cmdb_id。传入子集时只保留这起事故里有的 UUID。"""
    ordered = []
    seen = set()
    for alert in alerts:
        objects = getattr(alert, "monitor_objects", None)
        if not isinstance(objects, list):
            continue
        for item in objects:
            if not isinstance(item, dict):
                continue
            text = _text(item.get("cmdb_id"))
            if not text or text.lower() in seen:
                continue
            seen.add(text.lower())
            ordered.append(text)
    if requested is None:
        return ordered
    by_key = {item.lower(): item for item in ordered}
    picked = []
    picked_seen = set()
    for raw in requested:
        text = _text(raw)
        match = by_key.get(text.lower()) if text else None
        if match is None or match.lower() in picked_seen:
            continue
        picked_seen.add(match.lower())
        picked.append(match)
    return picked


def build_incident_impact_topology(request, incident_id, alerts, requested):
    """无论种子是否为空都调用 NATS。没有订阅者表示这套部署没有 CMDB。"""
    seeds = collect_incident_seed_uuids(alerts, requested)
    user_info = _user_info(request)
    try:
        response = CMDB().incident_impact_topology(inst_uuids=seeds, user_info=user_info)
    except NoRespondersError:
        logger.info(
            "event=incident_impact_topology_not_purchased incident_id=%s",
            incident_id,
        )
        return _status(request, "not_purchased", "error.impact_topology_not_purchased")
    except Exception as exc:
        _warn_unavailable(incident_id, type(exc).__name__, exc)
        return _status(request, "unavailable", "error.impact_topology_unavailable")

    if not isinstance(response, dict) or response.get("result") is not True:
        _warn_unavailable(incident_id, "ResultFalse")
        return _status(request, "unavailable", "error.impact_topology_unavailable")

    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    nodes = data.get("nodes")
    links = data.get("links")
    if not isinstance(nodes, list) or not isinstance(links, list):
        _warn_unavailable(incident_id, "InvalidPayload")
        return _status(request, "unavailable", "error.impact_topology_unavailable")
    return {
        "relation_status": "ok",
        "message": "",
        "truncated": bool(data.get("truncated")),
        "nodes": nodes,
        "links": links,
    }


def _warn_unavailable(incident_id, error_type, exc=None):
    logger.warning(
        "event=incident_impact_topology_unavailable incident_id=%s failed_stage=rpc error_type=%s",
        incident_id,
        error_type,
        exc_info=safe_exception_info(exc) if exc is not None else None,
    )


def _status(request, relation_status, message_key):
    return {
        "relation_status": relation_status,
        "message": alerts_message(request, message_key),
        "truncated": False,
        "nodes": [],
        "links": [],
    }


def _user_info(request):
    user = getattr(request, "user", None)
    return {
        "team": _team(get_current_team(request)),
        "user": getattr(user, "username", "") or "",
        "domain": getattr(user, "domain", "") or "",
        "locale": getattr(user, "locale", "") or "",
        "include_children": request.COOKIES.get("include_children", "0") == "1",
    }


def _team(value):
    text = _text(value)
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _text(value):
    if value is None:
        return ""
    return str(value).strip()
