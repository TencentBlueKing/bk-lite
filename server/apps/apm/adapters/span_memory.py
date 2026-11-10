"""同一批 Span 上计算逐目标 RED 和按目标分组的 RED。"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from apps.apm.adapters.errors import TelemetryGroupedReadFallback, TelemetryUniqueSpanLimitExceeded
from apps.apm.adapters.span_aliases import client_dependency_matches, dependency_identity, grouped_dependency_conflicts
from apps.apm.services.contracts import (
    ENTRY_SPAN_KINDS,
    GROUPED_RED_INSTANCE,
    GROUPED_RED_NAME,
    GROUPED_RED_VERSION,
    DependencyMetricQuery,
    GroupedDependencyRedQuery,
    GroupedServiceRedQuery,
    InstanceActivity,
    InstanceActivityQuery,
    ServiceEndpointRed,
    ServiceMetricQuery,
    ServiceRed,
    ServiceRedPoint,
    top_endpoints_from_grouped,
)

_RED_SERIES_POINTS = 120
_ENTRY_KINDS = frozenset(ENTRY_SPAN_KINDS)


def _window_seconds(started_at: datetime, ended_at: datetime) -> int:
    return max(1, int((ended_at - started_at).total_seconds()))


def _trend_step(window_seconds: int) -> int:
    return max(15, math.ceil(window_seconds / (_RED_SERIES_POINTS - 1)))


def _align_bucket(moment: datetime, step: int) -> datetime:
    seconds = int(moment.timestamp())
    return datetime.fromtimestamp(seconds - (seconds % step), tz=UTC)


def _quantile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


@dataclass(frozen=True)
class MemorySpan:
    trace_id: str
    span_id: str
    started_at: datetime
    duration_ms: float
    service_namespace: str
    service_name: str
    environment: str
    name: str
    kind: str
    status: str
    version: str = ""
    instance_id: str = ""
    attributes: Mapping[str, str] = field(default_factory=dict)


def _merge_span(left: MemorySpan, right: MemorySpan) -> MemorySpan:
    """同一 trace_id + span_id 保留较大耗时，名称 / 版本 / 实例取字典序较大值，与 LogsQL max() 一致。"""

    primary = right if right.duration_ms > left.duration_ms else left
    status = "error" if left.status == "error" or right.status == "error" else primary.status
    return replace(
        primary,
        duration_ms=max(left.duration_ms, right.duration_ms),
        status=status,
        name=max(left.name, right.name),
        version=max(left.version, right.version),
        instance_id=max(left.instance_id or "", right.instance_id or ""),
    )


def _dedup_spans(spans: Sequence[MemorySpan]) -> list[MemorySpan]:
    kept: dict[tuple[str, str], MemorySpan] = {}
    for span in spans:
        key = (span.trace_id, span.span_id)
        current = kept.get(key)
        kept[key] = span if current is None else _merge_span(current, span)
    return list(kept.values())


def _summarize(spans: Sequence[MemorySpan], *, window_seconds: int, slow_ms: int | None, apdex_ms: int | None) -> ServiceRed:
    if not spans:
        return ServiceRed(None, None, None, None)
    durations = [span.duration_ms for span in spans]
    requests = len(spans)
    errors = sum(1 for span in spans if span.status == "error")
    slow = sum(1 for duration in durations if duration > slow_ms) if slow_ms else None
    satisfied = tolerating = None
    if apdex_ms:
        satisfied = sum(1 for duration in durations if duration <= apdex_ms)
        within = sum(1 for duration in durations if duration <= apdex_ms * 4)
        tolerating = max(0, within - satisfied)
    return ServiceRed(
        request_rate=requests / window_seconds,
        error_rate=errors / requests,
        p95_ms=_quantile(durations, 0.95),
        p99_ms=_quantile(durations, 0.99),
        request_count=requests,
        error_count=errors,
        avg_ms=sum(durations) / requests,
        max_ms=max(durations),
        p50_ms=_quantile(durations, 0.5),
        p75_ms=_quantile(durations, 0.75),
        p90_ms=_quantile(durations, 0.9),
        slow_count=slow,
        satisfied_count=satisfied,
        tolerating_count=tolerating,
    )


def _dimension_value(span: MemorySpan, dimension: str) -> str:
    if dimension == GROUPED_RED_NAME:
        return span.name or ""
    if dimension == GROUPED_RED_VERSION:
        return span.version or ""
    if dimension == GROUPED_RED_INSTANCE:
        return span.instance_id or ""
    raise ValueError("不支持的分组维度")


def _classify_dependency(span: MemorySpan) -> tuple[str, str, str] | None:
    return dependency_identity(dict(span.attributes), span.name)


def _matches_dependency_filter(span: MemorySpan, query: DependencyMetricQuery) -> bool:
    return client_dependency_matches(
        dict(span.attributes),
        span.name,
        channel=query.channel,
        system=query.system,
        statement=query.statement,
    )


class InMemorySpanMetricStore:
    """用同一批 Span 计算逐目标 RED 和按目标分组的 RED，供策略等价性测试与本地夹具使用。"""

    def __init__(self, spans: Iterable[MemorySpan] = (), *, unique_span_limit: int | None = None):
        self.spans = list(spans)
        self.unique_span_limit = unique_span_limit

    def service_red(self, query: ServiceMetricQuery) -> ServiceRed:
        spans = _dedup_spans(self._entry_spans(query))
        red = self._finish(spans, query)
        if not query.include_endpoints or red.request_count is None:
            return red
        # 不超过 1 天时，VictoriaTraces 的 Top 操作只按端点和版本过滤，不按实例。
        top_spans = spans
        if query.instance_id and query.ended_at - query.started_at <= timedelta(days=1):
            top_spans = _dedup_spans(self._entry_spans(query, instance_id=""))
        window_seconds = _window_seconds(query.started_at, query.ended_at)
        grouped = {
            key: _summarize(
                items,
                window_seconds=window_seconds,
                slow_ms=query.slow_threshold_ms or None,
                apdex_ms=query.apdex_threshold_ms or None,
            )
            for key, items in _group_spans(top_spans, (GROUPED_RED_NAME,)).items()
        }
        return replace(red, top_endpoints=top_endpoints_from_grouped(grouped, name_index=0))

    def service_red_grouped(self, query: GroupedServiceRedQuery) -> dict[tuple[str, ...], ServiceRed]:
        if not query.group_by:
            raise ValueError("分组维度不能为空")
        spans = self._entry_spans(query, endpoint="", version="", instance_id="")
        self._enforce_unique_limit(spans)
        grouped = _group_spans(_dedup_spans(spans), query.group_by)
        return {key: self._finish(items, query) for key, items in grouped.items()}

    def dependency_red(self, query: DependencyMetricQuery) -> ServiceRed:
        spans = [span for span in self._client_spans(query) if _matches_dependency_filter(span, query)]
        return self._finish(_dedup_spans(spans), query)

    def dependency_red_grouped(self, query: GroupedDependencyRedQuery) -> dict[tuple[str, str, str], ServiceRed]:
        spans = self._client_spans(query)
        self._enforce_unique_limit(spans)
        buckets = self._dependency_buckets(spans, query.targets)
        return {identity: self._finish(_dedup_spans(items), query) for identity, items in buckets.items()}

    def service_red_grouped_by_day(
        self,
        query: GroupedServiceRedQuery,
        windows: Sequence[tuple[datetime, datetime]],
    ) -> dict[tuple[str, ...], tuple[ServiceRed, ...]]:
        if not query.group_by:
            raise ValueError("分组维度不能为空")
        per_window, collected = self._window_groups(
            windows,
            lambda started_at, ended_at: self._entry_spans(
                replace(query, started_at=started_at, ended_at=ended_at),
                endpoint="",
                version="",
                instance_id="",
            ),
            query.group_by,
        )
        self._enforce_unique_limit(collected)
        return self._reds_for_windows(query, windows, per_window)

    def dependency_red_grouped_by_day(
        self,
        query: GroupedDependencyRedQuery,
        windows: Sequence[tuple[datetime, datetime]],
    ) -> dict[tuple[str, str, str], tuple[ServiceRed, ...]]:
        per_window: list[dict[tuple[str, str, str], list[MemorySpan]]] = []
        collected: list[MemorySpan] = []
        for started_at, ended_at in windows:
            spans = self._client_spans(replace(query, started_at=started_at, ended_at=ended_at))
            collected.extend(spans)
            buckets = self._dependency_buckets(spans, query.targets)
            per_window.append({key: _dedup_spans(items) for key, items in buckets.items()})
        self._enforce_unique_limit(collected)
        return self._reds_for_windows(query, windows, per_window)

    def service_endpoints(self, query: ServiceMetricQuery, limit: int = 100) -> tuple[ServiceEndpointRed, ...]:
        spans = _dedup_spans(self._entry_spans(query, endpoint="", version="", instance_id=""))
        window_seconds = _window_seconds(query.started_at, query.ended_at)
        grouped = {
            key: _summarize(items, window_seconds=window_seconds, slow_ms=None, apdex_ms=None)
            for key, items in _group_spans(spans, (GROUPED_RED_NAME,)).items()
        }
        return top_endpoints_from_grouped(grouped, name_index=0, limit=max(1, limit))

    def instance_activity(self, query: InstanceActivityQuery) -> list[InstanceActivity]:
        latest: dict[tuple[str, str, str, str], MemorySpan] = {}
        for span in self.spans:
            if not span.instance_id or not query.started_at <= span.started_at < query.ended_at:
                continue
            key = (span.service_namespace, span.service_name, span.environment, span.instance_id)
            current = latest.get(key)
            if current is None or span.started_at > current.started_at:
                latest[key] = span
        return [
            InstanceActivity(
                service_namespace=span.service_namespace,
                service_name=span.service_name,
                instance_id=span.instance_id,
                environment=span.environment,
                version=span.version,
                last_seen_at=span.started_at,
            )
            for span in latest.values()
        ]

    def client_db_rollups(self, namespace: str, service_name: str, environment: str, started_at, ended_at) -> list[dict]:
        counts: dict[tuple[str, str, str], int] = {}
        for span in _dedup_spans(self._client_spans_between(namespace, service_name, environment, started_at, ended_at)):
            identity = _classify_dependency(span)
            if identity is None:
                continue
            counts[identity] = counts.get(identity, 0) + 1
        rows = [
            {"channel": channel, "system": system, "statement": statement, "call_count": count}
            for (channel, system, statement), count in counts.items()
        ]
        rows.sort(key=lambda item: (-item["call_count"], item["statement"]))
        return rows

    def _dependency_buckets(self, spans, targets) -> dict[tuple[str, str, str], list[MemorySpan]]:
        buckets: dict[tuple[str, str, str], list[MemorySpan]] = {}
        for span in spans:
            attributes = dict(span.attributes)
            if grouped_dependency_conflicts(attributes, span.name, targets):
                raise TelemetryGroupedReadFallback("分组依赖与逐目标过滤重叠，退回逐目标")
            identity = dependency_identity(attributes, span.name)
            if identity is None:
                continue
            buckets.setdefault(identity, []).append(span)
        return buckets

    def _window_groups(self, windows, select, group_by: tuple[str, ...]):
        per_window = []
        collected: list[MemorySpan] = []
        for started_at, ended_at in windows:
            spans = select(started_at, ended_at)
            collected.extend(spans)
            per_window.append(_group_spans(_dedup_spans(spans), group_by))
        return per_window, collected

    def _reds_for_windows(self, query, windows, per_window):
        keys = set()
        for grouped in per_window:
            keys.update(grouped)
        result = {}
        for key in keys:
            reds = []
            for index, (started_at, ended_at) in enumerate(windows):
                scoped = replace(query, started_at=started_at, ended_at=ended_at, include_breakdown=False)
                reds.append(self._finish(per_window[index].get(key, ()), scoped))
            result[key] = tuple(reds)
        return result

    def _finish(self, spans: Sequence[MemorySpan], query) -> ServiceRed:
        window_seconds = _window_seconds(query.started_at, query.ended_at)
        slow_ms = query.slow_threshold_ms or None
        apdex_ms = query.apdex_threshold_ms or None
        red = _summarize(spans, window_seconds=window_seconds, slow_ms=slow_ms, apdex_ms=apdex_ms)
        if not getattr(query, "include_breakdown", False) or red.request_count is None:
            return red
        step = _trend_step(window_seconds)
        buckets: dict[datetime, list[MemorySpan]] = {}
        for span in spans:
            buckets.setdefault(_align_bucket(span.started_at, step), []).append(span)
        points = []
        for stamp in sorted(buckets):
            point = _summarize(buckets[stamp], window_seconds=step, slow_ms=slow_ms, apdex_ms=apdex_ms)
            points.append(
                ServiceRedPoint(
                    timestamp=stamp,
                    request_rate=point.request_rate,
                    error_rate=point.error_rate,
                    p95_ms=point.p95_ms,
                    p99_ms=point.p99_ms,
                    avg_ms=point.avg_ms,
                    max_ms=point.max_ms,
                    p50_ms=point.p50_ms,
                    p75_ms=point.p75_ms,
                    p90_ms=point.p90_ms,
                    slow_count=point.slow_count,
                    satisfied_count=point.satisfied_count,
                    tolerating_count=point.tolerating_count,
                    error_count=point.error_count,
                    request_count=point.request_count,
                )
            )
        return replace(red, timeseries=tuple(points))

    def _enforce_unique_limit(self, spans: Sequence[MemorySpan]) -> None:
        if self.unique_span_limit is None:
            return
        unique = {(span.trace_id, span.span_id) for span in spans}
        if len(unique) > self.unique_span_limit:
            raise TelemetryUniqueSpanLimitExceeded("APM 查询唯一 Span 数超过单次聚合上限")

    def _entry_spans(self, query, *, endpoint=None, version=None, instance_id=None) -> list[MemorySpan]:
        endpoint = query.endpoint if endpoint is None else endpoint
        version = query.version if version is None else version
        instance_id = query.instance_id if instance_id is None else instance_id
        return [
            span
            for span in self.spans
            if span.kind in _ENTRY_KINDS
            and span.service_namespace == query.service_namespace
            and span.service_name == query.service_name
            and span.environment == query.environment
            and query.started_at <= span.started_at < query.ended_at
            and (not endpoint or span.name == endpoint)
            and (not version or span.version == version)
            and (not instance_id or span.instance_id == instance_id)
        ]

    def _client_spans(self, query) -> list[MemorySpan]:
        return self._client_spans_between(
            query.service_namespace,
            query.service_name,
            query.environment,
            query.started_at,
            query.ended_at,
        )

    def _client_spans_between(self, namespace: str, service_name: str, environment: str, started_at, ended_at) -> list[MemorySpan]:
        return [
            span
            for span in self.spans
            if span.kind == "client"
            and span.service_namespace == namespace
            and span.service_name == service_name
            and span.environment == environment
            and started_at <= span.started_at < ended_at
        ]


def _group_spans(spans: Sequence[MemorySpan], group_by: tuple[str, ...]) -> dict[tuple[str, ...], list[MemorySpan]]:
    grouped: dict[tuple[str, ...], list[MemorySpan]] = {}
    for span in spans:
        key = tuple(_dimension_value(span, dimension) for dimension in group_by)
        grouped.setdefault(key, []).append(span)
    return grouped
