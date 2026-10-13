"""APM 只读目录查询。组织集合只接受网关注入。"""

import uuid
from dataclasses import replace
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.apm.adapters import TelemetryStoreUnavailable, VictoriaTracesTelemetryStore
from apps.apm.adapters.victoriatraces import _encode_cursor
from apps.apm.models import (
    ApmApplication,
    ApmService,
    ApmServiceInstance,
)
from apps.apm.services.query import MAX_METRIC_WINDOW, DjangoTelemetryQueryService
from apps.apm.services.contracts import ServiceMetricQuery, TraceSearchQuery
from apps.apm.services.trace_access import TraceAccessResolver, collect_visible_page

TRACE_WINDOW = timedelta(hours=1)
_access = TraceAccessResolver()


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
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "items": [serialize(row) for row in queryset[start : start + page_size]],
    }


def list_applications(*, team, page, page_size, keyword):
    ids = team_ids(team)
    if not ids:
        return page_result(ApmApplication.objects.none(), page, page_size, _application_item)
    queryset = (
        ApmApplication.objects.filter(is_builtin=False, organization_links__organization__in=ids)
        .distinct()
        .order_by("application_id", "id")
    )
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(application_id__icontains=keyword))
    return page_result(queryset, page, page_size, _application_item)


def list_services(*, team, page, page_size, keyword, application_id=""):
    ids = team_ids(team)
    if not ids:
        return page_result(ApmService.objects.none(), page, page_size, _service_item)
    queryset = (
        ApmService.objects.filter(organization_links__organization__in=ids)
        .select_related("application")
        .distinct()
        .order_by("normalized_name", "id")
    )
    if application_id:
        queryset = queryset.filter(application__application_id=application_id)
    if keyword:
        queryset = queryset.filter(name__icontains=keyword)
    return page_result(queryset, page, page_size, _service_item)


def list_instances(*, team, page, page_size, keyword, application_id=""):
    ids = team_ids(team)
    if not ids:
        return page_result(ApmServiceInstance.objects.none(), page, page_size, _instance_item)
    queryset = (
        ApmServiceInstance.objects.filter(organization_links__organization__in=ids)
        .select_related("service__application")
        .distinct()
        .order_by("normalized_instance_id", "id")
    )
    if application_id:
        queryset = queryset.filter(service__application__application_id=application_id)
    if keyword:
        queryset = queryset.filter(instance_id__icontains=keyword)
    return page_result(queryset, page, page_size, _instance_item)


def _application_item(obj):
    return {
        "id": str(obj.id),
        "application_id": obj.application_id,
        "name": obj.name,
        "description": obj.description,
    }


def _service_item(obj):
    application = obj.application
    return {
        "id": str(obj.id),
        "name": obj.name,
        "namespace": obj.namespace,
        "application_id": application.application_id if application else "",
        "language": obj.language,
        "archived": obj.archived_at is not None,
    }


def _instance_item(obj):
    return {
        "id": str(obj.id),
        "instance_id": obj.instance_id,
        "service_id": str(obj.service_id),
        "environment": obj.environment,
        "version": obj.version,
    }


def query_service_metrics(*, team, service_id, start, end, environment=""):
    start, end = _aware(start), _aware(end)
    if end <= start:
        return {"result": False, "message": "开始时间必须早于结束时间"}
    if end - start > MAX_METRIC_WINDOW:
        return {"result": False, "message": "查询时间范围不能超过 7 天"}
    service = _owned_service(team, service_id)
    if service is None:
        return {"result": False, "message": "服务不存在"}
    query = ServiceMetricQuery(
        service_namespace=service.namespace,
        service_name=service.name,
        environment=environment or "",
        started_at=start,
        ended_at=end,
        include_breakdown=False,
    )
    try:
        red = _telemetry().service_red(query)
    except TelemetryStoreUnavailable:
        return {"result": False, "message": "服务指标暂不可用"}
    except ValueError as exc:
        return {"result": False, "message": str(exc)}
    return {
        "service_id": str(service.id),
        "environment": environment or "",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "request_rate": red.request_rate,
        "error_rate": red.error_rate,
        "p95_ms": red.p95_ms,
        "p99_ms": red.p99_ms,
        "request_count": red.request_count,
        "error_count": red.error_count,
        "timeseries": [
            {
                "timestamp": point.timestamp.isoformat(),
                "request_rate": point.request_rate,
                "error_rate": point.error_rate,
                "p95_ms": point.p95_ms,
                "p99_ms": point.p99_ms,
            }
            for point in red.timeseries
        ],
    }


