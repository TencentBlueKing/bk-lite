"""机房大屏统计：设备类型、机柜容量、活跃告警。

只统计机房 → 机柜 → 设备。监控整体失败时，覆盖视图把已绑定设备计入
「告警暂不可用」，其余视图返回失败，不把失败伪装成 0。
"""

from __future__ import annotations

from collections import defaultdict

from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.instance_identity import optional_inst_uuid
from apps.cmdb.services.instance_scope import resolve_room_rack_devices
from apps.cmdb.services.rack_room import _safe_int, list_server_rooms, rack_u_occupancy
from apps.cmdb.services.room3d_device_alarms import (
    COVERAGE_ALARM_UNAVAILABLE,
    COVERAGE_MONITORED_ALARMING,
    COVERAGE_MONITORED_CLEAR,
    COVERAGE_UNMONITORED,
    _default_monitor_client,
    classify_device_alarm_coverage,
)
from apps.core.logger import cmdb_logger as logger

MONITOR_ID_BATCH_SIZE = 500
_COVERAGE_ORDER = (
    COVERAGE_MONITORED_CLEAR,
    COVERAGE_MONITORED_ALARMING,
    COVERAGE_UNMONITORED,
    COVERAGE_ALARM_UNAVAILABLE,
)
_COVERAGE_LABELS = {
    "zh": {
        COVERAGE_MONITORED_CLEAR: "已监控无告警",
        COVERAGE_MONITORED_ALARMING: "已监控有告警",
        COVERAGE_UNMONITORED: "未监控",
        COVERAGE_ALARM_UNAVAILABLE: "告警暂不可用",
    },
    "en": {
        COVERAGE_MONITORED_CLEAR: "Monitored without alarms",
        COVERAGE_MONITORED_ALARMING: "Monitored with alarms",
        COVERAGE_UNMONITORED: "Unmonitored",
        COVERAGE_ALARM_UNAVAILABLE: "Alarms unavailable",
    },
}
_SEVERITY_ORDER = ("critical", "error", "warning")
_SEVERITY_RANK = {"critical": 3, "error": 2, "warning": 1}
_SEVERITY_LABELS = {
    "zh": {"critical": "严重", "error": "错误", "warning": "警告"},
    "en": {"critical": "Critical", "error": "Error", "warning": "Warning"},
}
_CAPACITY_VIEWS = {"summary", "rack_top"}
_ALARM_VIEWS = {"coverage", "level_distribution", "rack_top", "device_list"}


def _language_code(language: str | None) -> str:
    return "en" if str(language or "").lower().startswith("en") else "zh"


def _error(message: str, code: int = 400) -> dict:
    return {"result": False, "data": {}, "message": message, "code": code}


def _ok(data) -> dict:
    return {"result": True, "data": data, "message": ""}


def _parse_limit(value, default: int = 5, maximum: int = 50) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 1:
        return default
    return min(parsed, maximum)


def _room_error_from_locator(server_room_id, parse_locator):
    locator = parse_locator(server_room_id)
    if locator is None:
        return _error("server_room_id 参数必须为 UUIDv4"), None
    return None, locator


def resolve_target_room(*, server_room_id, permission_map, user, user_info, parse_locator):
    """显式机房不可见时失败；空 id 取可见机房列表的第一条，排序与 get_room_list 一致。"""
    if permission_map is None:
        return _error("无权限查看当前机房", code=403), None
    text = "" if server_room_id in (None, "") else str(server_room_id).strip()
    if not text:
        rooms = [item for item in list_server_rooms(permission_map=permission_map, user_info=user_info) if item.get("inst_uuid")]
        if not rooms:
            return _error("没有可见机房", code=404), None
        return None, rooms[0]
    error, locator = _room_error_from_locator(text, parse_locator)
    if error:
        return error, None
    locator_type, locator_value = locator
    if locator_type == "uuid":
        room = InstanceManage.query_entity_by_uuid(locator_value)
    else:
        room = InstanceManage.query_entity_by_id(locator_value)
    if not room:
        return _error("机房实例不存在", code=404), None
    if room.get("model_id") != "server_room":
        return _error("server_room_id 必须指向 server_room 实例"), None
    if not optional_inst_uuid(room.get("inst_uuid")):
        return _error("机房实例缺少合法 inst_uuid", code=409), None
    if not InstanceManage._has_topology_view_permission(room, permission_map, user=user):
        return _error("无权限查看当前机房", code=403), None
    return None, room


