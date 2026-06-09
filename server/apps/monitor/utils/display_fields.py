from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models.monitor_metrics import Metric


def validate_display_fields(monitor_object, display_fields):
    """校验 display_fields 结构与指标存在性，返回规整后的列表。"""
    if not isinstance(display_fields, list):
        raise BaseAppException("display_fields must be a list")

    existing = {
        (m["monitor_plugin__name"], m["name"])
        for m in Metric.objects.filter(monitor_object=monitor_object).values("monitor_plugin__name", "name")
    }

    normalized = []
    for idx, col in enumerate(display_fields):
        if not isinstance(col, dict):
            raise BaseAppException("each display field must be an object")
        name = (col.get("name") or "").strip()
        if not name:
            raise BaseAppException("display field name is required")
        metrics = col.get("metrics") or []
        if not isinstance(metrics, list) or not metrics:
            raise BaseAppException(f"display field '{name}' requires at least one metric")
        norm_metrics = []
        for binding in metrics:
            if not isinstance(binding, dict):
                raise BaseAppException(f"display field '{name}' has a non-object metric binding")
            plugin = (binding.get("plugin") or "").strip()
            metric = (binding.get("metric") or "").strip()
            if not plugin or not metric:
                raise BaseAppException(f"display field '{name}' has an incomplete metric binding")
            if (plugin, metric) not in existing:
                raise BaseAppException(f"metric not found: {plugin}/{metric}")
            norm_metrics.append({"plugin": plugin, "metric": metric})
        normalized.append({"name": name, "sort_order": col.get("sort_order", idx), "metrics": norm_metrics})

    sorted_cols = sorted(normalized, key=lambda c: c["sort_order"])
    return [{**col, "sort_order": i} for i, col in enumerate(sorted_cols)]
