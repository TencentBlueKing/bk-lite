"""把监控对象的展示字段收成指标列，并整理实例上的当前值。

字段/属性列（如 IP）不进入结果。某个指标没有数值时保留空值，不用别的指标顶上。
"""

from apps.monitor.utils.dimension import normalize_instance_identity
from apps.monitor.utils.display_fields_metrics import display_field_key, is_field_display_column

DISPLAY_METRICS_INSTANCE_CAP = 50


def localize_metric_column_names(columns, object_name, translations, customized=False) -> list[dict]:
    """默认列用当前语言的指标译名。用户改过的列名保持原样。"""
    if not isinstance(columns, list):
        return []
    if customized or not isinstance(object_name, str) or not object_name:
        return [column for column in columns if isinstance(column, dict)]
    lookup = translations if isinstance(translations, dict) else {}
    localized = []
    for column in columns:
        if not isinstance(column, dict):
            continue
        name = column.get("name") if isinstance(column.get("name"), str) else ""
        metric = _column_metric_name(column)
        if metric:
            translated = lookup.get(f"monitor_object_metric.{object_name}.{metric}.name")
            if isinstance(translated, str) and translated.strip():
                name = translated.strip()
        localized.append({**column, "name": name})
    return localized


def _column_metric_name(column) -> str:
    keys = column.get("keys") or []
    if not keys or not isinstance(keys[0], str):
        return ""
    key = keys[0]
    if key.startswith("field::"):
        return ""
    return key.rsplit("::", 1)[-1]


def metric_display_columns(display_fields) -> list[dict]:
    indexed = []
    for index, col in enumerate(display_fields or []):
        if isinstance(col, dict):
            indexed.append((index, col))
    indexed.sort(key=lambda pair: (_sort_order(pair[1]), pair[0]))
    columns = []
    for _, col in indexed:
        if is_field_display_column(col):
            continue
        keys = []
        seen = set()
        for binding in col.get("metrics") or []:
            if not isinstance(binding, dict):
                continue
            metric = binding.get("metric")
            if not isinstance(metric, str) or not metric:
                continue
            plugin = binding.get("plugin") if isinstance(binding.get("plugin"), str) else ""
            key = display_field_key(plugin, metric)
            if not key or key in seen:
                continue
            seen.add(key)
            keys.append(key)
        if not keys:
            continue
        name = col.get("name") if isinstance(col.get("name"), str) else ""
        columns.append({"name": name, "keys": keys})
    return columns


def display_metric_lookup_keys(token: str) -> list[str]:
    """主键候选：先原始值，再存储键。两者相同则只留一个。"""
    text = str(token or "").strip()
    if not text:
        return []
    keys = [text]
    try:
        storage = normalize_instance_identity(text)["storage_instance_key"]
    except ValueError:
        storage = ""
    if isinstance(storage, str) and storage and storage not in keys:
        keys.append(storage)
    return keys


def normalize_metric_cell(raw) -> dict:
    if isinstance(raw, dict):
        value = raw.get("value")
        unit = raw.get("unit") if isinstance(raw.get("unit"), str) else ""
    else:
        value, unit = raw, ""
    if isinstance(value, bool) or value in (None, ""):
        return {"value": None, "unit": unit}
    if isinstance(value, (int, float)) or isinstance(value, str):
        return {"value": value, "unit": unit}
    return {"value": None, "unit": unit}


def metric_value_map(row: dict, columns: list[dict]) -> dict:
    values = {}
    source = row if isinstance(row, dict) else {}
    for column in columns:
        for key in column.get("keys") or []:
            if key in source:
                values[key] = normalize_metric_cell(source.get(key))
            else:
                values[key] = {"value": None, "unit": ""}
    return values


def _sort_order(col: dict):
    value = col.get("sort_order")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return value