def _model_display_names(language: str) -> dict[str, str]:
    from apps.cmdb.services.model import ModelManage

    try:
        models = ModelManage.search_model(language=language, include_hidden=True) or []
    except Exception as exc:
        logger.warning(
            "scoped instance group model names failed failed_stage=model_catalog error_type=%s",
            type(exc).__name__,
        )
        return {}
    names = {}
    for model in models:
        if not isinstance(model, dict) or not model.get("model_id"):
            continue
        names[str(model["model_id"])] = model.get("model_name") or str(model["model_id"])
    return names


def _model_label(instance: dict, model_names: dict[str, str]) -> str:
    model_id = str(instance.get("model_id") or "").strip()
    if not model_id:
        return "unknown"
    return model_names.get(model_id) or model_id


def _rack_usage(rack: dict, devices: list[dict]) -> dict:
    u_count = _safe_int(rack.get("u_count")) or 0
    used_u, free_u, _max_free = rack_u_occupancy(u_count, devices)
    unracked = 0
    for device in devices:
        start = _safe_int(device.get("rack_u_start"))
        size = _safe_int(device.get("u_size"))
        if not start or not size:
            unracked += 1
    usage = round(used_u / u_count * 100) if u_count else 0
    return {
        "u_count": u_count,
        "used_u": used_u,
        "free_u": free_u,
        "usage": usage,
        "device_count": len(devices),
        "unracked_device_count": unracked,
    }


def _iter_room_devices(scope) -> list[tuple[dict, dict]]:
    pairs = []
    for rack in scope.racks:
        rack_uuid = rack.get("inst_uuid")
        for device in scope.devices_by_rack_uuid.get(rack_uuid, []):
            pairs.append((rack, device))
    return pairs


def room_device_type_distribution(
    *,
    server_room_id=None,
    user_info=None,
    permission_map=None,
    user=None,
    language: str = "zh-Hans",
    parse_locator=None,
) -> dict:
    """机柜内可见设备按模型显示名计数，数量降序。"""
    error, scope = _room_scope(
        server_room_id=server_room_id,
        user_info=user_info,
        permission_map=permission_map,
        user=user,
        parse_locator=parse_locator,
    )
    if error:
        return error
    names = _model_display_names(language)
    counts: dict[str, int] = defaultdict(int)
    for _rack, device in _iter_room_devices(scope):
        counts[_model_label(device, names)] += 1
    data = [{"name": name, "value": value} for name, value in counts.items()]
    data.sort(key=lambda item: (-item["value"], item["name"]))
    return _ok(data)


def room_rack_capacity(
    *,
    server_room_id=None,
    view=None,
    limit=None,
    user_info=None,
    permission_map=None,
    user=None,
    parse_locator=None,
) -> dict:
    view_name = str(view or "summary").strip() or "summary"
    if view_name not in _CAPACITY_VIEWS:
        return _error("view 必须是 summary 或 rack_top")
    error, scope = _room_scope(
        server_room_id=server_room_id,
        user_info=user_info,
        permission_map=permission_map,
        user=user,
        parse_locator=parse_locator,
    )
    if error:
        return error
    if view_name == "summary":
        return _ok(_capacity_summary(scope))
    rows = []
    for rack in scope.racks:
        usage = _rack_usage(rack, scope.devices_by_rack_uuid.get(rack.get("inst_uuid"), []))
        rows.append(
            {
                "name": rack.get("inst_name") or rack.get("inst_uuid") or "",
                "value": usage["usage"],
                "used_u": usage["used_u"],
                "u_count": usage["u_count"],
            }
        )
    rows.sort(key=lambda item: (-item["value"], item["name"]))
    return _ok(rows[: _parse_limit(limit)])


