"""监控视图实例列表：单列全局排序。

流程：校验 ordering →（必要时）只为排序列全量取数 → 内存排序 → 由调用方分页 →
其余展示列仍只补当前页。
"""

from __future__ import annotations

import requests

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.monitor.constants.instance_list_ordering import ORDERING_METRIC_BATCH_SIZE
from apps.monitor.models.collect_config import CollectConfig
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.utils.display_fields import build_display_column_key
from apps.monitor.utils.display_fields_metrics import display_field_key, is_field_display_column


def parse_ordering_params(ordering, order="asc"):
    """解析并校验 ordering / order；无排序时返回 (None, \"asc\")。"""
    key = (ordering or "").strip()
    if not key:
        return None, "asc"
    direction = (order or "asc").strip().lower()
    if direction not in ("asc", "desc"):
        raise ValidationAppException("order must be asc or desc")
    return key, direction


def resolve_ordering_spec(monitor_object_id, display_fields, ordering_key: str):
    """将 ordering 解析为可执行规格；非法键抛 ValidationAppException。

    MVP 白名单：``time`` + 数值/进度类展示指标列（非 Enum、非 field 列）。
    同时接受 ``column_key``（``metric:<digest>``）与主绑定的 ``plugin::metric``。
    """
    if ordering_key == "time":
        return {"kind": "time"}

    allowed = _build_numeric_display_ordering_map(monitor_object_id, display_fields)
    spec = allowed.get(ordering_key)
    if not spec:
        raise ValidationAppException(f"Unsupported ordering: {ordering_key}")
    return spec


def _build_numeric_display_ordering_map(monitor_object_id, display_fields):
    """column_key / display_field_key -> metric 排序规格。"""
    metric_cols = []
    primary_bindings = []
    for col in display_fields or []:
        if is_field_display_column(col if isinstance(col, dict) else {}):
            continue
        metrics = (col.get("metrics") if isinstance(col, dict) else None) or []
        if not metrics:
            continue
        primary = metrics[0] or {}
        plugin = (primary.get("plugin") or "").strip()
        metric_name = (primary.get("metric") or "").strip()
        if not metric_name:
            continue
        metric_cols.append(col)
        primary_bindings.append((plugin, metric_name))

    if not primary_bindings:
        return {}

    metric_rows = (
        Metric.objects.filter(
            monitor_object_id=monitor_object_id,
            name__in=[name for _, name in primary_bindings],
        )
        .select_related("monitor_plugin")
        .all()
    )
    by_plugin = {}
    by_name = {}
    for row in metric_rows:
        plugin_name = row.monitor_plugin.name if row.monitor_plugin_id else ""
        by_plugin[(plugin_name, row.name)] = row
        by_name.setdefault(row.name, row)

    allowed = {}
    for col, (plugin, metric_name) in zip(metric_cols, primary_bindings):
        meta = by_plugin.get((plugin, metric_name)) if plugin else by_name.get(metric_name)
        if not meta:
            continue
        data_type = (meta.data_type or "").strip()
        if data_type.lower() == "enum":
            continue
        spec = {
            "kind": "metric",
            "plugin": plugin,
            "metric": metric_name,
            "metric_obj": meta,
            "out_key": display_field_key(plugin, metric_name),
        }
        column_key = col.get("column_key") if isinstance(col, dict) else None
        if not column_key:
            column_key = build_display_column_key(col)
        allowed[column_key] = spec
        allowed[spec["out_key"]] = spec
        if not plugin and metric_name not in allowed:
            allowed[metric_name] = spec
    return allowed


def apply_ordering_to_instances(
    monitor_object_id,
    obj_metric_map,
    instances: list,
    ordering_key: str | None,
    order: str = "asc",
    *,
    query_metric_values,
):
    """就地排序 instances，返回因排序已写入的展示列 out_key（供本页 fill 跳过）。

    ``query_metric_values(metric_obj, target_instances)`` 由调用方注入（通常为
    MonitorObjectService._query_metric_values），便于单测替换。
    """
    if not ordering_key or not instances:
        return None

    display_fields = obj_metric_map.get("display_fields") or []
    spec = resolve_ordering_spec(monitor_object_id, display_fields, ordering_key)
    filled_out_key = None

    if spec["kind"] == "time":
        _sort_instances(instances, _time_sort_value, order)
        return None

    metric_obj = spec["metric_obj"]
    out_key = spec["out_key"]
    plugin = spec["plugin"]
    eligible = _eligible_instances_for_plugin(instances, plugin)
    try:
        value_map = _query_metric_values_batched(query_metric_values, metric_obj, eligible)
    except requests.Timeout as exc:
        raise BaseAppException("Sorting timed out; try again or refine filters") from exc

    for inst in instances:
        if out_key not in inst or inst.get(out_key) is None:
            raw = value_map.get(inst["instance_id"])
            if raw is not None:
                inst[out_key] = raw

    def metric_sort_value(inst):
        return _numeric_sort_value(inst.get(out_key))

    _sort_instances(instances, metric_sort_value, order)
    filled_out_key = out_key
    return filled_out_key


def _eligible_instances_for_plugin(instances, plugin_name):
    if not plugin_name:
        return instances
    instance_ids = [inst["instance_id"] for inst in instances]
    covered = set(
        CollectConfig.objects.filter(
            monitor_instance_id__in=instance_ids,
            monitor_plugin__name=plugin_name,
        ).values_list("monitor_instance_id", flat=True)
    )
    # 无 CollectConfig 的上报型实例：仍尝试纳入，由 VM 是否返回值决定。
    # 与展示列「有归属才展示」略宽，避免排序时漏掉仅靠上报可见的实例。
    if len(covered) == len(instances):
        return instances
    # 混合场景：有配置的按插件过滤；无任何配置的实例保留给 VM 判定。
    uncovered = [inst for inst in instances if inst["instance_id"] not in covered]
    if not covered:
        return instances
    eligible = [inst for inst in instances if inst["instance_id"] in covered]
    # 把完全没有 CollectConfig 的实例并入（可能是 reported-only）
    has_any_cc = set(CollectConfig.objects.filter(monitor_instance_id__in=instance_ids).values_list("monitor_instance_id", flat=True))
    for inst in uncovered:
        if inst["instance_id"] not in has_any_cc:
            eligible.append(inst)
    return eligible or instances


def _query_metric_values_batched(query_metric_values, metric_obj, instances):
    if not instances:
        return {}
    if len(instances) <= ORDERING_METRIC_BATCH_SIZE:
        return query_metric_values(metric_obj, instances) or {}
    merged = {}
    for start in range(0, len(instances), ORDERING_METRIC_BATCH_SIZE):
        batch = instances[start : start + ORDERING_METRIC_BATCH_SIZE]
        merged.update(query_metric_values(metric_obj, batch) or {})
    return merged


def _time_sort_value(inst):
    raw = inst.get("time")
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _numeric_sort_value(raw):
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict):
        raw = raw.get("value")
        if raw is None or raw == "":
            return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _sort_instances(instances, value_fn, order: str):
    descending = order == "desc"

    def sort_key(inst):
        val = value_fn(inst)
        instance_id = str(inst.get("instance_id") or "")
        if val is None:
            return (1, 0.0, instance_id)
        keyed = -val if descending else val
        return (0, keyed, instance_id)

    instances.sort(key=sort_key)
