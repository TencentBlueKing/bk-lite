"""监控只读目录查询。组织集合只接受网关注入，不读请求里的组织字段。"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.monitor.filters.monitor_policy import exclude_policy_group_rules
from apps.monitor.models import Metric, MonitorInstance, MonitorObject, MonitorPolicy, PolicyOrganization
from apps.monitor.services.authorized_metric_query import AuthorizedMetricQueryError, _build_query
from apps.monitor.services.metrics import Metrics, MetricsQueryBudgetExceeded

METRIC_RANGE_WINDOW = timedelta(hours=6)


def team_ids(team):
    ids = []
    for item in team or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0:
            ids.append(value)
    return ids


def page_result(queryset, page, page_size, serialize):
    total = queryset.count()
    start = (page - 1) * page_size
    rows = list(queryset[start : start + page_size])
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "items": [serialize(row) for row in rows],
    }


def list_objects(*, team, page, page_size, keyword):
    if not team_ids(team):
        return page_result(MonitorObject.objects.none(), page, page_size, _object_item)
    queryset = MonitorObject.objects.filter(is_visible=True).order_by("order", "id")
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(display_name__icontains=keyword))
    return page_result(queryset, page, page_size, _object_item)


def list_instances(*, team, page, page_size, keyword, monitor_object_id=None):
    ids = team_ids(team)
    if not ids:
        return page_result(MonitorInstance.objects.none(), page, page_size, _instance_item)
    queryset = (
        MonitorInstance.objects.filter(is_deleted=False, monitorinstanceorganization__organization__in=ids)
        .distinct()
        .order_by("id")
    )
    if monitor_object_id:
        queryset = queryset.filter(monitor_object_id=monitor_object_id)
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(ip__icontains=keyword))
    return page_result(queryset, page, page_size, _instance_item)


def list_policies(*, team, page, page_size, keyword, monitor_object_id=None):
    ids = team_ids(team)
    if not ids:
        return page_result(MonitorPolicy.objects.none(), page, page_size, _policy_item)
    owned = PolicyOrganization.objects.filter(organization__in=ids).values("policy_id")
    queryset = exclude_policy_group_rules(MonitorPolicy.objects.filter(id__in=owned)).order_by("id")
    if monitor_object_id:
        queryset = queryset.filter(monitor_object_id=monitor_object_id)
    if keyword:
        queryset = queryset.filter(name__icontains=keyword)
    return page_result(queryset, page, page_size, _policy_item)


def _object_item(obj):
    return {
        "id": obj.id,
        "name": obj.name,
        "display_name": obj.display_name,
        "type": obj.type_id,
        "level": obj.level,
        "parent_id": obj.parent_id,
        "description": obj.description,
    }


def _instance_item(obj):
    return {
        "id": obj.id,
        "name": obj.name,
        "monitor_object_id": obj.monitor_object_id,
        "ip": obj.ip,
        "is_active": obj.is_active,
        "node_id": obj.node_id,
        "cmdb_id": obj.cmdb_id,
        "cloud_region_id": obj.cloud_region_id,
    }


def _policy_item(obj):
    return {
        "id": obj.id,
        "name": obj.name,
        "monitor_object_id": obj.monitor_object_id,
        "alert_name": obj.alert_name,
        "enable": obj.enable,
        "collect_type": obj.collect_type,
    }


def list_metrics(*, team, page, page_size, keyword, monitor_object_id):
    if not team_ids(team):
        return page_result(Metric.objects.none(), page, page_size, _metric_item)
    if not MonitorObject.objects.filter(id=monitor_object_id, is_visible=True).exists():
        return {"result": False, "message": "监控对象不存在"}
    queryset = Metric.objects.filter(monitor_object_id=monitor_object_id).order_by("sort_order", "id")
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(display_name__icontains=keyword))
    return page_result(queryset, page, page_size, _metric_item)


def query_metric_instant(*, team, instance_id, metric_id):
    prepared = _prepare_metric_query(team, instance_id, metric_id)
    if prepared.get("result") is False:
        return prepared
    try:
        query, _applied = Metrics.apply_card_series_limit(prepared["query"])
        payload = Metrics.get_metrics(query)
    except (AuthorizedMetricQueryError, MetricsQueryBudgetExceeded) as exc:
        return {"result": False, "message": str(exc)}
    except Exception:
        return {"result": False, "message": "指标查询失败"}
    projected = _project_metric_payload(payload, ranged=False)
    if projected.get("result") is False:
        return projected
    return {
        "metric_id": prepared["metric"].id,
        "instance_id": prepared["instance"].id,
        "unit": prepared["metric"].unit,
        **projected,
    }


def query_metric_range(*, team, instance_id, metric_id, start, end, step="5m"):
    start, end = _aware(start), _aware(end)
    if end <= start:
        return {"result": False, "message": "开始时间必须早于结束时间"}
    if end - start > METRIC_RANGE_WINDOW:
        return {"result": False, "message": "查询时间范围不能超过 6 小时"}
    try:
        Metrics.parse_step_to_seconds(step)
    except ValueError:
        return {"result": False, "message": "查询步长无效"}
    prepared = _prepare_metric_query(team, instance_id, metric_id)
    if prepared.get("result") is False:
        return prepared
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    try:
        payload = Metrics.get_metrics_range(
            prepared["query"],
            start_ms,
            end_ms,
            step,
            card_budget=True,
        )
    except (AuthorizedMetricQueryError, MetricsQueryBudgetExceeded) as exc:
        return {"result": False, "message": str(exc)}
    except Exception:
        return {"result": False, "message": "指标查询失败"}
    projected = _project_metric_payload(payload, ranged=True)
    if projected.get("result") is False:
        return projected
    return {
        "metric_id": prepared["metric"].id,
        "instance_id": prepared["instance"].id,
        "unit": prepared["metric"].unit,
        "start": start.isoformat(),
        "end": end.isoformat(),
        **projected,
    }


def _prepare_metric_query(team, instance_id, metric_id):
    ids = team_ids(team)
    instance = (
        MonitorInstance.objects.filter(
            id=instance_id,
            is_deleted=False,
            monitorinstanceorganization__organization__in=ids,
        )
        .distinct()
        .first()
        if ids
        else None
    )
    if instance is None:
        return {"result": False, "message": "监控实例不存在"}
    metric = Metric.objects.filter(id=metric_id, monitor_object_id=instance.monitor_object_id).first()
    if metric is None:
        return {"result": False, "message": "监控指标不存在"}
    try:
        query = _build_query(metric, (instance.id,), None, "AVG")
    except AuthorizedMetricQueryError as exc:
        return {"result": False, "message": str(exc)}
    return {"metric": metric, "instance": instance, "query": query}


def _project_metric_payload(payload, *, ranged):
    if not isinstance(payload, dict) or payload.get("status") not in (None, "success"):
        return {"result": False, "message": "指标查询失败"}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    series = []
    for item in data.get("result") or []:
        if not isinstance(item, dict):
            continue
        labels = item.get("metric") if isinstance(item.get("metric"), dict) else {}
        clean = {str(key): value for key, value in labels.items() if not str(key).startswith("__")}
        if ranged:
            points = [
                {"timestamp": pair[0], "value": pair[1]}
                for pair in item.get("values") or []
                if isinstance(pair, (list, tuple)) and len(pair) >= 2
            ]
            series.append({"labels": clean, "points": points})
        else:
            value = item.get("value")
            point = None
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                point = {"timestamp": value[0], "value": value[1]}
            series.append({"labels": clean, "point": point})
    budget = data.get("series_budget") if isinstance(data.get("series_budget"), dict) else {}
    return {"series": series, "truncated": bool(budget.get("truncated"))}


def _metric_item(obj):
    names = []
    for item in obj.dimensions or []:
        raw = item.get("name") if isinstance(item, dict) else item
        if raw not in (None, ""):
            names.append(str(raw))
    return {
        "id": obj.id,
        "name": obj.name,
        "display_name": obj.display_name,
        "unit": obj.unit,
        "dimensions": names,
        "description": obj.description or "",
    }


def _aware(value):
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.utc)
    return value
