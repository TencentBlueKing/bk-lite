"""脚本业务指标定义查询：同时覆盖 stdout 短名与 Telegraf/VM 写出的 name_value 序列。"""

from __future__ import annotations

LABELS = "__$labels__"

# 官方 Prometheus 3.16.0 promtool 实测：默认 or 的向量匹配会排除 __name__
# （engine.go 在 on=false 时把 MetricName 并入 BytesWithoutLabels）。
# 同一组用户标签下 `name or name_value` 只保留左侧一条，不会双序列、不会把值加两次。
# `or ignoring(__name__)` 与默认 or 在这类输入上结果相同；不能用自建「含 __name__ 去重」模型当依据。


def script_business_metric_selector(name: str, suffix: str = "") -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    return f"{text}{suffix}{{{LABELS}}}"


def script_business_metric_query(name: str) -> str:
    """目录名保持短名；查询写入定义，兼容历史 `name` 与采集侧 `name_value`。

    使用默认 PromQL `or`。两侧用户标签相同时左侧优先；仅一侧存在时就用那一侧。
    不在求值路径偷偷改写。
    """
    bare = script_business_metric_selector(name)
    if not bare:
        return ""
    valued = script_business_metric_selector(name, "_value")
    if bare == valued:
        return bare
    return f"({bare} or {valued})"


def _v2_ignoring_name_query(metric_name: str) -> str:
    bare = script_business_metric_selector(metric_name)
    valued = script_business_metric_selector(metric_name, "_value")
    if not bare:
        return ""
    return f"({valued} or ignoring(__name__) {bare})"


def is_legacy_script_business_query(name, query) -> bool:
    """识别可安全改写的裸 name / name_value，以及曾写出的 v2 ignoring 形式。

    不改手写复杂查询。
    """
    text = str(query or "").strip()
    metric_name = str(name or "").strip()
    if not metric_name or not text:
        return False
    bare = script_business_metric_selector(metric_name)
    valued = script_business_metric_selector(metric_name, "_value")
    desired = script_business_metric_query(metric_name)
    if text == desired:
        return False
    return text in {bare, valued, _v2_ignoring_name_query(metric_name)}


def synced_script_business_metric_query(name, query) -> str:
    metric_name = str(name or "").strip()
    text = "" if query is None else str(query).strip()
    if not metric_name:
        return text
    if not text or is_legacy_script_business_query(metric_name, text):
        return script_business_metric_query(metric_name)
    return str(query)


def _iter_script_business_metrics(metric_ids=None):
    from apps.monitor.models import Metric
    from apps.monitor.services.custom_script_plugin import is_script_collect_type, is_script_self_monitor_metric_name

    queryset = Metric.objects.select_related("monitor_plugin")
    if metric_ids is not None:
        queryset = queryset.filter(id__in=list(metric_ids))
    for metric in queryset:
        plugin = metric.monitor_plugin
        collect_type = getattr(plugin, "collect_type", None) if plugin is not None else None
        if not is_script_collect_type(collect_type):
            continue
        if is_script_self_monitor_metric_name(metric.name, collect_type):
            continue
        if not is_legacy_script_business_query(metric.name, metric.query):
            continue
        yield metric, script_business_metric_query(metric.name)


def _snapshot_row(metric, new_query, old_query=None):
    old = metric.query if old_query is None else old_query
    plugin = getattr(metric, "monitor_plugin", None)
    return {
        "id": metric.id,
        "name": metric.name,
        "plugin_id": getattr(plugin, "id", None),
        "old_query": old,
        "new_query": new_query,
    }


def sync_existing_script_business_metric_queries(*, save: bool = False, metric_ids=None, allow_all: bool = False):
    """把已有脚本业务指标定义同步为兼容查询。默认只 dry-run，不写库，不改 TSDB。

    写入必须同时 ``save=True``，并且提供 ``metric_ids``，或在审过 dry-run 后显式 ``allow_all=True``。
    禁止只传 save=True 做全局写入。返回 snapshot 列表，可供 restore 回滚定义（不是文件回滚）。
    """
    if save and metric_ids is None and not allow_all:
        raise ValueError("refusing global definition write: pass metric_ids=... or allow_all=True after a dry-run review")

    changed = []
    for metric, new_query in _iter_script_business_metrics(metric_ids):
        row = _snapshot_row(metric, new_query)
        if save:
            metric.query = new_query
            metric.save(update_fields=["query", "updated_at"])
        changed.append(row)
    return changed


def restore_script_business_metric_queries(snapshot, *, save: bool = False):
    """按 sync 返回的 snapshot 把 Metric.query 还原为 old_query。默认 dry-run，不改 TSDB。"""
    from apps.monitor.models import Metric

    rows = list(snapshot or [])
    ids = [item["id"] for item in rows if item.get("id") is not None]
    by_id = {metric.id: metric for metric in Metric.objects.filter(id__in=ids)}
    planned = []
    for item in rows:
        metric = by_id.get(item.get("id"))
        if metric is None:
            planned.append({**item, "restored": False, "reason": "metric missing"})
            continue
        old_query = item.get("old_query")
        planned.append({**item, "current_query": metric.query, "restored": True})
        if save:
            metric.query = old_query
            metric.save(update_fields=["query", "updated_at"])
    return planned
