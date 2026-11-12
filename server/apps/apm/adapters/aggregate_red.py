"""入口 RED 与可用性 SLO 的聚合库读取，以及相对 VictoriaTraces 的窗口路由。

慢请求、Apdex、版本、实例和延迟 SLO 仍走 VictoriaTraces。聚合库报错只向上抛，不回退扫明细。
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

from apps.apm.adapters.errors import TelemetryQueryTooLarge, TelemetryStoreUnavailable
from apps.apm.adapters.victoriatraces import MAX_RED_POINTS, VictoriaTracesTelemetryStore
from apps.apm.services.contracts import (
    GroupedRed,
    GroupedRedOverview,
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
from apps.core.aggregate_promql import apm_flush_seconds, escape_promql_label_value, escape_re2

ERROR_STATUS = "STATUS_CODE_ERROR"
GROUPED_QUERY_LIMIT_BYTES = 12 * 1024
_TARGET_BY = "service_namespace, service_name, deployment_environment"


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


def histogram_quantile(phi: float, buckets: Sequence[tuple[float, float]]) -> float | None:
    """按 Prometheus ``histogram_quantile`` 从累计桶计算分位数。

    桶按上界升序。``+Inf`` 桶的累计值为 0，或没有 ``+Inf`` 桶时返回 ``None``。
    分位落在 ``+Inf`` 桶时返回最大有限上界。第一个桶的下界是 0。
    累计值下降时先取前缀最大值，再在桶内线性插值。
    """

    parsed: list[tuple[float, float]] = []
    for upper, count in buckets:
        if isinstance(upper, bool) or isinstance(count, bool):
            continue
        if not isinstance(upper, (int, float)) or not isinstance(count, (int, float)):
            continue
        if math.isnan(upper) or not math.isfinite(count):
            continue
        parsed.append((float(upper), float(count)))
    if not parsed:
        return None
    parsed.sort(key=lambda item: item[0])
    merged: list[tuple[float, float]] = []
    for upper, count in parsed:
        if merged and merged[-1][0] == upper:
            merged[-1] = (upper, max(merged[-1][1], count))
        else:
            merged.append((upper, count))
    monotonic: list[tuple[float, float]] = []
    running = merged[0][1]
    monotonic.append((merged[0][0], running))
    for upper, count in merged[1:]:
        running = max(running, count)
        monotonic.append((upper, running))
    total = 0.0
    finite_upper: float | None = None
    has_infinity = False
    for upper, count in monotonic:
        if math.isinf(upper) and upper > 0:
            has_infinity = True
            total = count
        elif math.isfinite(upper):
            finite_upper = upper
    if not has_infinity or total <= 0 or finite_upper is None:
        return None
    rank = phi * total
    chosen: int | None = None
    for index, (_, count) in enumerate(monotonic):
        if count >= rank:
            chosen = index
            break
    if chosen is None:
        return finite_upper
    upper = monotonic[chosen][0]
    if not math.isfinite(upper):
        return finite_upper
    lower = 0.0 if chosen == 0 else monotonic[chosen - 1][0]
    if not math.isfinite(lower):
        lower = 0.0
    previous = 0.0 if chosen == 0 else monotonic[chosen - 1][1]
    span = monotonic[chosen][1] - previous
    if span <= 0:
        return lower
    return lower + (upper - lower) * ((rank - previous) / span)


def _job_value(namespace: str, name: str) -> str:
    return f"{namespace or 'unknown'}/{name or 'unknown'}"


def _label_key(namespace: str, name: str) -> tuple[str, str]:
    return (namespace or "unknown", name or "unknown")


def _job_regex(jobs: Sequence[str]) -> str:
    return "|".join(escape_promql_label_value(escape_re2(job)) for job in jobs)


def _grouped_expressions(regex: str, window_seconds: int, step_seconds: int, *, include_overview: bool) -> list[tuple[str, str]]:
    red = f'job=~"{regex}", service_name!=""'
    error = f'{red}, status_code="{ERROR_STATUS}"'
    window = f"{window_seconds}s"
    expressions = [
        ("requests", f"sum by ({_TARGET_BY}) (increase(apm_calls_total{{{red}}}[{window}]))"),
        ("errors", f"sum by ({_TARGET_BY}) (increase(apm_calls_total{{{error}}}[{window}]))"),
        ("duration_sum", f"sum by ({_TARGET_BY}) (increase(apm_duration_milliseconds_sum{{{red}}}[{window}]))"),
        ("duration_count", f"sum by ({_TARGET_BY}) (increase(apm_duration_milliseconds_count{{{red}}}[{window}]))"),
        (
            "p95",
            f"histogram_quantile(0.95, sum by (le, {_TARGET_BY}) (increase(apm_duration_milliseconds_bucket{{{red}}}[{window}])))",
        ),
        (
            "p99",
            f"histogram_quantile(0.99, sum by (le, {_TARGET_BY}) (increase(apm_duration_milliseconds_bucket{{{red}}}[{window}])))",
        ),
        (
            "overflow",
            f'sum by (job) (increase(apm_calls_total{{job=~"{regex}", otel_metric_overflow="true"}}[{window}])) > 0',
        ),
    ]
    if include_overview:
        step = f"{step_seconds}s"
        expressions.extend(
            [
                ("buckets", f"sum by (le) (increase(apm_duration_milliseconds_bucket{{{red}}}[{window}]))"),
                ("late", f'sum(increase(apm_aggregate_late_spans_total{{job=~"{regex}"}}[{window}]))'),
                ("trend_requests", f"sum(increase(apm_calls_total{{{red}}}[{step}]))"),
                ("trend_errors", f"sum(increase(apm_calls_total{{{error}}}[{step}]))"),
                ("trend_buckets", f"sum by (le) (increase(apm_duration_milliseconds_bucket{{{red}}}[{step}]))"),
            ]
        )
    return expressions


def _chunk_jobs(jobs: Sequence[str], window_seconds: int, step_seconds: int, *, include_overview: bool) -> list[list[str]]:
    # 每条表达式只含一次 job 正则，所以表达式长度 = 固定开销 + 正则长度。
    overhead = max(
        len(expression.encode("utf-8")) for _, expression in _grouped_expressions("", window_seconds, step_seconds, include_overview=include_overview)
    )
    budget = GROUPED_QUERY_LIMIT_BYTES - overhead
    chunks: list[list[str]] = []
    current: list[str] = []
    used = 0
    for job in jobs:
        piece = len(_job_regex([job]).encode("utf-8"))
        extra = piece if not current else piece + 1
        if current and used + extra > budget:
            chunks.append(current)
            current = [job]
            used = piece
        else:
            current.append(job)
            used += extra
    if current:
        chunks.append(current)
    return chunks


def _le_bound(raw: object) -> float | None:
    if raw == "+Inf":
        return math.inf
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(value):
        return None
    return value


def _resample_points(values: Sequence[float | None], points: int) -> tuple[float | None, ...]:
    if points <= 0:
        return ()
    if not values:
        return tuple([None] * points)
    if len(values) == points:
        return tuple(values)
    if len(values) == 1:
        return tuple([values[0]] * points)
    result: list[float | None] = []
    last_index = len(values) - 1
    for index in range(points):
        position = index * last_index / (points - 1)
        left = int(position)
        right = min(left + 1, last_index)
        left_value = values[left]
        right_value = values[right]
        if left_value is None and right_value is None:
            result.append(None)
        elif left == right or left_value is None:
            result.append(right_value)
        elif right_value is None:
            result.append(left_value)
        else:
            weight = position - left
            result.append(left_value * (1 - weight) + right_value * weight)
    return tuple(result)


class _GroupedAccum:
    def __init__(self):
        self.requests: float | None = None
        self.errors: float | None = None
        self.total_ms: float | None = None
        self.counted: float | None = None
        self.p95: float | None = None
        self.p99: float | None = None

    def add(self, field: str, value: float, *, replace: bool = False) -> None:
        current = getattr(self, field)
        if replace:
            if current is None:
                setattr(self, field, value)
            return
        setattr(self, field, value if current is None else current + value)


def _service_catalog(services: Sequence[tuple[str, str]]):
    by_label: dict[tuple[str, str], list[tuple[str, str]]] = {}
    job_services: dict[str, list[tuple[str, str]]] = {}
    jobs: list[str] = []
    seen_jobs: set[str] = set()
    for namespace, name in services:
        identity = (namespace, name)
        label = _label_key(namespace, name)
        identities = by_label.setdefault(label, [])
        if identity not in identities:
            identities.append(identity)
        job = _job_value(namespace, name)
        owners = job_services.setdefault(job, [])
        if identity not in owners:
            owners.append(identity)
        if job not in seen_jobs:
            seen_jobs.add(job)
            jobs.append(job)
    return by_label, job_services, jobs


def _series_target(metric: dict, by_label: dict[tuple[str, str], list[tuple[str, str]]]):
    if "service_name" not in metric and "service_namespace" not in metric:
        return None
    name = str(metric.get("service_name") or "")
    if not name:
        return None
    namespace = str(metric.get("service_namespace") or "unknown")
    identities = by_label.get((namespace, name))
    if not identities:
        return None
    if "deployment_environment" in metric:
        environment = str(metric.get("deployment_environment") or "")
    else:
        environment = ""
    return identities, environment


def _matrix_points(series: dict) -> list[tuple[float, float | None]]:
    values = series.get("values")
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
    return points


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

    def grouped_red(
        self,
        services: Sequence[tuple[str, str]],
        started_at: datetime,
        ended_at: datetime,
        *,
        include_overview: bool = False,
        overview_points: int = 0,
    ) -> GroupedRed:
        try:
            return self._grouped_red(
                services,
                started_at,
                ended_at,
                include_overview=include_overview,
                overview_points=overview_points,
            )
        except AggregateMetricsTooLarge as exc:
            raise TelemetryQueryTooLarge("聚合库响应超过大小上限") from exc
        except AggregateMetricsUnavailable as exc:
            raise TelemetryStoreUnavailable("聚合库查询不可用") from exc

    def _grouped_red(
        self,
        services: Sequence[tuple[str, str]],
        started_at: datetime,
        ended_at: datetime,
        *,
        include_overview: bool,
        overview_points: int,
    ) -> GroupedRed:
        ended_at = align_query_end(ended_at, now=self.clock())
        started_at = _as_utc(started_at)
        window_seconds = int((ended_at - started_at).total_seconds())
        by_label, job_services, jobs = _service_catalog(services)
        if window_seconds <= 0 or not jobs:
            overview = _empty_grouped_overview(overview_points) if include_overview else None
            return GroupedRed({}, frozenset(), overview)
        step = _grouped_step(window_seconds, overview_points if include_overview else 1)
        chunks = _chunk_jobs(jobs, window_seconds, step, include_overview=include_overview)
        totals = {"requests": 0.0, "errors": 0.0, "saw_requests": False, "saw_errors": False}
        accums: dict[tuple[tuple[str, str], str], _GroupedAccum] = {}
        truncated: set[tuple[str, str]] = set()
        bucket_totals: dict[float, float] = {}
        late_total: float | None = None
        request_points: dict[float, float] = {}
        error_points: dict[float, float] = {}
        bucket_points: dict[float, dict[float, float]] = {}
        range_start = started_at + timedelta(seconds=step)
        for chunk in chunks:
            expressions = _grouped_expressions(_job_regex(chunk), window_seconds, step, include_overview=include_overview)
            results = {kind: self.client.query_instant(expression, at=ended_at) for kind, expression in expressions if not kind.startswith("trend_")}
            self._absorb_grouped_counts(results, by_label, accums, totals)
            truncated.update(self._overflow_services(results.get("overflow") or [], job_services))
            if include_overview:
                self._absorb_buckets(results.get("buckets") or [], by_label, bucket_totals)
                late_value = _scalar(results.get("late") or [])
                if late_value is not None:
                    late_total = late_value if late_total is None else late_total + late_value
                if range_start <= ended_at:
                    for kind, expression in expressions:
                        if not kind.startswith("trend_"):
                            continue
                        matrix = self.client.query_range(expression, start=range_start, end=ended_at, step_seconds=step)
                        if kind == "trend_requests":
                            _absorb_matrix_sum(matrix, by_label, request_points)
                        elif kind == "trend_errors":
                            _absorb_matrix_sum(matrix, by_label, error_points)
                        else:
                            _absorb_matrix_buckets(matrix, by_label, bucket_points)
        by_target = _grouped_targets(accums, window_seconds)
        overview = None
        if include_overview:
            overview = _grouped_overview(
                totals,
                window_seconds,
                bucket_totals,
                late_total,
                request_points,
                error_points,
                bucket_points,
                step,
                overview_points,
            )
        return GroupedRed(by_target, frozenset(truncated), overview)

    def _absorb_grouped_counts(self, results: dict[str, list], by_label: dict, accums: dict, totals: dict) -> None:
        counted_fields = (
            ("requests", "requests", False),
            ("errors", "errors", False),
            ("duration_sum", "total_ms", False),
            ("duration_count", "counted", False),
            ("p95", "p95", True),
            ("p99", "p99", True),
        )
        for kind, field, replace in counted_fields:
            for series in results.get(kind) or []:
                metric = series.get("metric")
                if not isinstance(metric, dict):
                    continue
                target = _series_target(metric, by_label)
                value = _sample(series)
                if target is None or value is None:
                    continue
                identities, environment = target
                if kind == "requests" and value <= 0:
                    continue
                if kind == "requests":
                    totals["saw_requests"] = True
                    totals["requests"] += value
                elif kind == "errors":
                    totals["saw_errors"] = True
                    totals["errors"] += value
                for identity in identities:
                    accums.setdefault((identity, environment), _GroupedAccum()).add(field, value, replace=replace)

    @staticmethod
    def _overflow_services(result: list, job_services: dict[str, list[tuple[str, str]]]) -> set[tuple[str, str]]:
        found: set[tuple[str, str]] = set()
        for series in result:
            metric = series.get("metric")
            if not isinstance(metric, dict):
                continue
            value = _sample(series)
            if value is None or value <= 0:
                continue
            job = str(metric.get("job") or "")
            found.update(job_services.get(job, ()))
        return found

    @staticmethod
    def _absorb_buckets(result: list, by_label: dict, totals: dict[float, float]) -> None:
        for series in result:
            metric = series.get("metric")
            if not isinstance(metric, dict):
                continue
            if ("service_name" in metric or "service_namespace" in metric) and _series_target(metric, by_label) is None:
                continue
            upper = _le_bound(metric.get("le"))
            value = _sample(series)
            if upper is None or value is None:
                continue
            totals[upper] = totals.get(upper, 0.0) + value


def _grouped_step(window_seconds: int, points: int) -> int:
    return max(apm_flush_seconds(), math.ceil(window_seconds / max(points, 1)))


def _empty_grouped_overview(points: int) -> GroupedRedOverview:
    blank = tuple([None] * max(points, 0))
    return GroupedRedOverview(None, None, None, blank, blank, blank, None)


def _grouped_targets(accums: dict[tuple[tuple[str, str], str], _GroupedAccum], window_seconds: int) -> dict[tuple[str, str, str], ServiceRed]:
    by_target: dict[tuple[str, str, str], ServiceRed] = {}
    for (identity, environment), accum in accums.items():
        if accum.requests is None or accum.requests <= 0:
            continue
        namespace, name = identity
        error_count = 0.0 if accum.errors is None else accum.errors
        avg_ms = None if accum.total_ms is None or accum.counted is None or accum.counted <= 0 else accum.total_ms / accum.counted
        by_target[(namespace, name, environment)] = ServiceRed(
            request_rate=accum.requests / window_seconds,
            error_rate=error_count / accum.requests,
            p95_ms=accum.p95,
            p99_ms=accum.p99,
            request_count=int(accum.requests),
            error_count=int(error_count),
            avg_ms=avg_ms,
            max_ms=None,
        )
    return by_target


def _grouped_overview(
    totals: dict,
    window_seconds: int,
    bucket_totals: dict[float, float],
    late_total: float | None,
    request_points: dict[float, float],
    error_points: dict[float, float],
    bucket_points: dict[float, dict[float, float]],
    step: int,
    overview_points: int,
) -> GroupedRedOverview:
    if not totals["saw_requests"]:
        request_rate = None
        error_rate = None
    else:
        request_rate = totals["requests"] / window_seconds
        error_rate = (totals["errors"] if totals["saw_errors"] else 0.0) / window_seconds
    timestamps = sorted(set(request_points) | set(error_points) | set(bucket_points))
    request_rates: list[float | None] = []
    error_rates: list[float | None] = []
    p95_rates: list[float | None] = []
    for timestamp in timestamps:
        count = request_points.get(timestamp)
        request_rates.append(None if count is None else count / step)
        if timestamp in error_points:
            error_rates.append(error_points[timestamp] / step)
        elif count is not None and count > 0:
            error_rates.append(0.0)
        else:
            error_rates.append(None)
        buckets = bucket_points.get(timestamp)
        p95_rates.append(None if not buckets else histogram_quantile(0.95, list(buckets.items())))
    return GroupedRedOverview(
        request_rate=request_rate,
        error_request_rate=error_rate,
        p95_ms=histogram_quantile(0.95, list(bucket_totals.items())) if bucket_totals else None,
        request_trend=_resample_points(request_rates, overview_points),
        error_trend=_resample_points(error_rates, overview_points),
        p95_trend=_resample_points(p95_rates, overview_points),
        late_spans=None if late_total is None else int(late_total),
    )


def _series_is_authorized(metric: dict, by_label: dict) -> bool:
    if "service_name" not in metric and "service_namespace" not in metric:
        return True
    return _series_target(metric, by_label) is not None


def _absorb_matrix_sum(result: list, by_label: dict, into: dict[float, float]) -> None:
    for series in result:
        metric = series.get("metric")
        if not isinstance(metric, dict) or not _series_is_authorized(metric, by_label):
            continue
        for timestamp, value in _matrix_points(series):
            if value is None:
                continue
            into[timestamp] = into.get(timestamp, 0.0) + value


def _absorb_matrix_buckets(result: list, by_label: dict, into: dict[float, dict[float, float]]) -> None:
    for series in result:
        metric = series.get("metric")
        if not isinstance(metric, dict) or not _series_is_authorized(metric, by_label):
            continue
        upper = _le_bound(metric.get("le"))
        if upper is None:
            continue
        for timestamp, value in _matrix_points(series):
            if value is None:
                continue
            slot = into.setdefault(timestamp, {})
            slot[upper] = slot.get(upper, 0.0) + value


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

    def grouped_red(
        self,
        services: Sequence[tuple[str, str]],
        started_at: datetime,
        ended_at: datetime,
        *,
        include_overview: bool = False,
        overview_points: int = 0,
    ) -> GroupedRed | None:
        if not self._covered(started_at):
            return None
        return self.aggregate.grouped_red(
            services,
            started_at,
            ended_at,
            include_overview=include_overview,
            overview_points=overview_points,
        )

    def _covered(self, started_at: datetime) -> bool:
        if not self.aggregate.available:
            return False
        origin = self.origin_at()
        if origin is None:
            return False
        return _as_utc(started_at) >= _as_utc(origin)

    def _use_aggregate(self, query: ServiceMetricQuery) -> bool:
        if query.version or query.instance_id or query.slow_threshold_ms or query.apdex_threshold_ms:
            return False
        return self._covered(query.started_at)


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
