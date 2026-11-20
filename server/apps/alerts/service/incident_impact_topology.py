"""事故影响拓扑的告警侧入口。只通过 CMDB RPC 取关系，不触碰 CMDB 服务。"""

from nats.errors import NoRespondersError

from apps.alerts.constants.constants import AlertStatus, SessionStatus
from apps.alerts.models.models import Alert
from apps.alerts.utils.i18n import alerts_message
from apps.core.logger import alert_logger as logger
from apps.core.logger import safe_exception_info
from apps.core.utils.team_utils import get_current_team
from apps.rpc.cmdb import CMDB

ALERTING_RELATED_LIMIT = 40
QUIET_RELATED_LIMIT = 20
ALERT_PAGE_SIZE = 20
_ACTIVE_STATUSES = set(AlertStatus.ACTIVATE_STATUS)


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


def build_incident_impact_topology(request, incident_id, alerts, requested, visible_alerts=None):
    """无论种子是否为空都调用 NATS。没有订阅者表示这套部署没有 CMDB。"""
    prepared = _prepare_impact(request, incident_id, alerts, requested, visible_alerts)
    if prepared[0] is None:
        return prepared[1]
    return prepared[1]


def list_incident_impact_alerts(request, incident_id, alerts, requested, inst_uuid, page, visible_alerts=None):
    """侧栏分页。节点必须是这一次拓扑会画出来的对象。"""
    prepared = _prepare_impact(request, incident_id, alerts, requested, visible_alerts)
    if prepared[0] is None:
        return None, prepared[1]
    catalog = prepared[0]
    payload = prepared[1]
    if payload.get("relation_status") != "ok":
        return None, payload
    key = _canonical(inst_uuid)
    entry = catalog.get(key)
    if entry is None:
        return None, None
    ordered = _ordered_alerts(entry, catalog["incident_index"], catalog["active_index"])
    start = (page - 1) * ALERT_PAGE_SIZE
    return {
        "count": len(ordered),
        "page": page,
        "page_size": ALERT_PAGE_SIZE,
        "items": ordered[start : start + ALERT_PAGE_SIZE],
    }, payload


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
        "context_status": "unavailable",
        "alert_status": "unavailable",
        "message": alerts_message(request, message_key),
        "truncated": False,
        "related_truncated": False,
        "quiet_omitted": 0,
        "nodes": [],
        "links": [],
    }


def _prepare_impact(request, incident_id, alerts, requested, visible_alerts):
    seeds = collect_incident_seed_uuids(alerts, requested)
    user_info = _user_info(request)
    try:
        response = CMDB().incident_impact_topology(inst_uuids=seeds, user_info=user_info)
    except NoRespondersError:
        logger.info(
            "event=incident_impact_topology_not_purchased incident_id=%s",
            incident_id,
        )
        return None, _status(request, "not_purchased", "error.impact_topology_not_purchased")
    except Exception as exc:
        _warn_unavailable(incident_id, type(exc).__name__, exc)
        return None, _status(request, "unavailable", "error.impact_topology_unavailable")

    if not isinstance(response, dict) or response.get("result") is not True:
        _warn_unavailable(incident_id, "ResultFalse")
        return None, _status(request, "unavailable", "error.impact_topology_unavailable")

    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    nodes = data.get("nodes")
    links = data.get("links")
    if not isinstance(nodes, list) or not isinstance(links, list):
        _warn_unavailable(incident_id, "InvalidPayload")
        return None, _status(request, "unavailable", "error.impact_topology_unavailable")
    return _overlay_impact(request, incident_id, alerts, data, visible_alerts)


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


def _canonical(value):
    return _text(value).lower()


