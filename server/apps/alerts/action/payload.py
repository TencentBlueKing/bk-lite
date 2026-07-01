TOP_FIELDS = ["alert_id", "title", "content", "level", "status",
              "resource_id", "resource_name", "resource_type", "item", "source_name"]


def _flatten(prefix, value, out):
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}" if prefix else k, v, out)
    else:
        out[prefix] = value


def build_match_payload(alert) -> dict:
    """把 Alert 扁平成 {顶层字段 + labels.* + enrichment.*} 的 dict。"""
    payload = {}
    for f in TOP_FIELDS:
        payload[f] = getattr(alert, f, None)
    _flatten("labels", getattr(alert, "labels", {}) or {}, payload)
    _flatten("enrichment", getattr(alert, "enrichment", {}) or {}, payload)
    return payload


def resolve_field(payload: dict, path: str):
    """点号路径取值；缺失返回 None。"""
    return payload.get(path)
