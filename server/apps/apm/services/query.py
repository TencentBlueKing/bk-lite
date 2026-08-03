from datetime import timedelta

from apps.apm.services.contracts import (
    MetricStore,
    ServiceMetricQuery,
    ServiceRed,
    TraceDetail,
    TracePage,
    TraceSearchQuery,
    TraceStore,
)
from apps.apm.services.trace_sanitizer import sanitize_trace_detail


MAX_METRIC_WINDOW = timedelta(hours=24)
MAX_TRACE_WINDOW = timedelta(days=7)
MAX_TRACE_PAGE_SIZE = 100


class DjangoTelemetryQueryService:
    """对调用方隐藏查询限制和 MetricStore 的失败语义。"""

    def __init__(self, metric_store: MetricStore | None = None, trace_store: TraceStore | None = None):
        self.metric_store = metric_store
        self.trace_store = trace_store

    def service_red(self, query: ServiceMetricQuery) -> ServiceRed:
        if query.ended_at <= query.started_at:
            raise ValueError("查询结束时间必须晚于开始时间")
        if query.ended_at - query.started_at > MAX_METRIC_WINDOW:
            raise ValueError("RED 查询时间窗不能超过 24 小时")
        if not query.service_name.strip():
            raise ValueError("service.name 不能为空")
        if self.metric_store is None:
            raise RuntimeError("MetricStore 未配置")
        return self.metric_store.service_red(query)

    def search_traces(self, query: TraceSearchQuery) -> TracePage:
        if query.ended_at <= query.started_at:
            raise ValueError("查询结束时间必须晚于开始时间")
        if query.ended_at - query.started_at > MAX_TRACE_WINDOW:
            raise ValueError("Trace 查询时间窗不能超过 7 天")
        if not query.service_name or not query.service_name.strip():
            raise ValueError("Trace 查询必须指定 service.name")
        if query.environment is None:
            raise ValueError("Trace 查询必须指定 deployment.environment")
        if query.limit < 1 or query.limit > MAX_TRACE_PAGE_SIZE:
            raise ValueError("Trace 每页数量必须在 1 到 100 之间")
        if self.trace_store is None:
            raise RuntimeError("TraceStore 未配置")
        return self.trace_store.search(query)

    def get_trace(self, trace_id: str) -> TraceDetail | None:
        if self.trace_store is None:
            raise RuntimeError("TraceStore 未配置")
        detail = self.trace_store.get_trace(trace_id)
        return sanitize_trace_detail(detail) if detail is not None else None
