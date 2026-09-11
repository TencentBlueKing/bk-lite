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


def build_match_payload(alert) -> dict:
    """保留动作参数绑定使用的首个关联事件 source_id。"""
    payload = _base_payload(alert)
    events = getattr(alert, "events", None)
    first_event = events.first() if events is not None else None
    if first_event is not None:
        payload["source_id"] = first_event.source_id
    return payload


def resolve_field(payload: dict, path: str):
    """点号路径取值；缺失返回 None。"""
    return payload.get(path)


def build_rule_payload(alert, *, include_source_names=True):
    """派生来源仅供规则评估，不改变动作参数绑定的字段协议。"""
    from apps.alerts.service.source_names import source_names_by_alert

    payload = _base_payload(alert)
    if include_source_names:
        payload["source_names"] = source_names_by_alert([alert.pk], alert._state.db or "default")[alert.pk]
    return payload
