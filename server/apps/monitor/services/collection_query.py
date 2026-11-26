"""监控实例采集查询。一行一台，插件状态收成上报、采集状态和采集方式。"""

from __future__ import annotations

import re
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from apps.core.logger import monitor_logger as logger
from apps.monitor.models.collect_config import CollectConfig
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.active_alert_ranking import format_active_alert_local_time
from apps.monitor.services.generic_query import GenericQueryError, _checked_sort, _optional_page, _table
from apps.monitor.services.generic_query_limits import INSTANCE_LIST_MAX
from apps.monitor.services.instance_distribution import _object_labels, _type_labels
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.query_deadline import past_deadline, resolve_nats_deadline
from apps.monitor.utils.instance import list_reporting_status
from apps.monitor.utils.last_sample import last_sample_timestamp_query, last_sample_unix_seconds
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.monitor.utils.vm_query_batch import run_unique_vm_queries

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

# 单条状态查询的标签匹配串上限。超出后按实例拆开，避免把全部实例拼进一条正则。
_MATCHER_BUDGET = 8000
_VM_READ_TIMEOUT_SECONDS = 15.0
_SELECTOR_RE = re.compile(r"\{([^{}]*)\}")
_VM_MISS = object()
_DEADLINE = object()

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
    deadline=None,
):
    report_code = _choice(report_status, {REPORT_STATUS_ALL, REPORT_STATUS_NORMAL, REPORT_STATUS_UNAVAILABLE}, "上报状态")
    collect_code = _choice(collect_status, {COLLECT_STATUS_ALL, COLLECT_STATUS_NORMAL, COLLECT_STATUS_OFFLINE}, "采集状态")
    mode_code = _choice(collect_mode, {COLLECT_MODE_ALL, COLLECT_MODE_AUTO, COLLECT_MODE_MANUAL}, "采集方式")
    requested_sort = _checked_sort(order_by, order_dir, {SORT_LAST_SAMPLE})
    scoped = list(instances)
    if mode_code != COLLECT_MODE_ALL:
        scoped = _filter_mode(scoped, mode_code)
    needs_status = report_code != REPORT_STATUS_ALL or collect_code != COLLECT_STATUS_ALL or requested_sort is not None
    vm = vm_api or VictoriaMetricsAPI()
    read_deadline = resolve_nats_deadline(deadline)
    if needs_status:
        rows = _rolled_rows(scoped, locale=locale, vm_api=vm, deadline=read_deadline)
        if report_code != REPORT_STATUS_ALL:
            rows = [row for row in rows if row["report_status"] == report_code]
        if collect_code != COLLECT_STATUS_ALL:
            rows = [row for row in rows if row["collect_status"] == collect_code]
        rows.sort(key=lambda row: _sort_key(row, requested_sort))
        labeled = [_public_row(row) for row in rows]
        return _page(labeled, page, page_size, bounded=bounded)
    ordered = sorted(scoped, key=_instance_name_key)
    total = len(ordered)
    paging = _optional_page(page, page_size)
    if paging is None:
        if bounded and total > INSTANCE_LIST_MAX:
            raise GenericQueryError(f"实例超过 {INSTANCE_LIST_MAX} 条，请缩小范围或填写分页")
        visible = ordered
    else:
        page_no, size = paging
        start = (page_no - 1) * size
        visible = ordered[start : start + size]
    rows = _rolled_rows(visible, locale=locale, vm_api=vm, deadline=read_deadline, plugin_population=ordered)
    rows.sort(key=lambda row: _sort_key(row, None))
    labeled = [_public_row(row) for row in rows]
    if paging is None:
        return labeled
    return _table(labeled, total, page_no, size)


