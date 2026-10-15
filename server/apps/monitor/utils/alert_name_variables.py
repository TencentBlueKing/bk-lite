import re

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.utils.display_fields_metrics import display_field_key

RESERVED_ALERT_TEMPLATE_KEYS = frozenset(
    {
        "monitor_object",
        "resource_id",
        "resource_name",
        "parent_resource_id",
        "parent_resource_name",
        "level",
        "metric_name",
        "value",
        "dimension_value",
        "resource_ip",
        "instance_name",
        "instance_id",
        "monitor_instance_id",
        "metric_instance_id",
    }
)

VARIABLE_ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ASSET_IP_FACT = "asset.ip"


def normalize_variable_id(raw) -> str:
    if raw is None:
        return ""
    return str(raw).strip()


def validate_variable_id(variable_id: str, used: set[str], column_name: str):
    """校验展示列 variable_id；空值表示不作为告警名称变量。"""
    if not variable_id:
        return
    if not VARIABLE_ID_PATTERN.fullmatch(variable_id):
        raise BaseAppException(f"display field '{column_name}' has invalid variable_id: {variable_id}")
    if variable_id in RESERVED_ALERT_TEMPLATE_KEYS or variable_id.startswith("metric__"):
        raise BaseAppException(f"display field '{column_name}' uses reserved variable_id: {variable_id}")
    if variable_id in used:
        raise BaseAppException(f"display field variable_id '{variable_id}' is duplicated")
    used.add(variable_id)


def resolve_resource_ip(summary_facts, ip) -> str:
    if isinstance(summary_facts, dict):
        fact = summary_facts.get(ASSET_IP_FACT)
        if fact not in (None, ""):
            return str(fact).strip()
    if ip not in (None, ""):
        return str(ip).strip()
    return ""


_NOTIFICATION_FACT_PART = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_NOTIFICATION_SENSITIVE_PARTS = ("password", "token", "secret", "private_key", "credential")
_NOTIFICATION_FACT_MAX_LENGTH = 1000


def _notification_fact_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("name") or item.get("ip") or "").strip()
            elif item not in (None, ""):
                text = str(item).strip()
            else:
                text = ""
            if text:
                parts.append(text)
        return "、".join(parts)
    return ""


def _put_notification_fact(labels: dict, fact: str, value: str) -> None:
    parts = fact.split(".")
    if not parts or any(not _NOTIFICATION_FACT_PART.fullmatch(part) for part in parts):
        return
    cursor = labels
    for part in parts[:-1]:
        child = cursor.get(part)
        if child is None:
            child = {}
            cursor[part] = child
        elif not isinstance(child, dict):
            return
        cursor = child
    leaf = parts[-1]
    if cursor.get(leaf) in (None, ""):
        cursor[leaf] = value


def build_instance_notification_labels(summary_facts, ip, summary_columns) -> dict:
    """按监控对象自己声明的摘要列，整理可放进告警通知的实例资料。"""
    facts = summary_facts if isinstance(summary_facts, dict) else {}
    labels = {}
    resolved_ip = resolve_resource_ip(facts, ip)
    if resolved_ip:
        labels["ip"] = resolved_ip[:_NOTIFICATION_FACT_MAX_LENGTH]
    for column in summary_columns or []:
        if not isinstance(column, dict):
            continue
        fact = str(column.get("fact") or "").strip()
        if not fact or any(part in fact.lower() for part in _NOTIFICATION_SENSITIVE_PARTS):
            continue
        text = _notification_fact_text(facts.get(fact))
        if not text:
            continue
        _put_notification_fact(labels, fact, text[:_NOTIFICATION_FACT_MAX_LENGTH])
    return labels


def iter_variable_id_columns(display_fields):
    for col in display_fields or []:
        if not isinstance(col, dict):
            continue
        variable_id = normalize_variable_id(col.get("variable_id"))
        if variable_id:
            yield variable_id, col


def format_display_cell_value(raw) -> str:
    if raw is None or raw == "":
        return ""
    if isinstance(raw, dict):
        value = raw.get("value")
        if value is None or value == "":
            return ""
        return str(value)
    return str(raw)


def extract_display_variable_values(row: dict, display_fields) -> dict:
    values = {}
    for variable_id, col in iter_variable_id_columns(display_fields):
        col_type = col.get("type") or "metric"
        value = ""
        for binding in col.get("metrics") or []:
            key = display_field_key(
                binding.get("plugin") or "",
                binding.get("metric") or "",
                binding.get("field") if col_type == "field" else None,
            )
            value = format_display_cell_value(row.get(key))
            if value:
                break
        values[variable_id] = value
    return values


def field_label_map(display_fields) -> dict[str, str]:
    """variable_id -> 字段列绑定的 VM label key（仅 type=field）。"""
    mapping = {}
    for variable_id, col in iter_variable_id_columns(display_fields):
        if (col.get("type") or "metric") != "field":
            continue
        for binding in col.get("metrics") or []:
            field = (binding.get("field") or "").strip()
            if field:
                mapping[variable_id] = field
                break
    return mapping


def overlay_dimension_field_values(values: dict, dimensions: dict, label_map: dict) -> dict:
    if not dimensions or not label_map:
        return values
    merged = dict(values)
    for variable_id, field in label_map.items():
        raw = dimensions.get(field)
        if raw not in (None, ""):
            merged[variable_id] = str(raw)
    return merged


def load_display_variable_map(monitor_object, instance_ids: list[str]) -> dict[str, dict]:
    """对本轮策略实例批量回填带 variable_id 的展示列。"""
    if not monitor_object or not instance_ids:
        return {}
    display_fields = list(iter_variable_id_columns(getattr(monitor_object, "display_fields", None)))
    if not display_fields:
        return {}

    filtered_fields = [col for _, col in display_fields]
    from apps.monitor.services.monitor_object import MonitorObjectService

    rows = [{"instance_id": instance_id} for instance_id in instance_ids]
    obj_metric_map = {
        "display_fields": filtered_fields,
        "instance_id_keys": getattr(monitor_object, "instance_id_keys", None) or [],
        "supplementary_indicators": [],
    }
    MonitorObjectService._safe_fill_display_metrics(
        monitor_object.id,
        obj_metric_map,
        rows,
    )
    return {row["instance_id"]: extract_display_variable_values(row, filtered_fields) for row in rows}
