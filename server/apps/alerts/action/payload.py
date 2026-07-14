TOP_FIELDS = ["alert_id", "title", "content", "level", "status",
              "resource_id", "resource_name", "resource_type", "item", "source_name"]


def _flatten(prefix, value, out):
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}" if prefix else k, v, out)
    else:
        out[prefix] = value


def build_match_payload(alert) -> dict:
    """把 Alert 扁平成 {顶层字段 + labels.* + enrichment.* + source_id(来自关联事件)} 的 dict。

    关于 source 字段过滤，约定如下：
      - 推荐用 key='source_name', value='NATS'  （payload 顶层即有，可读性更好）
      - 历史数据可能用 key='source_id', value=2   （从关联事件第一条 snapshot，
        这是 Alert 模型上不存在的字段，仅通过此路径暴露，便于向后兼容）
    """
    payload = {}
    for f in TOP_FIELDS:
        payload[f] = getattr(alert, f, None)
    _flatten("labels", getattr(alert, "labels", {}) or {}, payload)
    _flatten("enrichment", getattr(alert, "enrichment", {}) or {}, payload)

    # 暴露关联事件第一条的 source_id，让 match_rules 既能写 source_id 也能写 source_name。
    # 只在有关联事件时填入；无事件时 key 不存在，避免 None 被当成有效值。
    events = getattr(alert, "events", None)
    if events is not None:
        first_evt = events.first()
        if first_evt is not None:
            payload["source_id"] = getattr(first_evt, "source_id", None)
    return payload


def resolve_field(payload: dict, path: str):
    """点号路径取值；缺失返回 None。"""
    return payload.get(path)
