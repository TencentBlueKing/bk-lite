from django.utils import timezone

from apps.alerts.open_api.errors import AlertsOpenAPIError
from apps.alerts.serializers.alert import AlertModelSerializer

_ALLOWED_ORDERING = {"created_at", "-created_at"}


def _validation_error(message: str = "参数非法") -> None:
    raise AlertsOpenAPIError("alerts.validation.failed", message, 400)


def _parse_positive_int(value, *, field_name: str, default=None, max_value=None):
    if value is None or value == "":
        if default is not None:
            return default
        _validation_error(f"{field_name} 必须是正整数")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        _validation_error(f"{field_name} 必须是正整数")
    if parsed < 1:
        _validation_error(f"{field_name} 必须是正整数")
    if max_value is not None and parsed > max_value:
        return max_value
    return parsed


def parse_pagination(query_params, *, max_page_size=100) -> tuple[int, int]:
    page = _parse_positive_int(query_params.get("page"), field_name="page", default=1)
    page_size = _parse_positive_int(
        query_params.get("page_size"),
        field_name="page_size",
        default=20,
        max_value=max_page_size,
    )
    return page, page_size


def parse_ordering(query_params) -> str:
    ordering = query_params.get("ordering") or "-created_at"
    if ordering not in _ALLOWED_ORDERING:
        _validation_error("ordering 仅支持 created_at 或 -created_at")
    return ordering


def _format_datetime(dt):
    if dt is None:
        return None
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M:%S")


def _get_event_count(alert) -> int:
    annotated = getattr(alert, "event_count_annotated", None)
    if annotated is not None:
        return annotated
    events = getattr(alert, "events", None)
    if events is not None and hasattr(events, "count"):
        return events.count()
    return 0


def serialize_alert(alert, *, detail: bool = False) -> dict:
    data = {
        "alert_id": alert.alert_id,
        "title": alert.title,
        "content": alert.content,
        "status": alert.status,
        "level": alert.level,
        "source_name": alert.source_name or "",
        "operator": alert.operator or [],
        "item": alert.item,
        "resource_id": alert.resource_id,
        "resource_type": alert.resource_type,
        "resource_name": alert.resource_name,
        "rule_id": alert.rule_id,
        "fingerprint": alert.fingerprint,
        "dimensions": alert.dimensions or {},
        "first_event_time": _format_datetime(alert.first_event_time),
        "last_event_time": _format_datetime(alert.last_event_time),
        "closed_at": _format_datetime(getattr(alert, "closed_at", None)),
        "created_at": _format_datetime(alert.created_at),
        "updated_at": _format_datetime(alert.updated_at),
        "event_count": _get_event_count(alert),
        "duration": AlertModelSerializer.get_duration(alert),
    }
    if detail:
        data["labels"] = alert.labels or {}
        data["enrichment"] = alert.enrichment or {}
    return data


def _get_event_source(event):
    source = getattr(event, "source", None)
    if source is None:
        return None
    return getattr(source, "id", None) or getattr(source, "pk", None)


def _get_event_source_name(event) -> str:
    source = getattr(event, "source", None)
    if source is None:
        return ""
    return getattr(source, "name", "") or ""


def serialize_event(event) -> dict:
    return {
        "event_id": event.event_id,
        "title": event.title,
        "description": event.description or "",
        "level": event.level,
        "action": event.action,
        "status": event.status,
        "source": _get_event_source(event),
        "source_name": _get_event_source_name(event),
        "resource_id": event.resource_id,
        "resource_type": event.resource_type,
        "resource_name": event.resource_name,
        "item": event.item,
        "value": event.value,
        "start_time": _format_datetime(event.start_time),
        "end_time": _format_datetime(event.end_time),
        "received_at": _format_datetime(event.received_at),
    }


def parse_operator_payload(action: str, data) -> dict:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        _validation_error("请求体必须是 JSON 对象")

    action = (action or "").lower()
    result: dict = {}

    if action in ("assign", "reassign"):
        assignee = data.get("assignee")
        if not assignee or not isinstance(assignee, list) or not all(isinstance(x, str) and x for x in assignee):
            _validation_error("assignee 必须是非空字符串数组")
        result["assignee"] = assignee
        if "assignment_id" in data and data["assignment_id"] is not None:
            try:
                result["assignment_id"] = int(data["assignment_id"])
            except (TypeError, ValueError):
                _validation_error("assignment_id 必须是整数")
    elif action == "close":
        if "reason" in data:
            reason = data["reason"]
            if reason is not None and not isinstance(reason, str):
                _validation_error("reason 必须是字符串")
            result["reason"] = reason
    elif action == "acknowledge":
        pass
    else:
        _validation_error(f"不支持的操作: {action}")

    return result


def parse_batch_payload(action: str, data) -> dict:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        _validation_error("请求体必须是 JSON 对象")

    alert_ids = data.get("alert_ids")
    if not alert_ids or not isinstance(alert_ids, list):
        _validation_error("alert_ids 必须是非空数组")
    if not (1 <= len(alert_ids) <= 100):
        _validation_error("alert_ids 长度必须在 1 到 100 之间")
    if not all(isinstance(x, str) and x for x in alert_ids):
        _validation_error("alert_ids 必须是字符串数组")

    operator_fields = {key: value for key, value in data.items() if key != "alert_ids"}
    parsed_operator = parse_operator_payload(action, operator_fields)
    return {"alert_ids": alert_ids, **parsed_operator}
