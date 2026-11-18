"""监控实例采集查询。一行一台，插件状态收成上报、采集状态和采集方式。"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from apps.core.logger import monitor_logger as logger
from apps.monitor.models.collect_config import CollectConfig
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.active_alert_ranking import format_active_alert_local_time
from apps.monitor.services.generic_query import GenericQueryError, _checked_sort, _optional_page, _table
from apps.monitor.services.generic_query_limits import INSTANCE_LIST_MAX
from apps.monitor.services.instance_distribution import _object_labels, _type_labels
from apps.monitor.utils.instance import list_reporting_status
from apps.monitor.utils.last_sample import last_sample_timestamp_query, last_sample_unix_seconds
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI

REPORT_STATUS_ALL = "all"
REPORT_STATUS_NORMAL = "normal"
REPORT_STATUS_UNAVAILABLE = "unavailable"
COLLECT_STATUS_ALL = "all"
COLLECT_STATUS_NORMAL = "normal"
COLLECT_STATUS_OFFLINE = "offline"
COLLECT_MODE_ALL = "all"
COLLECT_MODE_AUTO = "auto"
COLLECT_MODE_MANUAL = "manual"
SORT_LAST_SAMPLE = "last_sample_at"

_REPORT_LABELS = {
    REPORT_STATUS_NORMAL: "正常",
    REPORT_STATUS_UNAVAILABLE: "失联",
}
_COLLECT_STATUS_LABELS = {
    COLLECT_STATUS_NORMAL: "正常",
    COLLECT_STATUS_OFFLINE: "失联",
}
_COLLECT_MODE_LABELS = {
    COLLECT_MODE_AUTO: "自动",
    COLLECT_MODE_MANUAL: "手动",
}


def query_collection_rows(
    instances,
    *,
    report_status=None,
    collect_status=None,
    collect_mode=None,
    order_by=None,
    order_dir=None,
    page=None,
    page_size=None,
    locale=None,
    vm_api=None,
    bounded=True,
):
    report_code = _choice(report_status, {REPORT_STATUS_ALL, REPORT_STATUS_NORMAL, REPORT_STATUS_UNAVAILABLE}, "上报状态")
    collect_code = _choice(collect_status, {COLLECT_STATUS_ALL, COLLECT_STATUS_NORMAL, COLLECT_STATUS_OFFLINE}, "采集状态")
    mode_code = _choice(collect_mode, {COLLECT_MODE_ALL, COLLECT_MODE_AUTO, COLLECT_MODE_MANUAL}, "采集方式")
    requested_sort = _checked_sort(order_by, order_dir, {SORT_LAST_SAMPLE})
    rows = _rolled_rows(list(instances), locale=locale, vm_api=vm_api or VictoriaMetricsAPI())
    if report_code != REPORT_STATUS_ALL:
        rows = [row for row in rows if row["report_status"] == report_code]
    if collect_code != COLLECT_STATUS_ALL:
        rows = [row for row in rows if row["collect_status"] == collect_code]
    if mode_code != COLLECT_MODE_ALL:
        rows = [row for row in rows if row["collect_mode"] == mode_code]
    rows.sort(key=lambda row: _sort_key(row, requested_sort))
    labeled = [_public_row(row) for row in rows]
    return _page(labeled, page, page_size, bounded=bounded)


def _choice(value, allowed: set[str], label: str) -> str:
    if value in (None, ""):
        return "all"
    text = str(value).strip()
    if text not in allowed:
        raise GenericQueryError(f"{label}不受支持")
    return text


def _rolled_rows(instances, *, locale, vm_api) -> list[dict]:
    if not instances:
        return []
    objects = []
    seen_objects = set()
    types = []
    seen_types = set()
    for instance in instances:
        monitor_object = instance.monitor_object
        if monitor_object is None or monitor_object.id in seen_objects:
            continue
        seen_objects.add(monitor_object.id)
        objects.append(monitor_object)
        monitor_type = monitor_object.type
        if monitor_type is not None and monitor_type.id not in seen_types:
            seen_types.add(monitor_type.id)
            types.append(monitor_type)
    object_labels = _object_labels(objects, locale)
    type_labels = _type_labels(types, locale)
    plugins_by_object = _plugins_by_object([item.id for item in objects])
    report_maps = _report_maps(instances, plugins_by_object, vm_api)
    configured = _configured_plugin_ids(instances, plugins_by_object)
    rows = []
    for instance in instances:
        monitor_object = instance.monitor_object
        object_id = getattr(monitor_object, "id", None)
        plugins = plugins_by_object.get(object_id, [])
        configured_ids = configured.get(instance.id, set())
        reported_ids = set()
        timestamps = []
        for plugin in plugins:
            stamp = report_maps.get((object_id, plugin.id), {}).get(instance.id)
            if stamp is None:
                continue
            reported_ids.add(plugin.id)
            timestamps.append(stamp)
        last_sample = max(timestamps) if timestamps else None
        offline = bool(configured_ids - reported_ids)
        object_identity = "" if object_id is None else str(object_id)
        object_key = "" if monitor_object is None else (monitor_object.name or "")
        rows.append(
            {
                "instance_id": instance.id,
                "name": instance.name or "",
                "monitor_object_id": object_identity,
                "monitor_object": object_key,
                "monitor_object_type": type_labels.get(getattr(getattr(monitor_object, "type", None), "id", None), ""),
                "monitor_object_name": object_labels.get(object_id, "") if object_id is not None else "",
                "collect_mode": COLLECT_MODE_AUTO if configured_ids else COLLECT_MODE_MANUAL,
                "report_status": list_reporting_status(last_sample),
                "collect_status": COLLECT_STATUS_OFFLINE if offline else COLLECT_STATUS_NORMAL,
                "last_sample_at": _display_time(last_sample),
                "_last_sample": last_sample,
            }
        )
    return rows


def _plugins_by_object(object_ids: list[int]) -> dict[int, list]:
    grouped = defaultdict(list)
    if not object_ids:
        return grouped
    wanted = set(object_ids)
    plugins = MonitorPlugin.objects.filter(monitor_object__in=object_ids).distinct().prefetch_related("monitor_object")
    for plugin in plugins:
        for monitor_object in plugin.monitor_object.all():
            if monitor_object.id in wanted:
                grouped[monitor_object.id].append(plugin)
    return grouped


def _report_maps(instances, plugins_by_object, vm_api) -> dict[tuple, dict[str, float]]:
    keys_by_object = {}
    for instance in instances:
        monitor_object = instance.monitor_object
        if monitor_object is not None:
            keys_by_object[monitor_object.id] = tuple(monitor_object.instance_id_keys or [])
    cache: dict[tuple, dict[str, float]] = {}
    maps = {}
    for object_id, plugins in plugins_by_object.items():
        keys = keys_by_object.get(object_id, ())
        for plugin in plugins:
            cache_key = ((plugin.status_query or "").strip(), keys)
            if cache_key not in cache:
                cache[cache_key] = _query_plugin_reports(plugin, keys, vm_api)
            maps[(object_id, plugin.id)] = cache[cache_key]
    return maps


def _query_plugin_reports(plugin, instance_id_keys: tuple[str, ...], vm_api) -> dict[str, float]:
    query = (plugin.status_query or "").strip()
    if not query or not instance_id_keys:
        return {}
    try:
        payload = vm_api.query(last_sample_timestamp_query(query), step="20m")
    except Exception as exc:
        logger.exception(
            "event=collection_plugin_status_failed plugin_id=%s error_type=%s",
            plugin.id,
            type(exc).__name__,
        )
        return {}
    found = {}
    for metric in (payload or {}).get("data", {}).get("result", []) or []:
        labels = metric.get("metric") or {}
        instance_id = str(tuple(labels.get(key) for key in instance_id_keys))
        stamp = last_sample_unix_seconds(metric)
        if not instance_id or stamp is None:
            continue
        current = found.get(instance_id)
        if current is None or stamp > current:
            found[instance_id] = stamp
    return found


def _configured_plugin_ids(instances, plugins_by_object) -> dict[str, set[int]]:
    instance_ids = [instance.id for instance in instances]
    object_by_instance = {instance.id: instance.monitor_object_id for instance in instances}
    legacy_counts = Counter()
    legacy_plugin = {}
    for object_id, plugins in plugins_by_object.items():
        for plugin in plugins:
            legacy = (object_id, plugin.collector, plugin.collect_type)
            legacy_counts[legacy] += 1
            legacy_plugin[legacy] = plugin.id
    configured = defaultdict(set)
    configs = CollectConfig.objects.filter(monitor_instance_id__in=instance_ids).values_list(
        "monitor_instance_id",
        "monitor_plugin_id",
        "collector",
        "collect_type",
    )
    for instance_id, plugin_id, collector, collect_type in configs:
        object_id = object_by_instance.get(instance_id)
        object_plugin_ids = {plugin.id for plugin in plugins_by_object.get(object_id, [])}
        if plugin_id and plugin_id in object_plugin_ids:
            configured[instance_id].add(plugin_id)
            continue
        legacy = (object_id, collector, collect_type)
        if legacy_counts[legacy] == 1 and legacy_plugin[legacy] in object_plugin_ids:
            configured[instance_id].add(legacy_plugin[legacy])
    return configured


def _display_time(timestamp: float | None) -> str:
    if timestamp is None:
        return ""
    formatted = format_active_alert_local_time(datetime.fromtimestamp(timestamp, tz=timezone.utc))
    return formatted or ""


def _sort_key(row: dict, requested):
    if requested is None:
        return (row["name"].casefold(), row["name"], row["instance_id"])
    _field, descending = requested
    timestamp = row["_last_sample"]
    if descending:
        return (timestamp is None, -(timestamp or 0), row["name"].casefold(), row["instance_id"])
    return (timestamp is None, timestamp or 0, row["name"].casefold(), row["instance_id"])


def _public_row(row: dict) -> dict:
    return {
        "instance_id": row["instance_id"],
        "name": row["name"],
        "monitor_object_id": row["monitor_object_id"],
        "monitor_object": row["monitor_object"],
        "monitor_object_type": row["monitor_object_type"],
        "monitor_object_name": row["monitor_object_name"],
        "collect_mode": _COLLECT_MODE_LABELS[row["collect_mode"]],
        "report_status": _REPORT_LABELS[row["report_status"]],
        "collect_status": _COLLECT_STATUS_LABELS[row["collect_status"]],
        "last_sample_at": row["last_sample_at"],
    }


def _page(rows: list[dict], page, page_size, *, bounded: bool):
    total = len(rows)
    paging = _optional_page(page, page_size)
    if paging is None:
        if bounded and total > INSTANCE_LIST_MAX:
            raise GenericQueryError(f"实例超过 {INSTANCE_LIST_MAX} 条，请缩小范围或填写分页")
        return rows
    page_no, size = paging
    start = (page_no - 1) * size
    return _table(rows[start : start + size], total, page_no, size)