def query_collection_count(
    instances,
    *,
    report_status=None,
    collect_status=None,
    collect_mode=None,
    vm_api=None,
    deadline=None,
) -> int:
    """范围内的实例数。过滤条件与列表相同，不组装对外明细。"""
    report_code = _choice(report_status, {REPORT_STATUS_ALL, REPORT_STATUS_NORMAL, REPORT_STATUS_UNAVAILABLE}, "上报状态")
    collect_code = _choice(collect_status, {COLLECT_STATUS_ALL, COLLECT_STATUS_NORMAL, COLLECT_STATUS_OFFLINE}, "采集状态")
    mode_code = _choice(collect_mode, {COLLECT_MODE_ALL, COLLECT_MODE_AUTO, COLLECT_MODE_MANUAL}, "采集方式")
    needs_status = report_code != REPORT_STATUS_ALL or collect_code != COLLECT_STATUS_ALL
    needs_mode = mode_code != COLLECT_MODE_ALL
    if not needs_status and not needs_mode:
        if isinstance(instances, list):
            return len(instances)
        return instances.count()
    materialized = instances if isinstance(instances, list) else list(instances.select_related("monitor_object", "monitor_object__type"))
    if needs_mode:
        materialized = _filter_mode(materialized, mode_code)
    if not needs_status:
        return len(materialized)
    rows = _rolled_rows(
        materialized,
        locale=None,
        vm_api=vm_api or VictoriaMetricsAPI(),
        deadline=resolve_nats_deadline(deadline),
        with_labels=False,
    )
    if report_code != REPORT_STATUS_ALL:
        rows = [row for row in rows if row["report_status"] == report_code]
    if collect_code != COLLECT_STATUS_ALL:
        rows = [row for row in rows if row["collect_status"] == collect_code]
    return len(rows)


def _choice(value, allowed: set[str], label: str) -> str:
    if value in (None, ""):
        return "all"
    text = str(value).strip()
    if text not in allowed:
        raise GenericQueryError(f"{label}不受支持")
    return text


def _instance_name_key(instance):
    name = instance.name or ""
    return (name.casefold(), name, instance.id)


def _filter_mode(instances, mode_code):
    if not instances:
        return []
    plugins_by_object = _plugins_by_object(_object_ids(instances))
    configured = _configured_plugin_ids(instances, plugins_by_object)
    kept = []
    for instance in instances:
        mode = COLLECT_MODE_AUTO if configured.get(instance.id) else COLLECT_MODE_MANUAL
        if mode == mode_code:
            kept.append(instance)
    return kept


def _object_ids(instances) -> list:
    ids = []
    seen = set()
    for instance in instances:
        object_id = _instance_object_id(instance)
        if object_id is not None and object_id not in seen:
            seen.add(object_id)
            ids.append(object_id)
    return ids


def _rolled_rows(instances, *, locale, vm_api, deadline, with_labels=True, plugin_population=None) -> list[dict]:
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
    if with_labels:
        object_labels = _object_labels(objects, locale)
        type_labels = _type_labels(types, locale)
    else:
        object_labels = {}
        type_labels = {}
    population = list(instances if plugin_population is None else plugin_population)
    plugins_by_object = _plugins_by_object(_object_ids(population))
    configured = _configured_plugin_ids(instances, plugins_by_object)
    report_maps = _report_maps(instances, plugins_by_object, vm_api, configured, deadline, population)
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


def _plugin_status_query(plugin) -> str:
    """原生插件的状态不算脚本序列。脚本插件的状态查询本身只看自己的模板。"""
    from apps.monitor.services.script_attach import is_script_plugin
    from apps.monitor.utils.script_series_isolation import exclude_script_series

    query = (plugin.status_query or "").strip()
    if query and not is_script_plugin(plugin):
        return exclude_script_series(query)
    return query