def list_traces(*, team, start, end, service_id="", status=None, limit=20, cursor=""):
    start, end = _aware(start), _aware(end)
    if end <= start:
        return {"result": False, "message": "开始时间必须早于结束时间"}
    if end - start > TRACE_WINDOW:
        return {"result": False, "message": "查询时间范围不能超过 1 小时"}
    ids = team_ids(team)
    if not ids:
        return {"items": [], "next_cursor": None}
    service_name = None
    service_namespace = None
    if service_id:
        service = _owned_service(team, service_id)
        if service is None:
            return {"result": False, "message": "服务不存在"}
        service_name = service.name
        service_namespace = service.namespace
    query = TraceSearchQuery(
        started_at=start,
        ended_at=end,
        service_namespace=service_namespace,
        service_name=service_name,
        status=status,
        cursor=cursor or None,
        limit=limit,
    )
    query_service = _telemetry()

    def fetch_page(page_cursor):
        page = query_service.search_traces(replace(query, cursor=page_cursor))
        return page.items, page.next_cursor

    try:
        visible, next_cursor = collect_visible_page(
            fetch_page=fetch_page,
            filter_items=lambda items: _access.filter_summaries(items, ids),
            cursor=query.cursor,
            limit=limit,
            encode_cursor=lambda item: _encode_cursor(item.started_at, item.trace_id),
        )
    except TelemetryStoreUnavailable:
        return {"result": False, "message": "调用数据暂不可用"}
    except ValueError as exc:
        return {"result": False, "message": str(exc)}
    return {"items": [_trace_item(item) for item in visible], "next_cursor": next_cursor}


def get_trace(*, team, trace_id):
    ids = team_ids(team)
    if not ids:
        return {"result": False, "message": "调用不存在"}
    try:
        detail = _telemetry().get_trace(trace_id.lower())
    except TelemetryStoreUnavailable:
        return {"result": False, "message": "调用数据暂不可用"}
    if detail is None:
        return {"result": False, "message": "调用不存在"}
    visible = _access.filter_detail(detail, ids)
    if visible is None:
        return {"result": False, "message": "调用不存在"}
    return {
        "trace_id": visible.trace_id,
        "service_name": visible.service_name,
        "truncated": visible.truncated,
        "spans": [_span_item(span) for span in visible.spans],
    }


def _telemetry():
    store = VictoriaTracesTelemetryStore()
    return DjangoTelemetryQueryService(metric_store=store, trace_store=store)


def _owned_service(team, service_id):
    ids = team_ids(team)
    if not ids or not service_id:
        return None
    try:
        parsed = uuid.UUID(str(service_id))
    except ValueError:
        return None
    return (
        ApmService.objects.filter(id=parsed, organization_links__organization__in=ids)
        .distinct()
        .first()
    )


def _trace_item(item):
    return {
        "trace_id": item.trace_id,
        "started_at": item.started_at.isoformat(),
        "duration_ms": item.duration_ms,
        "service_name": item.service_name,
        "environment": item.environment,
        "status": item.status,
        "root_span_name": item.root_span_name,
        "span_count": item.span_count,
    }


def _span_item(span):
    return {
        "span_id": span.span_id,
        "parent_span_id": span.parent_span_id,
        "name": span.name,
        "started_at": span.started_at.isoformat(),
        "duration_ms": span.duration_ms,
        "status": span.status,
        "kind": span.kind,
        "service_name": span.service_name,
        "attributes": dict(span.attributes),
    }


def _aware(value):
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.utc)
    return value
