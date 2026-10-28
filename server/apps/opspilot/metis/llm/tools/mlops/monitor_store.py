"""按 execution_id 记住本轮成功的监控时序查询，供预测工具读取原始点。"""

import threading
from typing import Any, Optional

from django.core.cache import cache

from apps.core.logger import opspilot_logger as logger

_LOCK = threading.Lock()
_CACHE_SECONDS = 30 * 60
_MAX_ENTRIES = 20
_MEMORY: dict[str, list] = {}


def _cache_key(execution_id: str) -> str:
    return f"opspilot:monitor_metric_query:{execution_id}"


def execution_id_from_config(config: Optional[dict]) -> str:
    if not isinstance(config, dict):
        return ""
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        configurable = config
    execution_id = configurable.get("execution_id") or configurable.get("thread_id")
    if execution_id in (None, ""):
        request = configurable.get("graph_request")
        extra = getattr(request, "extra_config", None) if request is not None else None
        if isinstance(extra, dict):
            execution_id = extra.get("execution_id") or extra.get("thread_id")
    if execution_id in (None, ""):
        return ""
    return str(execution_id)


def record_monitor_metric_query(
    config: Optional[dict],
    metric: str,
    instance_ids: Any,
    payload: Any,
    monitor_obj_id: str = "",
) -> None:
    execution_id = execution_id_from_config(config)
    metric_name = str(metric or "").strip()
    if not execution_id or not metric_name or not isinstance(payload, dict):
        return
    if payload.get("result") is False or payload.get("success") is False:
        return
    entry = {
        "metric": metric_name,
        "instance_ids": list(instance_ids or []),
        "monitor_obj_id": str(monitor_obj_id or ""),
        "payload": payload,
    }
    key = _cache_key(execution_id)
    try:
        with _LOCK:
            current = list(_MEMORY.get(key) or [])
            current.append(entry)
            trimmed = current[-_MAX_ENTRIES:]
            _MEMORY[key] = trimmed
            if len(_MEMORY) > 200:
                _MEMORY.pop(next(iter(_MEMORY)), None)
            cache.set(key, trimmed, _CACHE_SECONDS)
    except Exception as exc:
        logger.debug(
            "event=monitor_metric_query_cache_failed execution_id=%s error_type=%s",
            execution_id,
            type(exc).__name__,
        )


def _stored_entries(execution_id: str) -> list:
    if not execution_id:
        return []
    key = _cache_key(execution_id)
    current = _MEMORY.get(key)
    if not isinstance(current, list):
        current = cache.get(key) or []
    return current if isinstance(current, list) else []


def cached_monitor_metrics(execution_id: str) -> list[str]:
    """本轮已成功记下的指标名，最近一次在前。"""
    names: list[str] = []
    seen: set[str] = set()
    for entry in reversed(_stored_entries(execution_id)):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("metric") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def latest_monitor_metric_query(execution_id: str, metric: str) -> Optional[dict]:
    metric_name = str(metric or "").strip()
    if not execution_id or not metric_name:
        return None
    for entry in reversed(_stored_entries(execution_id)):
        if isinstance(entry, dict) and entry.get("metric") == metric_name:
            return entry
    return None