def _report_maps(instances, plugins_by_object, vm_api, configured, deadline, population=None) -> dict[tuple, dict[str, float]]:
    """没人配置的插件不再查询。选择器只含这次要出结果的实例。

    手动实例能搭乘的插件，只来自本次请求已经授权并过滤后的实例，不到库里再找同对象的其他实例。
    失联仍是已配置插件减去有上报的插件。最后采样时间不再计入没配给这台机器的插件。
    """
    if past_deadline(deadline):
        logger.warning("event=collection_query_deadline_exceeded")
        raise GenericQueryError("采集查询超时")
    if population is None:
        population = instances
    keys_by_object = {}
    for instance in instances:
        monitor_object = instance.monitor_object
        if monitor_object is not None:
            keys_by_object[monitor_object.id] = tuple(monitor_object.instance_id_keys or [])
    manual_by_object = defaultdict(list)
    for instance in instances:
        object_id = _instance_object_id(instance)
        if object_id is not None and not configured.get(instance.id):
            manual_by_object[object_id].append(instance)
    in_use = _plugin_ids_in_use(population, plugins_by_object) if manual_by_object else {}

    maps = {}
    groups = {}
    for object_id, plugins in plugins_by_object.items():
        keys = keys_by_object.get(object_id, ())
        object_instances = [instance for instance in instances if _instance_object_id(instance) == object_id]
        for plugin in plugins:
            query = _plugin_status_query(plugin)
            needed = [instance for instance in object_instances if plugin.id in configured.get(instance.id, set())]
            plugin_active = bool(needed) or plugin.id in in_use.get(object_id, set())
            if not query or not keys or not plugin_active:
                maps[(object_id, plugin.id)] = {}
                continue
            allowed = {instance.id for instance in needed}
            for instance in manual_by_object.get(object_id, []):
                if instance.id not in allowed:
                    needed.append(instance)
                    allowed.add(instance.id)
            if not needed:
                maps[(object_id, plugin.id)] = {}
                continue
            group = groups.setdefault((query, keys), {"instances": {}, "plugins": [], "plugin_id": plugin.id})
            for instance in needed:
                group["instances"][instance.id] = instance
            group["plugins"].append((object_id, plugin.id, allowed))

    jobs = []
    job_groups = []
    plugin_id_by_job = {}
    for (query, keys), group in groups.items():
        targets = list(group["instances"].values())
        scoped_queries = _scoped_status_queries(query, keys, targets)
        if not scoped_queries:
            logger.warning(
                "event=collection_status_query_unscoped plugin_id=%s reason=%s failed_stage=%s error_type=%s",
                group["plugin_id"],
                _unscopeable_reason(query, keys, targets),
                "status_query_scope",
                "UnscopeableStatusQuery",
            )
            continue
        for scoped in scoped_queries:
            jobs.append(scoped)
            job_groups.append((query, keys))
            plugin_id_by_job.setdefault(scoped, group["plugin_id"])

    aborted = threading.Event()

    def fetch(scoped):
        if aborted.is_set() or past_deadline(deadline):
            aborted.set()
            return _DEADLINE
        remaining = None if deadline is None else deadline - time.monotonic()
        try:
            return _read_status(vm_api, last_sample_timestamp_query(scoped), remaining)
        except Exception as exc:
            if past_deadline(deadline):
                aborted.set()
                return _DEADLINE
            logger.exception(
                "event=collection_plugin_status_failed plugin_id=%s error_type=%s",
                plugin_id_by_job.get(scoped),
                type(exc).__name__,
            )
            return _VM_MISS

    payloads, _errors = run_unique_vm_queries(jobs, fetch)
    if aborted.is_set():
        logger.warning("event=collection_query_deadline_exceeded")
        raise GenericQueryError("采集查询超时")
    merged: dict[tuple, dict[str, float]] = {}
    failed = set()
    for scoped, key in zip(jobs, job_groups):
        payload = payloads.get(scoped, _VM_MISS)
        if payload is _VM_MISS:
            failed.add(key)
            continue
        found = merged.setdefault(key, {})
        for instance_id, stamp in _plugin_reports_from_payload(payload, key[1]).items():
            current = found.get(instance_id)
            if current is None or stamp > current:
                found[instance_id] = stamp

    for key, group in groups.items():
        found = {} if key in failed else merged.get(key, {})
        for object_id, plugin_id, allowed in group["plugins"]:
            maps[(object_id, plugin_id)] = {instance_id: stamp for instance_id, stamp in found.items() if instance_id in allowed}
    return maps