def _overlay_impact(request, incident_id, incident_alerts, data, visible_alerts):
    incident_ids = {alert.id for alert in incident_alerts}
    incident_index = _index_alerts(incident_alerts, incident_ids)
    keys = _subject_keys(data)
    alert_failed = False
    active_alerts = []
    queryset = visible_alerts if visible_alerts is not None else Alert.objects.none()
    try:
        active_alerts = _load_active_alerts(queryset, keys)
    except Exception as exc:
        alert_failed = True
        logger.warning(
            "event=incident_impact_alerts_unavailable incident_id=%s failed_stage=query error_type=%s",
            incident_id,
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
    active_index = _index_alerts(active_alerts, incident_ids)
    return _compose_impact(request, data, incident_index, active_index, alert_failed)


def _compose_impact(request, data, incident_index, active_index, alert_failed):
    base_nodes = [dict(node) for node in data.get("nodes") or [] if isinstance(node, dict)]
    candidates = [dict(node) for node in data.get("related_candidates") or [] if isinstance(node, dict)]
    chosen, omitted = _choose_related(candidates, active_index, alert_failed)
    nodes = []
    catalog = {}
    for node in base_nodes + chosen:
        key = _canonical(node.get("inst_uuid"))
        if not key or key in catalog:
            continue
        decorated = _decorate_object(node, incident_index, active_index, alert_failed)
        nodes.append(decorated)
        catalog[key] = {
            "kind": "seed" if decorated.get("role") == "seed" else "object",
            "self_keys": [key],
            "member_keys": [],
        }
    context_status = str(data.get("context_status") or "ok")
    if context_status == "ok" and not data.get("truncated"):
        _attach_context_nodes(nodes, catalog, data, incident_index, active_index, alert_failed)
    omitted_nodes = _decorate_omitted(omitted, catalog, incident_index, active_index, alert_failed)
    links = _compose_links(data, nodes, context_status)
    omitted_links = _links_beyond(data, nodes, omitted_nodes, links, context_status)
    messages = []
    if context_status == "unavailable":
        messages.append(alerts_message(request, "error.impact_topology_context_unavailable"))
    if alert_failed:
        messages.append(alerts_message(request, "error.impact_topology_alerts_unavailable"))
    payload = {
        "relation_status": "ok",
        "context_status": context_status,
        "alert_status": "unavailable" if alert_failed else "ok",
        "message": " ".join(messages),
        "truncated": bool(data.get("truncated")),
        "related_truncated": bool(data.get("related_truncated")),
        "quiet_omitted": len(omitted_nodes),
        "omitted_quiet_nodes": omitted_nodes,
        "omitted_quiet_links": omitted_links,
        "nodes": nodes,
        "links": links,
    }
    return {"incident_index": incident_index, "active_index": active_index, **catalog}, payload


def _choose_related(candidates, active_index, alert_failed):
    alerting = []
    quiet = []
    for node in candidates:
        key = _canonical(node.get("inst_uuid"))
        if not key:
            continue
        items = active_index.get(key) or []
        if items and not alert_failed:
            alerting.append((_severity(min(items, key=_severity_item)["level"]), key, node))
        else:
            quiet.append((key, node))
    alerting.sort(key=lambda item: (item[0], item[1]))
    quiet.sort(key=lambda item: item[0])
    if alert_failed:
        ordered = sorted(quiet, key=lambda item: item[0])
        kept = ordered[: ALERTING_RELATED_LIMIT + QUIET_RELATED_LIMIT]
        return [item[1] for item in kept], [item[1] for item in ordered[len(kept) :]]
    chosen = [item[2] for item in alerting[:ALERTING_RELATED_LIMIT]]
    chosen.extend(item[1] for item in quiet[:QUIET_RELATED_LIMIT])
    return chosen, [item[1] for item in quiet[QUIET_RELATED_LIMIT:]]


def _decorate_omitted(omitted, catalog, incident_index, active_index, alert_failed):
    nodes = []
    for node in omitted:
        key = _canonical(node.get("inst_uuid"))
        if not key or key in catalog:
            continue
        decorated = _decorate_object(dict(node), incident_index, active_index, alert_failed)
        nodes.append(decorated)
        catalog[key] = {"kind": "object", "self_keys": [key], "member_keys": []}
    return nodes


def _link_key(link):
    return (
        _canonical(link.get("src_inst_uuid")),
        _canonical(link.get("dst_inst_uuid")),
        str(link.get("model_asst_id") or link.get("asst_id") or ""),
    )


def _links_beyond(data, nodes, omitted_nodes, links, context_status):
    if not omitted_nodes:
        return []
    present = {_link_key(link) for link in links}
    extra = []
    for link in _compose_links(data, nodes + omitted_nodes, context_status):
        key = _link_key(link)
        if key in present:
            continue
        present.add(key)
        extra.append(link)
    return extra


def _decorate_object(node, incident_index, active_index, alert_failed):
    key = _canonical(node.get("inst_uuid"))
    role = str(node.get("role") or "")
    if role == "seed":
        items = incident_index.get(key) or []
        outside = [item for item in active_index.get(key) or [] if not item["in_incident"]]
        return _with_alert_fields(node, "incident", items, len(outside), False)
    if alert_failed:
        return _with_alert_fields(node, "unknown", [], 0, False)
    items = active_index.get(key) or []
    state = "active" if items else "clear"
    return _with_alert_fields(node, state, items, 0, False)


def _attach_context_nodes(nodes, catalog, data, incident_index, active_index, alert_failed):
    members = {}
    for item in data.get("application_members") or []:
        if isinstance(item, dict):
            members[_canonical(item.get("inst_uuid"))] = item
    present = {_canonical(node.get("inst_uuid")) for node in nodes}
    displayed = [node for node in nodes]
    for node in displayed:
        context = _context_for(data, node.get("inst_uuid"))
        if context is None:
            continue
        for app in context.get("applications") or []:
            if not isinstance(app, dict):
                continue
            app_key = _canonical(app.get("inst_uuid"))
            if not app_key:
                continue
            if app_key not in present:
                created = _context_graph_node(app, "application", "service")
                nodes.append(_decorate_rollup(created, [app_key], members, active_index, alert_failed))
                present.add(app_key)
                catalog[app_key] = _rollup_entry("application", app_key, members)
            system = app.get("system") if isinstance(app.get("system"), dict) else None
            if not system:
                continue
            system_key = _canonical(system.get("inst_uuid"))
            if not system_key or system_key in present:
                if system_key and system_key not in catalog:
                    catalog[system_key] = _system_entry(system_key, data, members)
                continue
            created = _context_graph_node(system, "system", "system")
            entry = _system_entry(system_key, data, members)
            nodes.append(_decorate_rollup(created, [system_key, *entry["member_keys"]], members, active_index, alert_failed, system=True))
            present.add(system_key)
            catalog[system_key] = entry


def _decorate_rollup(node, keys, members, active_index, alert_failed, system=False):
    if alert_failed:
        return _with_alert_fields(node, "unknown", [], 0, False)
    items = {}
    truncated = False
    for key in keys:
        for item in active_index.get(key) or []:
            items[item["id"]] = item
        record = members.get(key) or {}
        if record.get("member_truncated"):
            truncated = True
        if not system:
            for member in record.get("member_uuids") or []:
                for item in active_index.get(_canonical(member)) or []:
                    items[item["id"]] = item
    state = "active" if items else "clear"
    return _with_alert_fields(node, state, list(items.values()), 0, truncated)


def _context_graph_node(source, role, default_layer):
    return {
        "inst_uuid": source.get("inst_uuid") or "",
        "inst_name": source.get("inst_name") or "",
        "model_id": source.get("model_id") or "",
        "model_name": source.get("model_name") or "",
        "layer": source.get("layer") or default_layer,
        "role": role,
        "found": True,
    }


def _rollup_entry(kind, self_key, members):
    record = members.get(self_key) or {}
    return {
        "kind": kind,
        "self_keys": [self_key],
        "member_keys": [_canonical(item) for item in record.get("member_uuids") or [] if _canonical(item)],
    }


def _system_entry(system_key, data, members):
    member_keys = []
    seen = {system_key}
    truncated = False
    for context in data.get("contexts") or []:
        for app in (context or {}).get("applications") or []:
            system = app.get("system") if isinstance(app, dict) else None
            if not isinstance(system, dict) or _canonical(system.get("inst_uuid")) != system_key:
                continue
            app_key = _canonical(app.get("inst_uuid"))
            record = members.get(app_key) or {}
            if record.get("member_truncated"):
                truncated = True
            for key in [app_key, *[_canonical(item) for item in record.get("member_uuids") or []]]:
                if key and key not in seen:
                    seen.add(key)
                    member_keys.append(key)
    return {"kind": "system", "self_keys": [system_key], "member_keys": member_keys, "truncated": truncated}


def _context_for(data, inst_uuid):
    key = _canonical(inst_uuid)
    for item in data.get("contexts") or []:
        if isinstance(item, dict) and _canonical(item.get("ci_uuid")) == key:
            return item
    return None


def _compose_links(data, nodes, context_status):
    present = {_canonical(node.get("inst_uuid")) for node in nodes}
    links = []
    seen = set()
    for source in list(data.get("links") or []) + list(data.get("related_links") or []):
        if not isinstance(source, dict):
            continue
        src = _canonical(source.get("src_inst_uuid"))
        dst = _canonical(source.get("dst_inst_uuid"))
        if src not in present or dst not in present:
            continue
        key = (src, dst, str(source.get("model_asst_id") or source.get("asst_id") or ""))
        if key in seen:
            continue
        seen.add(key)
        link = dict(source)
        link["origin"] = link.get("origin") or "relation"
        links.append(link)
    if context_status != "ok":
        return links
    for node in list(nodes):
        context = _context_for(data, node.get("inst_uuid"))
        if context is None:
            continue
        for app in context.get("applications") or []:
            if not isinstance(app, dict):
                continue
            app_key = _canonical(app.get("inst_uuid"))
            node_key = _canonical(node.get("inst_uuid"))
            if app_key and app_key != node_key and app_key in present:
                _add_context_link(links, seen, node.get("inst_uuid"), app.get("inst_uuid"), "context_application", "所属应用", app.get("inst_uuid"))
            system = app.get("system") if isinstance(app.get("system"), dict) else None
            if not system:
                continue
            system_key = _canonical(system.get("inst_uuid"))
            if system_key and system_key in present and system_key != app_key:
                _add_context_link(
                    links,
                    seen,
                    app.get("inst_uuid"),
                    system.get("inst_uuid"),
                    "context_system",
                    "所属系统",
                    system.get("inst_uuid"),
                )
    return links


def _add_context_link(links, seen, src, dst, asst_id, asst_name, parent):
    src_key = _canonical(src)
    dst_key = _canonical(dst)
    if any(item[0] == src_key and item[1] == dst_key for item in seen) or any(item[0] == dst_key and item[1] == src_key for item in seen):
        return
    seen.add((src_key, dst_key, asst_id))
    links.append(
        {
            "src_inst_uuid": src,
            "dst_inst_uuid": dst,
            "model_asst_id": asst_id,
            "asst_id": asst_id,
            "asst_name": asst_name,
            "parent_inst_uuid": parent or "",
            "origin": "ci_context",
        }
    )


def _with_alert_fields(node, state, items, outside, member_truncated):
    counted = list(items)
    counts = {"unassigned": 0, "pending": 0, "processing": 0}
    for item in counted:
        if item.get("status") in counts:
            counts[item["status"]] += 1
    level = ""
    if counted and state in {"incident", "active"}:
        level = min(counted, key=lambda item: (_severity(item.get("level")), item.get("id") or 0)).get("level") or ""
    node.update(
        {
            "alert_state": state,
            "alert_count": len(counted) if state != "unknown" else 0,
            "level": level,
            "status_counts": counts,
            "outside_incident_count": outside,
            "member_truncated": bool(member_truncated),
        }
    )
    return node


def _ordered_alerts(entry, incident_index, active_index):
    items = {}
    if entry["kind"] == "seed":
        sources = []
        for key in entry["self_keys"]:
            sources.extend(incident_index.get(key) or [])
            sources.extend(active_index.get(key) or [])
    else:
        sources = []
        for key in list(entry["self_keys"]) + list(entry.get("member_keys") or []):
            sources.extend(active_index.get(key) or [])
    for item in sources:
        items[item["id"]] = item
    return sorted(items.values(), key=lambda item: (0 if item.get("in_incident") else 1, _severity(item.get("level")), item.get("id") or 0))


def _subject_keys(data):
    keys = []
    seen = set()

    def add(value):
        key = _canonical(value)
        if not key or key in seen:
            return
        seen.add(key)
        keys.append(value if isinstance(value, str) else key)

    for node in list(data.get("nodes") or []) + list(data.get("related_candidates") or []):
        if isinstance(node, dict):
            add(node.get("inst_uuid"))
    for context in data.get("contexts") or []:
        if not isinstance(context, dict):
            continue
        for app in context.get("applications") or []:
            if not isinstance(app, dict):
                continue
            add(app.get("inst_uuid"))
            system = app.get("system") if isinstance(app.get("system"), dict) else None
            if system:
                add(system.get("inst_uuid"))
    for member in data.get("application_members") or []:
        if not isinstance(member, dict):
            continue
        add(member.get("inst_uuid"))
        for item in member.get("member_uuids") or []:
            add(item)
    return keys


def _load_active_alerts(queryset, keys):
    if queryset is None or not keys:
        return []
    wanted = {_canonical(item) for item in keys}
    query_keys = [str(item) for item in keys if _text(item)]
    found = (
        queryset.exclude(is_session_alert=True, session_status=SessionStatus.OBSERVING)
        .filter(status__in=tuple(AlertStatus.ACTIVATE_STATUS))
        .filter(events__cmdb_id__in=query_keys)
        .order_by()
        .distinct()
    )
    alerts = []
    for alert in found:
        if any(key in wanted for key in _cmdb_keys(alert)):
            alerts.append(alert)
    return alerts


def _index_alerts(alerts, incident_ids):
    index = {}
    for alert in alerts:
        item = {
            "id": alert.id,
            "alert_id": getattr(alert, "alert_id", "") or "",
            "title": getattr(alert, "title", "") or "",
            "level": "" if getattr(alert, "level", None) is None else str(alert.level),
            "status": getattr(alert, "status", "") or "",
            "in_incident": alert.id in incident_ids,
        }
        for key in _cmdb_keys(alert):
            bucket = index.setdefault(key, [])
            if any(existing["id"] == item["id"] for existing in bucket):
                continue
            bucket.append(item)
    return index


def _cmdb_keys(alert):
    objects = getattr(alert, "monitor_objects", None)
    keys = []
    seen = set()
    if not isinstance(objects, list):
        return keys
    for item in objects:
        if not isinstance(item, dict):
            continue
        key = _canonical(item.get("cmdb_id"))
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def _severity_item(item):
    return _severity(item.get("level"))


def _severity(level):
    try:
        return int(str(level))
    except (TypeError, ValueError):
        return 10**9
