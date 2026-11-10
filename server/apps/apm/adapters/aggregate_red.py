"""入口 RED 与可用性 SLO 的聚合库读取，以及相对 VictoriaTraces 的窗口路由。

慢请求、Apdex、版本、实例和延迟 SLO 仍走 VictoriaTraces。聚合库报错只向上抛，不回退扫明细。
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime

from apps.apm.adapters.errors import TelemetryQueryTooLarge, TelemetryStoreUnavailable
from apps.apm.adapters.victoriatraces import MAX_RED_POINTS, VictoriaTracesTelemetryStore
from apps.apm.services.contracts import (
    MetricDataState,
    ServiceEndpointRed,
    ServiceMetricQuery,
    ServiceRed,
    ServiceRedPoint,
    SloMeasurement,
    SloMetricQuery,
)
from apps.apm.services.trace_retention import trace_retention_block_reason
from apps.core.aggregate_origin import recorded_origin
from apps.core.aggregate_promql import AggregateMetricsTooLarge, AggregateMetricsUnavailable, AggregatePromqlClient
from apps.core.aggregate_promql import align_query_end as align_aggregate_query_end
from apps.core.aggregate_promql import apm_flush_seconds, escape_promql_label_value

ERROR_STATUS = "STATUS_CODE_ERROR"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def align_query_end(ended_at: datetime, *, now: datetime) -> datetime:
    """对齐到最近一个完整分钟，再留出一个 APM 刷出周期。"""

    return align_aggregate_query_end(ended_at, now=now, flush_seconds=apm_flush_seconds())


def _trend_step(window_seconds: int) -> int:
    # 刷出周期内通常只有一个样本。步长小于它时，increase 会把大多数点算成 0。
    return max(apm_flush_seconds(), math.ceil(window_seconds / (MAX_RED_POINTS - 1)))


def _selector(labels: tuple[tuple[str, str], ...]) -> str:
    return ",".join(f'{key}="{escape_promql_label_value(value)}"' for key, value in labels)


def _labels(query: ServiceMetricQuery | SloMetricQuery, *, status_code: str = "") -> tuple[tuple[str, str], ...]:
    # Collector 把空的命名空间和环境写成 unknown，序列标签与之一致。
    labels = [
        ("service_namespace", query.service_namespace or "unknown"),
        ("service_name", query.service_name or "unknown"),
        ("deployment_environment", query.environment or "unknown"),
    ]
    if query.endpoint:
        labels.append(("span_name", query.endpoint))
    if status_code:
        labels.append(("status_code", status_code))
    return tuple(labels)


def _increase(metric: str, labels: tuple[tuple[str, str], ...], window_seconds: int, *, by: str = "") -> str:
    inner = f"increase({metric}{{{_selector(labels)}}}[{window_seconds}s])"
    if by:
        return f"sum by ({by}) ({inner})"
    return f"sum({inner})"


def _quantile(phi: float, labels: tuple[tuple[str, str], ...], window_seconds: int, *, by: str = "le") -> str:
    inner = f"increase(apm_duration_milliseconds_bucket{{{_selector(labels)}}}[{window_seconds}s])"
    return f"histogram_quantile({phi}, sum by ({by}) ({inner}))"


def _number(raw: object) -> float | None:
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _sample(series: dict) -> float | None:
    raw = series.get("value")
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    return _number(raw[1])


def _scalar(result: list[dict]) -> float | None:
    if len(result) != 1:
        return None
    return _sample(result[0])


def _by_label(result: list[dict], label: str) -> dict[str, float]:
    grouped: dict[str, float] = {}
    for series in result:
        metric = series.get("metric")
        if not isinstance(metric, dict):
            continue
        name = str(metric.get(label) or "")
        if not name:
            continue
        value = _sample(series)
        if value is None:
            continue
        grouped[name] = value
    return grouped


def _matrix(result: list[dict]) -> list[tuple[float, float | None]]:
    if not result:
        return []
    values = result[0].get("values")
    if not isinstance(values, list):
        return []
    points: list[tuple[float, float | None]] = []
    for pair in values:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        timestamp = _number(pair[0])
        if timestamp is None:
            continue
        points.append((timestamp, _number(pair[1])))
    return points[-MAX_RED_POINTS:]


class AggregateApmRedStore:
    def __init__(self, client: AggregatePromqlClient, *, clock: Callable[[], datetime] | None = None):
        self.client = client
        self.clock = clock or (lambda: datetime.now(UTC))

    @property
    def available(self) -> bool:
        return self.client.available

    def service_red(self, query: ServiceMetricQuery) -> ServiceRed:
        try:
            return self._service_red(query)
        except AggregateMetricsTooLarge as exc:
            raise TelemetryQueryTooLarge("聚合库响应超过大小上限") from exc
        except AggregateMetricsUnavailable as exc:
            raise TelemetryStoreUnavailable("聚合库查询不可用") from exc

    def _service_red(self, query: ServiceMetricQuery) -> ServiceRed:
        ended_at = align_query_end(query.ended_at, now=self.clock())
        started_at = _as_utc(query.started_at)
        window_seconds = int((ended_at - started_at).total_seconds())
        if window_seconds <= 0:
            return ServiceRed(None, None, None, None)
        labels = _labels(query)
        requests = _scalar(
            self.client.query_instant(
                _increase("apm_calls_total", labels, window_seconds),
                at=ended_at,
            )
        )
        if requests is None or requests <= 0:
            return ServiceRed(None, None, None, None)
        errors = _scalar(
            self.client.query_instant(
                _increase("apm_calls_total", _labels(query, status_code=ERROR_STATUS), window_seconds),
                at=ended_at,
            )
        )
        total_ms = _scalar(
            self.client.query_instant(
                _increase("apm_duration_milliseconds_sum", labels, window_seconds),
                at=ended_at,
            )
        )
        counted = _scalar(
            self.client.query_instant(
                _increase("apm_duration_milliseconds_count", labels, window_seconds),
                at=ended_at,
            )
        )
        p95 = _scalar(self.client.query_instant(_quantile(0.95, labels, window_seconds), at=ended_at))
        p99 = _scalar(self.client.query_instant(_quantile(0.99, labels, window_seconds), at=ended_at))
        error_count = 0.0 if errors is None else errors
        timeseries: tuple[ServiceRedPoint, ...] = ()
        endpoints: tuple[ServiceEndpointRed, ...] = ()
        if query.include_breakdown:
            timeseries = self._trend(query, started_at, ended_at, window_seconds)
            if query.include_endpoints:
                endpoints = self._top_endpoints(query, ended_at, window_seconds)
        avg_ms = None if total_ms is None or counted is None or counted <= 0 else total_ms / counted
        return ServiceRed(
            request_rate=requests / window_seconds,
            error_rate=error_count / requests,
            p95_ms=p95,
            p99_ms=p99,
            timeseries=timeseries,
            top_endpoints=endpoints,
            request_count=int(requests),
            error_count=int(error_count),
            avg_ms=avg_ms,
            max_ms=None,
        )

    def _trend(
        self,
        query: ServiceMetricQuery,
        started_at: datetime,
        ended_at: datetime,
        window_seconds: int,
    ) -> tuple[ServiceRedPoint, ...]:
        step = _trend_step(window_seconds)
        labels = _labels(query)
        error_labels = _labels(query, status_code=ERROR_STATUS)
        requests = _matrix(
            self.client.query_range(
                _increase("apm_calls_total", labels, step),
                start=started_at,
                end=ended_at,
                step_seconds=step,
            )
        )
        errors = dict(
            _matrix(
                self.client.query_range(
                    _increase("apm_calls_total", error_labels, step),
                    start=started_at,
                    end=ended_at,
                    step_seconds=step,
                )
            )
        )
        p95 = dict(
            _matrix(
                self.client.query_range(
                    _quantile(0.95, labels, step),
                    start=started_at,
                    end=ended_at,
                    step_seconds=step,
                )
            )
        )
        p99 = dict(
            _matrix(
                self.client.query_range(
                    _quantile(0.99, labels, step),
                    start=started_at,
                    end=ended_at,
                    step_seconds=step,
                )
            )
        )
        points: list[ServiceRedPoint] = []
        for timestamp, count in requests:
            if count is None:
                points.append(
                    ServiceRedPoint(
                        timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
                        request_rate=None,
                        error_rate=None,
                        p95_ms=None,
                        p99_ms=None,
                        max_ms=None,
                    )
                )
                continue
            error_count = errors.get(timestamp)
            # 有请求但没有错误序列，表示这个桶没有错误样本，按 0 而不是缺数据。
            if count > 0 and error_count is None:
                error_count = 0.0
            points.append(
                ServiceRedPoint(
                    timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
                    request_rate=count / step,
                    error_rate=None if count <= 0 else error_count / count,
                    p95_ms=p95.get(timestamp) if count > 0 else None,
                    p99_ms=p99.get(timestamp) if count > 0 else None,
                    request_count=int(count),
                    error_count=None if count <= 0 else int(error_count or 0),
                    max_ms=None,
                )
            )
        return tuple(points)

    def slo_measurement(self, query: SloMetricQuery) -> SloMeasurement:
        try:
            return self._slo_measurement(query)
        except AggregateMetricsTooLarge as exc:
            raise TelemetryQueryTooLarge("聚合库响应超过大小上限") from exc
        except AggregateMetricsUnavailable as exc:
            raise TelemetryStoreUnavailable("聚合库查询不可用") from exc

    def _slo_measurement(self, query: SloMetricQuery) -> SloMeasurement:
        ended_at = align_query_end(query.ended_at, now=self.clock())
        started_at = _as_utc(query.started_at)
        window_seconds = int((ended_at - started_at).total_seconds())
        if window_seconds <= 0:
            return SloMeasurement(None, None, None, MetricDataState.NO_DATA)
        total = _scalar(
            self.client.query_instant(
                _increase("apm_calls_total", _labels(query), window_seconds),
                at=ended_at,
            )
        )
        if total is None or total <= 0:
            return SloMeasurement(None, None, None, MetricDataState.NO_DATA)
        bad = _scalar(
            self.client.query_instant(
                _increase("apm_calls_total", _labels(query, status_code=ERROR_STATUS), window_seconds),
                at=ended_at,
            )
        )
        bad_count = 0.0 if bad is None else bad
        good = max(0.0, total - bad_count)
        return SloMeasurement(
            compliance_percent=min(100.0, max(0.0, good / total * 100)),
            good_rate=good / window_seconds,
            total_rate=total / window_seconds,
            data_state=MetricDataState.AVAILABLE,
        )

    def _top_endpoints(self, query: ServiceMetricQuery, ended_at: datetime, window_seconds: int) -> tuple[ServiceEndpointRed, ...]:
        labels = _labels(query)
        requests = _by_label(
            self.client.query_instant(
                _increase("apm_calls_total", labels, window_seconds, by="span_name"),
                at=ended_at,
            ),
            "span_name",
        )
        errors = _by_label(
            self.client.query_instant(
                _increase("apm_calls_total", _labels(query, status_code=ERROR_STATUS), window_seconds, by="span_name"),
                at=ended_at,
            ),
            "span_name",
        )
        p95 = _by_label(
            self.client.query_instant(_quantile(0.95, labels, window_seconds, by="le, span_name"), at=ended_at),
            "span_name",
        )
        p99 = _by_label(
            self.client.query_instant(_quantile(0.99, labels, window_seconds, by="le, span_name"), at=ended_at),
            "span_name",
        )
        ranked = sorted(
            ((name, count) for name, count in requests.items() if count > 0),
            key=lambda item: (-item[1], item[0]),
        )[:10]
        return tuple(
            ServiceEndpointRed(
                endpoint=name,
                request_rate=count / window_seconds,
                error_rate=(errors.get(name) or 0.0) / count,
                p95_ms=p95.get(name),
                p99_ms=p99.get(name),
            )
            for name, count in ranked
        )


class ApmAggregateRedRouter:
    """聚合可用且窗口起点不早于聚合起点时读聚合库，否则读 VictoriaTraces。"""

    def __init__(self, *, traces, aggregate: AggregateApmRedStore, origin_at: Callable[[], datetime | None]):
        self.traces = traces
        self.aggregate = aggregate
        self.origin_at = origin_at

    def service_red(self, query: ServiceMetricQuery) -> ServiceRed:
        if not self._use_aggregate(query):
            return self.traces.service_red(query)
        return self.aggregate.service_red(query)

    def _use_aggregate(self, query: ServiceMetricQuery) -> bool:
        if not self.aggregate.available:
            return False
        if query.version or query.instance_id or query.slow_threshold_ms or query.apdex_threshold_ms:
            return False
        origin = self.origin_at()
        if origin is None:
            return False
        return _as_utc(query.started_at) >= _as_utc(origin)


class ApmAvailabilitySloStore:
    """可用性窗口被聚合起点覆盖时读聚合库；否则和延迟 SLO 一样读 VictoriaTraces。

    聚合库报错只向上抛，不回退扫明细。回退到明细时，窗口长于保留期或保留期无法解析则不查询。
    """

    def __init__(self, *, traces, aggregate: AggregateApmRedStore, origin_at: Callable[[], datetime | None]):
        self.traces = traces
        self.aggregate = aggregate
        self.origin_at = origin_at

    def slo_measurement(self, query: SloMetricQuery) -> SloMeasurement:
        if query.sli_type != "availability" or not self._covered(query):
            reason = trace_retention_block_reason(query.started_at, query.ended_at)
            if reason is not None:
                raise TelemetryStoreUnavailable(reason)
            return self.traces.slo_measurement(query)
        return self.aggregate.slo_measurement(query)

    def _covered(self, query: SloMetricQuery) -> bool:
        if not self.aggregate.available:
            return False
        origin = self.origin_at()
        if origin is None:
            return False
        return _as_utc(query.started_at) >= _as_utc(origin)


def apm_availability_slo_store(*, traces=None, clock: Callable[[], datetime] | None = None) -> ApmAvailabilitySloStore:
    detail_store = traces or VictoriaTracesTelemetryStore()
    return ApmAvailabilitySloStore(
        traces=detail_store,
        aggregate=AggregateApmRedStore(AggregatePromqlClient.from_env(), clock=clock),
        origin_at=lambda: recorded_origin("apm"),
    )


def apm_entry_red_store(*, traces=None, clock: Callable[[], datetime] | None = None) -> ApmAggregateRedRouter:
    detail_store = traces or VictoriaTracesTelemetryStore()
    return ApmAggregateRedRouter(
        traces=detail_store,
        aggregate=AggregateApmRedStore(AggregatePromqlClient.from_env(), clock=clock),
        origin_at=lambda: recorded_origin("apm"),
    )
