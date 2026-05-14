from typing import Any

from apps.core.exceptions.base_app_exception import BaseAppException


MISSING_METRIC_INSTANCE_ID_KEYS_ERROR = "指标未配置有效的 instance_id_keys，无法按实例查询"


def normalize_instance_id_keys(keys: Any) -> list[str]:
    if not isinstance(keys, list):
        return []

    normalized = []
    for key in keys:
        if key is None:
            continue
        key_str = str(key).strip()
        if key_str:
            normalized.append(key_str)
    return normalized


def default_monitor_object_instance_id_keys(level: Any = "base", object_name: Any = "") -> list[str]:
    object_name_str = str(object_name or "").strip()
    if str(level or "").strip() == "derivative" and object_name_str:
        return ["instance_id", object_name_str]
    return ["instance_id"]


def resolve_monitor_object_instance_id_keys(keys: Any, level: Any = "base", object_name: Any = "") -> list[str]:
    normalized = normalize_instance_id_keys(keys)
    if normalized:
        return normalized
    return default_monitor_object_instance_id_keys(level=level, object_name=object_name)


def resolve_metric_instance_id_keys(
    metric_keys: Any,
    monitor_object_keys: Any = None,
    *,
    strict: bool = False,
    error_message: str = MISSING_METRIC_INSTANCE_ID_KEYS_ERROR,
) -> list[str]:
    normalized_metric_keys = normalize_instance_id_keys(metric_keys)
    if normalized_metric_keys:
        return normalized_metric_keys

    normalized_object_keys = normalize_instance_id_keys(monitor_object_keys)
    if normalized_object_keys:
        return normalized_object_keys

    if strict:
        raise BaseAppException(error_message)
    return []