def room_active_alarms(
    *,
    server_room_id=None,
    view=None,
    limit=None,
    user_info=None,
    permission_map=None,
    user=None,
    language: str = "zh-Hans",
    parse_locator=None,
    monitor_client_factory=None,
) -> dict:
    if permission_map is None:
        return _error("无权限查看当前机房", code=403)
    view_name = str(view or "coverage").strip() or "coverage"
    if view_name not in _ALARM_VIEWS:
        return _error("view 必须是 coverage、level_distribution、rack_top 或 device_list")
    error, scope = _room_scope(
        server_room_id=server_room_id,
        user_info=user_info,
        permission_map=permission_map,
        user=user,
        parse_locator=parse_locator,
    )
    if error:
        return error
    placed = _iter_room_devices(scope)

    summaries, monitor_failed = _load_alarm_summaries(
        placed,
        user_info=user_info,
        monitor_client_factory=monitor_client_factory,
    )
    if monitor_failed and view_name != "coverage":
        logger.warning(
            "scoped alarm stats monitor failed view=%s device_count=%s failed_stage=monitor_result error_type=monitor_failed",
            view_name,
            len(placed),
        )
        return _error("告警统计暂不可用", code=503)
    lang = _language_code(language)
    if view_name == "coverage":
        return _ok(_coverage_rows(placed, summaries, monitor_failed=monitor_failed, language=lang))
    if view_name == "level_distribution":
        rows = _level_rows(placed, summaries, language=lang)
        if rows is None:
            return _error("告警等级计数缺失", code=503)
        return _ok(rows)
    if view_name == "rack_top":
        return _ok(_alarm_rack_top(placed, summaries, limit=_parse_limit(limit)))
    return _ok(_alarm_device_list(placed, summaries, language=lang, limit=_parse_limit(limit, default=20)))


def _room_scope(*, server_room_id, user_info, permission_map, user, parse_locator):
    error, room = resolve_target_room(
        server_room_id=server_room_id,
        permission_map=permission_map,
        user=user,
        user_info=user_info,
        parse_locator=parse_locator,
    )
    if error:
        return error, None
    scope = resolve_room_rack_devices(room.get("inst_uuid"), permission_map=permission_map, user=user)
    return None, scope


def _capacity_summary(scope) -> dict:
    pairs = _iter_room_devices(scope)
    total_u = 0
    used_u = 0
    free_u = 0
    unracked = 0
    for rack in scope.racks:
        usage = _rack_usage(rack, scope.devices_by_rack_uuid.get(rack.get("inst_uuid"), []))
        total_u += usage["u_count"]
        used_u += usage["used_u"]
        free_u += usage["free_u"]
        unracked += usage["unracked_device_count"]
    return {
        "rack_count": len(scope.racks),
        "device_count": len(pairs),
        "unracked_device_count": unracked,
        "total_u": total_u,
        "used_u": used_u,
        "free_u": free_u,
        "u_usage_percent": round(used_u / total_u * 100) if total_u else 0,
    }


def _monitor_id_of(device: dict) -> str:
    raw = device.get("monitor_id")
    if raw in (None, ""):
        return ""
    return str(raw).strip()


def _load_alarm_summaries(placed, *, user_info, monitor_client_factory=None) -> tuple[dict[str, dict], bool]:
    monitor_ids = []
    seen = set()
    for _parent, device in placed:
        monitor_id = _monitor_id_of(device)
        if monitor_id and monitor_id not in seen:
            seen.add(monitor_id)
            monitor_ids.append(monitor_id)
    if not monitor_ids:
        return {}, False
    factory = monitor_client_factory or _default_monitor_client
    merged: dict[str, dict] = {}
    try:
        client = factory()
        for offset in range(0, len(monitor_ids), MONITOR_ID_BATCH_SIZE):
            batch = monitor_ids[offset : offset + MONITOR_ID_BATCH_SIZE]
            response = client.query_active_alert_summaries_by_monitor_ids(batch, user_info=user_info or {})
            if not isinstance(response, dict) or response.get("result") is not True:
                logger.warning(
                    "scoped alarm stats monitor rejected monitor_id_count=%s failed_stage=monitor_result error_type=%s",
                    len(monitor_ids),
                    "invalid_response" if not isinstance(response, dict) else "result_false",
                )
                return {}, True
            data = response.get("data")
            items = (data.get("items") if isinstance(data, dict) else None) or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                monitor_id = str(item.get("monitor_id") or "").strip()
                if monitor_id:
                    merged[monitor_id] = item
    except Exception as exc:
        logger.exception(
            "scoped alarm stats monitor failed monitor_id_count=%s failed_stage=monitor_rpc error_type=%s",
            len(monitor_ids),
            type(exc).__name__,
        )
        return {}, True
    return merged, False


