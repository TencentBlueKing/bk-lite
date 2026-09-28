from apps.alerts.notification_templates.events import EVENT_JSON_ROOTS, EVENT_SCALAR_FIELDS

TOP_FIELDS = [
    "alert_id",
    "title",
    "content",
    "level",
    "status",
    "resource_id",
    "resource_name",
    "resource_type",
    "item",
    "source_name",
    "push_source_ids",
]


def _flatten(prefix, value, out):
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}" if prefix else k, v, out)
    else:
        out[prefix] = value


def _base_payload(alert) -> dict:
    """Alert 当前字段与操作参数绑定使用的 labels/enrichment 点号路径。"""
    payload = {}
    for f in TOP_FIELDS:
        payload[f] = getattr(alert, f, None)
    _flatten("labels", getattr(alert, "labels", {}) or {}, payload)
    _flatten("enrichment", getattr(alert, "enrichment", {}) or {}, payload)

    return payload


def _copy_event_fields(event, payload):
    """把代表事件的标量和 JSON 叶子铺进 payload。MagicMock 等非标量值直接跳过。"""
    for field in EVENT_SCALAR_FIELDS:
        if field == "source_name":
            source = getattr(event, "source", None)
            value = getattr(source, "name", None) if source is not None else None
        else:
            value = getattr(event, field, None)
        if isinstance(value, (str, int, float, bool)) and value != "":
            payload[f"event.{field}"] = value
    for root in EVENT_JSON_ROOTS:
        raw = getattr(event, root, None)
        if isinstance(raw, dict):
            _flatten(f"event.{root}", raw, payload)


def build_match_payload(alert) -> dict:
    """保留动作参数绑定使用的首个关联事件 source_id，并铺平该事件的白名单字段。"""
    payload = _base_payload(alert)
    events = getattr(alert, "events", None)
    first_event = events.first() if events is not None else None
    if first_event is not None:
        source_id = getattr(first_event, "source_id", None)
        if isinstance(source_id, (str, int)) and not isinstance(source_id, bool):
            payload["source_id"] = source_id
        _copy_event_fields(first_event, payload)
    return payload


def resolve_field(payload: dict, path: str):
    """点号路径取值；缺失返回 None。"""
    return payload.get(path)


LIFECYCLE_TRIGGER_EVENTS = ("created", "assigned", "acknowledged", "resolved", "closed")

# 手动执行没有生命周期事件，按告警当前状态映射为同一套 Key。
_STATUS_TO_TRIGGER_EVENT = {
    "unassigned": "created",
    "pending": "assigned",
    "processing": "acknowledged",
    "resolved": "resolved",
    "auto_recovery": "resolved",
    "closed": "closed",
    "auto_close": "closed",
}


def resolve_trigger_event_param(execution, alert) -> str:
    event = getattr(execution, "trigger_event", None)
    if isinstance(event, str) and event in LIFECYCLE_TRIGGER_EVENTS:
        return event
    status = getattr(alert, "status", None)
    if not isinstance(status, str) or not status:
        return ""
    return _STATUS_TO_TRIGGER_EVENT.get(status, status)


def build_rule_payload(alert, *, include_source_names=True):
    """派生来源仅供规则评估，不改变动作参数绑定的字段协议。"""
    from apps.alerts.service.source_names import source_names_by_alert

    payload = _base_payload(alert)
    if include_source_names:
        payload["source_names"] = source_names_by_alert([alert.pk], alert._state.db or "default")[alert.pk]
    return payload