def _instance_object_id(instance):
    object_id = getattr(instance, "monitor_object_id", None)
    if object_id is None and instance.monitor_object is not None:
        return instance.monitor_object.id
    return object_id


def _read_timeout(remaining):
    if remaining is None:
        return _VM_READ_TIMEOUT_SECONDS
    return min(_VM_READ_TIMEOUT_SECONDS, max(float(remaining), 0.001))


def _read_status(vm_api, promql, remaining=None):
    if type(vm_api) is VictoriaMetricsAPI:
        timeout = _read_timeout(remaining)
        if len(promql) > 3000:
            return vm_api.query_form(promql, step="20m", timeout=timeout)
        return vm_api.query(promql, step="20m", timeout=timeout)
    if len(promql) > 3000 and hasattr(vm_api, "query_form"):
        return vm_api.query_form(promql, step="20m")
    return vm_api.query(promql, step="20m")


def _scoped_status_queries(query: str, keys: tuple[str, ...], instances) -> list[str]:
    scoped_instances = [instance for instance in instances if _identity(instance, keys) is not None]
    if not scoped_instances or not _SELECTOR_RE.search(query):
        return []
    narrowed = []
    for chunk in _chunk_instances(keys, scoped_instances, _MATCHER_BUDGET):
        rewritten = _rewrite_selector(query, keys, chunk)
        if rewritten and rewritten != query:
            narrowed.append(rewritten)
    return narrowed


def _unscopeable_reason(query: str, keys: tuple[str, ...], instances) -> str:
    if not _SELECTOR_RE.search(query):
        return "no_selector"
    if not any(_identity(instance, keys) is not None for instance in instances):
        return "no_identity"
    return "not_narrowed"


def _plugin_ids_in_use(population, plugins_by_object) -> dict:
    configured = _configured_plugin_ids(population, plugins_by_object)
    in_use = defaultdict(set)
    for instance in population:
        object_id = _instance_object_id(instance)
        if object_id is None:
            continue
        in_use[object_id].update(configured.get(instance.id, ()))
    return in_use


def _identity(instance, keys: tuple[str, ...]):
    parsed = parse_instance_id(instance.id)
    if len(parsed) < len(keys):
        return None
    values = tuple(parsed[index] for index in range(len(keys)))
    if any(value in (None, "") for value in values):
        return None
    return tuple(str(value) for value in values)


def _chunk_instances(keys: tuple[str, ...], instances, budget: int) -> list[list]:
    chunks = []
    current = []
    for instance in instances:
        trial = current + [instance]
        if current and _matcher_length(keys, trial) > budget:
            chunks.append(current)
            current = [instance]
        else:
            current = trial
    if current:
        chunks.append(current)
    return chunks


def _matcher_length(keys: tuple[str, ...], instances) -> int:
    return len(_matchers(keys, instances))


def _matchers(keys: tuple[str, ...], instances) -> str:
    values_by_key = {key: set() for key in keys}
    for instance in instances:
        for key, value in zip(keys, _identity(instance, keys)):
            values_by_key[key].add(value)
    parts = []
    for key in keys:
        pattern = "|".join(re.escape(value) for value in sorted(values_by_key[key]))
        quoted = pattern.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'{key}=~"{quoted}"')
    return ",".join(parts)


def _rewrite_selector(query: str, keys: tuple[str, ...], instances) -> str:
    matcher = _matchers(keys, instances)
    if not matcher:
        return query

    def replace(match):
        body = match.group(1).strip()
        if not body:
            return "{" + matcher + "}"
        return "{" + matcher + "," + body + "}"

    return _SELECTOR_RE.sub(replace, query)


def _plugin_reports_from_payload(payload, instance_id_keys: tuple[str, ...]) -> dict[str, float]:
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