def _coverage_rows(placed, summaries, *, monitor_failed: bool, language: str) -> list[dict]:
    labels = _COVERAGE_LABELS[language]
    counts = {key: 0 for key in _COVERAGE_ORDER}
    for _parent, device in placed:
        monitor_id = _monitor_id_of(device)
        summary = None if monitor_failed else summaries.get(monitor_id)
        category = classify_device_alarm_coverage(monitor_id, summary, monitor_failed=monitor_failed)
        counts[category] += 1
    return [{"name": labels[key], "value": counts[key]} for key in _COVERAGE_ORDER]


def _level_counts_of(summary: dict) -> dict[str, int] | None:
    raw = summary.get("level_counts")
    if isinstance(raw, dict):
        parsed = {}
        for level in _SEVERITY_ORDER:
            try:
                parsed[level] = int(raw.get(level) or 0)
            except (TypeError, ValueError):
                return None
            if parsed[level] < 0:
                return None
        return parsed
    try:
        count = int(summary.get("active_alarm_count") or 0)
    except (TypeError, ValueError):
        return None
    if count <= 0:
        return {level: 0 for level in _SEVERITY_ORDER}
    return None


def _level_rows(placed, summaries, *, language: str) -> list[dict] | None:
    totals = {level: 0 for level in _SEVERITY_ORDER}
    for _parent, device in placed:
        monitor_id = _monitor_id_of(device)
        if not monitor_id:
            continue
        summary = summaries.get(monitor_id)
        if not isinstance(summary, dict):
            continue
        category = classify_device_alarm_coverage(monitor_id, summary, monitor_failed=False)
        if category != COVERAGE_MONITORED_ALARMING:
            continue
        counts = _level_counts_of(summary)
        if counts is None:
            return None
        for level in _SEVERITY_ORDER:
            totals[level] += counts[level]
    labels = _SEVERITY_LABELS[language]
    rows = [{"name": labels[level], "value": totals[level]} for level in _SEVERITY_ORDER if totals[level] > 0]
    rows.sort(key=lambda item: (-item["value"], item["name"]))
    return rows


def _alarm_rack_top(placed, summaries, *, limit: int) -> list[dict]:
    totals: dict[str, int] = defaultdict(int)
    for parent, device in placed:
        monitor_id = _monitor_id_of(device)
        summary = summaries.get(monitor_id) if monitor_id else None
        if not isinstance(summary, dict):
            continue
        if classify_device_alarm_coverage(monitor_id, summary, monitor_failed=False) != COVERAGE_MONITORED_ALARMING:
            continue
        try:
            count = int(summary.get("active_alarm_count") or 0)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        name = (parent or {}).get("inst_name") or (parent or {}).get("inst_uuid") or ""
        totals[str(name)] += count
    rows = [{"name": name, "value": value} for name, value in totals.items() if value > 0]
    rows.sort(key=lambda item: (-item["value"], item["name"]))
    return rows[:limit]


def _u_position(device: dict) -> str:
    start = _safe_int(device.get("rack_u_start"))
    size = _safe_int(device.get("u_size"))
    if not start or not size:
        return ""
    return f"{start}-{start + size - 1}"


def _alarm_device_list(placed, summaries, *, language: str, limit: int) -> list[dict]:
    model_names = _model_display_names("en" if language == "en" else "zh-Hans")
    severity_labels = _SEVERITY_LABELS[language]
    rows = []
    for parent, device in placed:
        monitor_id = _monitor_id_of(device)
        summary = summaries.get(monitor_id) if monitor_id else None
        if not isinstance(summary, dict):
            continue
        if classify_device_alarm_coverage(monitor_id, summary, monitor_failed=False) != COVERAGE_MONITORED_ALARMING:
            continue
        try:
            count = int(summary.get("active_alarm_count") or 0)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        severity = summary.get("highest_severity")
        if severity not in _SEVERITY_RANK:
            severity = None
        model_id = str(device.get("model_id") or "")
        rows.append(
            {
                "device_name": device.get("inst_name") or "",
                "model_name": model_names.get(model_id) or model_id,
                "rack_name": (parent or {}).get("inst_name") or "",
                "u_position": _u_position(device),
                "highest_severity": severity_labels.get(severity, "") if severity else "",
                "active_alarm_count": count,
                "_severity_rank": _SEVERITY_RANK.get(severity, 0),
            }
        )
    rows.sort(key=lambda item: (-item["_severity_rank"], -item["active_alarm_count"], item["device_name"]))
    trimmed = []
    for item in rows[:limit]:
        item.pop("_severity_rank", None)
        trimmed.append(item)
    return trimmed
