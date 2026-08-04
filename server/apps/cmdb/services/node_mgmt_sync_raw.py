import re
from typing import Any

RAW_DATA_FIELDS = (
    "id",
    "_id",
    "__name__",
    "model_id",
    "inst_name",
    "name",
    "pid",
    "arg",
    "exe",
    "cwd",
    "ports",
    "ip_addr",
    "ip",
    "cloud",
    "cloud_id",
    "cloud_name",
    "organization",
    "organization_ids",
    "__time__",
    "_status",
    "_error",
)
RAW_DATA_METRIC_MODEL_IDS = {
    "host_info_gauge": "host",
    "host_proc_usage_info_gauge": "host_proc_usage",
}
RAW_TEXT_LIMITS = {
    "_error": 500,
    "arg": 1024,
    "ports": 1024,
    "exe": 512,
    "cwd": 512,
    "inst_name": 512,
    "name": 512,
}
RAW_DEFAULT_TEXT_LIMIT = 255


def sanitize_node_mgmt_raw_text(value: str, *, limit: int) -> str:
    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    sanitized = re.sub(
        r"(?i)(--(?:password|passwd|token|secret|access[_-]?key|private[_-]?key))(?:=|\s+)([^\s]+)",
        r"\1=[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)\b(password|passwd|token|secret|access_key|private_key)\s*[:=]\s*([^\s,;]+)",
        r"\1=[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)(authorization\s*:\s*(?:bearer\s+)?)([^\s,;]+)",
        r"\1[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)([a-z][a-z0-9+.-]*://[^:/\s]+:)([^@\s]+)(@)",
        r"\1[REDACTED]\3",
        sanitized,
    )
    return sanitized[:limit]


def sanitize_node_mgmt_raw_data_item(item: dict[str, Any]) -> dict[str, Any]:
    sanitized = {key: item.get(key) for key in RAW_DATA_FIELDS if key in item}
    metric_name = item.get("__name__")
    if metric_name in RAW_DATA_METRIC_MODEL_IDS:
        sanitized["model_id"] = RAW_DATA_METRIC_MODEL_IDS[metric_name]
    if sanitized.get("model_id") in (None, ""):
        sanitized["model_id"] = "host"
    if sanitized.get("_status") in (None, "") and item.get("collect_status") not in (None, ""):
        sanitized["_status"] = item["collect_status"]
    if sanitized.get("_error") in (None, "") and item.get("cmdb_collect_error") not in (None, ""):
        sanitized["_error"] = item["cmdb_collect_error"]
    for key, value in tuple(sanitized.items()):
        if isinstance(value, str):
            sanitized[key] = sanitize_node_mgmt_raw_text(
                value,
                limit=RAW_TEXT_LIMITS.get(key, RAW_DEFAULT_TEXT_LIMIT),
            )
        elif key == "ports" and isinstance(value, list):
            sanitized[key] = [
                sanitize_node_mgmt_raw_text(str(port), limit=64)
                for port in value[:32]
                if isinstance(port, (str, int, float))
            ]
        elif key in ("organization", "organization_ids") and isinstance(value, list):
            sanitized[key] = [
                sanitize_node_mgmt_raw_text(str(value_item), limit=64)
                for value_item in value[:64]
                if isinstance(value_item, (str, int, float))
            ]
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            sanitized.pop(key)
    return sanitized
