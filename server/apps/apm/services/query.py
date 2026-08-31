from datetime import timedelta

from apps.apm.services.contracts import (
    MetricStore,
    ServiceMetricQuery,
    ServiceRed,
    SpanPage,
    SpanSearchQuery,
    TraceDetail,
    TracePage,
    TraceSearchQuery,
    TraceStore,
)
from apps.apm.services.trace_sanitizer import sanitize_trace_detail

MAX_METRIC_WINDOW = timedelta(days=7)
MAX_TRACE_WINDOW = timedelta(days=7)
MAX_TRACE_PAGE_SIZE = 100
_VALID_STATUSES = frozenset({"ok", "error"})
_VALID_KINDS = frozenset({"internal", "server", "client", "producer", "consumer"})


class DjangoTelemetryQueryService:
    """对调用方隐藏查询限制和 MetricStore 的失败语义。"""

    def __init__(self, metric_store: MetricStore | None = None, trace_store: TraceStore | None = None):
        self.metric_store = metric_store
        self.trace_store = trace_store

    def service_red(self, query: ServiceMetricQuery) -> ServiceRed:
        if query.ended_at <= query.started_at:
            raise ValueError("查询结束时间必须晚于开始时间")
        if query.ended_at - query.started_at > MAX_METRIC_WINDOW:
            raise ValueError("RED 查询时间窗不能超过 7 天")
        if not query.service_name.strip():
            raise ValueError("service.name 不能为空")
        if self.metric_store is None:
            raise RuntimeError("MetricStore 未配置")
        return self.metric_store.service_red(query)

    def search_traces(self, query: TraceSearchQuery) -> TracePage:
        self._validate_trace_window(query.started_at, query.ended_at)
        if query.service_name is not None and not query.service_name.strip():
            raise ValueError("service.name 不能为空字符串")
        if query.limit < 1 or query.limit > MAX_TRACE_PAGE_SIZE:
            raise ValueError("Trace 每页数量必须在 1 到 100 之间")
        self._validate_status(query.status)
        self._validate_duration_bounds(query.min_duration_ms, query.max_duration_ms)
        if self.trace_store is None:
            raise RuntimeError("TraceStore 未配置")
        return self.trace_store.search(query)

    def search_spans(self, query: SpanSearchQuery) -> SpanPage:
        self._validate_trace_window(query.started_at, query.ended_at)
        if query.service_name is not None and not query.service_name.strip():
            raise ValueError("service.name 不能为空字符串")
        if query.limit < 1 or query.limit > MAX_TRACE_PAGE_SIZE:
            raise ValueError("Span 每页数量必须在 1 到 100 之间")
        self._validate_status(query.status)
        if query.kind is not None and query.kind not in _VALID_KINDS:
            raise ValueError("Span kind 仅支持 internal、server、client、producer、consumer")
        self._validate_duration_bounds(query.min_duration_ms, query.max_duration_ms)
        if self.trace_store is None:
            raise RuntimeError("TraceStore 未配置")
        return self.trace_store.search_spans(query)

    def get_trace(self, trace_id: str) -> TraceDetail | None:
        if self.trace_store is None:
            raise RuntimeError("TraceStore 未配置")
        detail = self.trace_store.get_trace(trace_id)
        return sanitize_trace_detail(detail) if detail is not None else None

    @staticmethod
    def _validate_trace_window(started_at, ended_at) -> None:
        if ended_at <= started_at:
            raise ValueError("查询结束时间必须晚于开始时间")
        if ended_at - started_at > MAX_TRACE_WINDOW:
            raise ValueError("查询时间窗不能超过 7 天")

    @staticmethod
    def _validate_status(status: str | None) -> None:
        if status is not None and status not in _VALID_STATUSES:
            raise ValueError("status 仅支持 ok 或 error")

    @staticmethod
    def _validate_duration_bounds(min_duration_ms: float | None, max_duration_ms: float | None) -> None:
        if min_duration_ms is not None and min_duration_ms < 0:
            raise ValueError("min_duration_ms 不能为负数")
        if max_duration_ms is not None and max_duration_ms < 0:
            raise ValueError("max_duration_ms 不能为负数")
        if min_duration_ms is not None and max_duration_ms is not None and min_duration_ms > max_duration_ms:
            raise ValueError("min_duration_ms 不能大于 max_duration_ms")
