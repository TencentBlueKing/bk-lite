"""构造不可变的创建输入，在遍历前限制单值，并限制深度、节点与总字节。"""
import json

from apps.alerts.action.payload import TOP_FIELDS
from apps.alerts.itsm.config import MAX_INPUT_BYTES, ItsmError
from apps.alerts.notification_templates.events import EVENT_JSON_ROOTS, EVENT_SCALAR_FIELDS
from apps.alerts.service.source_names import source_members

MAX_NODES = 1024
MAX_DEPTH = 8


def capture_snapshot(alert):
    result = {}
    remaining_bytes, remaining_nodes = MAX_INPUT_BYTES, MAX_NODES

    def consume(value, depth=0):
        nonlocal remaining_bytes, remaining_nodes
        remaining_nodes -= 1
        if depth > MAX_DEPTH or remaining_nodes < 0:
            raise ItsmError("告警创建输入超过深度或字段数量限制，规则未评估")
        if isinstance(value, str):
            if len(value) > remaining_bytes:
                raise ItsmError("告警创建输入超过 64 KiB，规则未评估")
            remaining_bytes -= len(value.encode()) + 4
        elif isinstance(value, dict):
            for key, item in value.items():
                consume(key, depth + 1)
                consume(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                consume(item, depth + 1)
        else:
            remaining_bytes -= 24
        if remaining_bytes < 0:
            raise ItsmError("告警创建输入超过 64 KiB，规则未评估")

    def put(key, value):
        consume(key)
        consume(value)
        result[key] = value

    def flatten(prefix, value, depth=0):
        if depth > MAX_DEPTH:
            raise ItsmError("告警创建输入超过深度限制，规则未评估")
        if isinstance(value, dict):
            # 空对象也计入节点预算，不能靠空分支绕过限制。
            nonlocal remaining_nodes
            remaining_nodes -= 1
            if remaining_nodes < 0:
                raise ItsmError("告警创建输入超过字段数量限制，规则未评估")
            for key, item in value.items():
                if len(str(key)) > 256:
                    raise ItsmError("告警创建输入字段名过长，规则未评估")
                flatten(f"{prefix}.{key}", item, depth + 1)
        else:
            put(prefix, value)

    for field in TOP_FIELDS:
        put(field, getattr(alert, field, None))
    flatten("labels", alert.labels or {})
    flatten("enrichment", alert.enrichment or {})
    event = alert.events.select_related("source").order_by("pk").first()
    if event:
        put("source_id", event.source_id)
        for field in EVENT_SCALAR_FIELDS:
            value = event.source.name if field == "source_name" else getattr(event, field, None)
            if isinstance(value, (str, int, float, bool)) and value != "":
                put(f"event.{field}", value)
        for field in EVENT_JSON_ROOTS:
            flatten(f"event.{field}", getattr(event, field, None) or {})
    names = list(
        source_members(alert._state.db or "default")
        .filter(alert_id=alert.pk)
        .values_list("event__source__name", flat=True)
        .order_by("event__source__name")
        .distinct()[:129]
    )
    if len(names) > 128:
        raise ItsmError("告警创建输入来源数量超过限制，规则未评估")
    put("source_names", names)
    # JSON 转义的实际大小仍检查，但遍历预算已保证分配有界。
    if len(json.dumps(result).encode()) > MAX_INPUT_BYTES:
        raise ItsmError("告警创建输入超过 64 KiB，规则未评估")
    return result
