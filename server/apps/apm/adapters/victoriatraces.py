from __future__ import annotations

import base64
import json
import math
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from apps.apm.adapters.errors import TelemetryStoreUnavailable
from apps.apm.services.contracts import (
    InstanceActivity,
    InstanceActivityQuery,
    MetricDataState,
    ServiceDependency,
    ServiceEndpointRed,
    ServiceMetricQuery,
    ServiceRed,
    ServiceRedPoint,
    SloMeasurement,
    SloMetricQuery,
    SpanDetail,
    TopologyDependencyQuery,
    TraceDetail,
    TracePage,
    TraceSearchQuery,
    TraceSummary,
)
from apps.apm.services.identity import normalize_identity

MAX_QUERY_WINDOW = timedelta(days=35)
MAX_TOPOLOGY_WINDOW = timedelta(days=7)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_UNIQUE_SPANS = 1_000_000
MAX_ACTIVITY_DIMENSIONS = 10_000
MAX_DEPENDENCIES = 10_000
MAX_RED_POINTS = 120
MAX_TOP_ENDPOINTS = 10
MAX_ENDPOINT_NAME_LENGTH = 256
_RAW_SPAN_PARSE_LIMIT = 1001

_NAMESPACE_FIELD = "`resource_attr:service.namespace`"
_SERVICE_FIELD = "`resource_attr:service.name`"
_INSTANCE_FIELD = "`resource_attr:service.instance.id`"
_ENVIRONMENT_FIELD = "`resource_attr:deployment.environment`"
_VERSION_FIELD = "`resource_attr:service.version`"


def _tag_map(tags: object) -> dict[str, object]:
    if not isinstance(tags, list):
        return {}
    result: dict[str, object] = {}
    for tag in tags:
        if isinstance(tag, dict) and isinstance(tag.get("key"), str):
            result[tag["key"]] = tag.get("value")
    return result


def _status_from_tags(tags: dict[str, object]) -> str:
    value = str(tags.get("otel.status_code", tags.get("status.code", ""))).casefold()
    error_tag = tags.get("error")
    if value in {"error", "status_code_error", "2"} or error_tag is True or str(error_tag).casefold() in {"1", "true"}:
        return "error"
    return "ok"


def _encode_cursor(started_at: datetime) -> str:
    microseconds = int(started_at.timestamp() * 1_000_000) - 1
    return base64.urlsafe_b64encode(str(microseconds).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> datetime:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        microseconds = int(base64.urlsafe_b64decode(padded.encode()).decode())
        return datetime.fromtimestamp(microseconds / 1_000_000, tz=UTC)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Trace 游标无效") from exc


def _logsql_string(value: str) -> str:
    """LogsQL exact-filter literal；字段名固定，只有值可由调用方提供。"""

    return json.dumps(value, ensure_ascii=False)


def _validate_window(started_at: datetime, ended_at: datetime, *, maximum: timedelta = MAX_QUERY_WINDOW) -> int:
    if ended_at <= started_at:
        raise ValueError("查询结束时间必须晚于开始时间")
    window = ended_at - started_at
    if window > maximum:
        raise ValueError(f"APM 查询时间窗不能超过 {maximum.days} 天")
    return max(1, int(window.total_seconds()))


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


class VictoriaTracesTelemetryStore:
    """APM 唯一遥测查询 Adapter；隐藏 Jaeger/LogsQL 与 VT 响应格式。"""

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        session: requests.Session | None = None,
    ):
        self.endpoint = (endpoint or os.getenv("APM_VICTORIATRACES_QUERY_ENDPOINT") or "http://127.0.0.1:10428").rstrip("/")
        self.session = session or requests.Session()
        self.timeout = (3, int(os.getenv("APM_VICTORIATRACES_QUERY_TIMEOUT", "15")))
        self.verify = os.getenv("APM_VICTORIATRACES_VERIFY_TLS", "true").casefold() != "false"
        user = os.getenv("APM_VICTORIATRACES_USER")
        password = os.getenv("APM_VICTORIATRACES_PASSWORD")
        self.auth = (user, password or "") if user else None

    def search(self, query: TraceSearchQuery) -> TracePage:
        _validate_window(query.started_at, query.ended_at)
        if not 1 <= query.limit <= 200:
            raise ValueError("Trace 查询 limit 必须在 1 到 200 之间")
        ended_at = min(query.ended_at, _decode_cursor(query.cursor)) if query.cursor else query.ended_at
        tags: dict[str, str] = {
            "resource_attr:deployment.environment": query.environment or "",
        }
        if query.service_namespace is not None:
            tags["resource_attr:service.namespace"] = query.service_namespace
        if query.instance_id is not None:
            tags["resource_attr:service.instance.id"] = query.instance_id

        payload = self._request_json(
            "/select/jaeger/api/traces",
            params={
                "service": query.service_name,
                "tags": json.dumps(tags, ensure_ascii=False, separators=(",", ":")),
                "start": int(query.started_at.timestamp() * 1_000_000),
                "end": int(ended_at.timestamp() * 1_000_000),
                "limit": query.limit + 1,
            },
        )
        raw_traces = payload.get("data", [])
        if not isinstance(raw_traces, list):
            raise TelemetryStoreUnavailable("VictoriaTraces 返回了无效的搜索结果")

        summaries: list[TraceSummary] = []
        for raw_trace in raw_traces[: query.limit + 1]:
            detail = self._parse_trace(raw_trace)
            if detail is None:
                continue
            matching_span = self._matching_span(detail, query)
            if matching_span is None:
                continue
            summaries.append(self._summary(detail, matching_span))
        summaries.sort(key=lambda item: (item.started_at, item.trace_id), reverse=True)

        page_items = tuple(summaries[: query.limit])
        next_cursor = _encode_cursor(page_items[-1].started_at) if len(summaries) > query.limit and page_items else None
        return TracePage(items=page_items, next_cursor=next_cursor)

    def get_trace(self, trace_id: str) -> TraceDetail | None:
        payload = self._request_json(f"/select/jaeger/api/traces/{trace_id}", allow_not_found=True)
        if payload is None:
            return None
        raw_traces = payload.get("data", [])
        if not isinstance(raw_traces, list) or not raw_traces:
            return None
        return self._parse_trace(raw_traces[0])

    def service_red(self, query: ServiceMetricQuery) -> ServiceRed:
        window_seconds = _validate_window(query.started_at, query.ended_at)
        deduped = self._deduped_entry_query(query.service_namespace, query.service_name, query.environment)
        aggregate = (
            f"{self._bounded_spans(deduped)} | stats count() as requests, count() if (status_code:=\"2\") as errors, "
            "quantile(0.95, duration) as p95, quantile(0.99, duration) as p99"
        )
        values = self._ungrouped_values(self._stats(aggregate, query.started_at, query.ended_at))
        requests_count = values.get("requests")
        if requests_count is None or requests_count <= 0:
            return ServiceRed(None, None, None, None)
        self._reject_truncated_unique_spans(deduped, requests_count, query.started_at, query.ended_at)
        errors_count = values.get("errors", 0.0)
        timeseries: tuple[ServiceRedPoint, ...] = ()
        endpoints: tuple[ServiceEndpointRed, ...] = ()
        if query.include_breakdown:
            step = max(15, math.ceil(window_seconds / (MAX_RED_POINTS - 1)))
            range_aggregate = (
                f"{deduped} | stats count() as requests, count() if (status_code:=\"2\") as errors, "
                "quantile(0.95, duration) as p95, quantile(0.99, duration) as p99"
            )
            ranged = self._range_values(
                self._stats_range(range_aggregate, query.started_at, query.ended_at, step=step)
            )
            timeseries = tuple(
                ServiceRedPoint(
                    timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
                    request_rate=count / step,
                    error_rate=ranged.get("errors", {}).get(timestamp, 0.0) / count if count > 0 else None,
                    p95_ms=self._nanoseconds_to_ms(ranged.get("p95", {}).get(timestamp)) if count > 0 else None,
                    p99_ms=self._nanoseconds_to_ms(ranged.get("p99", {}).get(timestamp)) if count > 0 else None,
                )
                for timestamp, count in list(ranged.get("requests", {}).items())[-MAX_RED_POINTS:]
            )
            endpoint_query = (
                f"{self._bounded_spans(self._deduped_entry_query(query.service_namespace, query.service_name, query.environment, keep_name=True))} "
                "| stats by (endpoint) count() as requests, count() if (status_code:=\"2\") as errors, "
                "quantile(0.95, duration) as p95, quantile(0.99, duration) as p99 "
                f"| sort by (requests) desc | limit {MAX_TOP_ENDPOINTS}"
            )
            endpoints = self._endpoint_red(self._stats(endpoint_query, query.started_at, query.ended_at), window_seconds)
        return ServiceRed(
            request_rate=requests_count / window_seconds,
            error_rate=errors_count / requests_count,
            p95_ms=self._nanoseconds_to_ms(values.get("p95")),
            p99_ms=self._nanoseconds_to_ms(values.get("p99")),
            timeseries=timeseries,
            top_endpoints=endpoints,
        )

    def slo_measurement(self, query: SloMetricQuery) -> SloMeasurement:
        window_seconds = _validate_window(query.started_at, query.ended_at)
        deduped = self._deduped_entry_query(
            query.service_namespace,
            query.service_name,
            query.environment,
            endpoint=query.endpoint,
        )
        if query.sli_type == "availability":
            final = "count() as total, count() if (status_code:=\"2\") as bad"
            good_metric = None
        else:
            if query.latency_threshold_ms is None or query.latency_threshold_ms <= 0:
                raise ValueError("时延 SLO 必须提供正数阈值")
            threshold_ns = query.latency_threshold_ms * 1_000_000
            final = f"count() as total, count() if (duration:<={threshold_ns}) as good"
            good_metric = "good"
        values = self._ungrouped_values(
            self._stats(f"{self._bounded_spans(deduped)} | stats {final}", query.started_at, query.ended_at)
        )
        total = values.get("total")
        if total is None or total <= 0:
            return SloMeasurement(None, None, None, MetricDataState.NO_DATA)
        self._reject_truncated_unique_spans(deduped, total, query.started_at, query.ended_at)
        good = values.get(good_metric, 0.0) if good_metric else max(0.0, total - values.get("bad", 0.0))
        return SloMeasurement(
            compliance_percent=min(100.0, max(0.0, good / total * 100)),
            good_rate=good / window_seconds,
            total_rate=total / window_seconds,
            data_state=MetricDataState.AVAILABLE,
        )

    def instance_activity(self, query: InstanceActivityQuery) -> list[InstanceActivity]:
        _validate_window(query.started_at, query.ended_at)
        logs_query = (
            f"{_SERVICE_FIELD}:* | stats by ({_NAMESPACE_FIELD}, {_SERVICE_FIELD}, {_INSTANCE_FIELD}, "
            f"{_ENVIRONMENT_FIELD}, {_VERSION_FIELD}) max(end_time_unix_nano) as last_seen "
            f"| sort by (last_seen) desc | limit {MAX_ACTIVITY_DIMENSIONS + 1}"
        )
        rows = self._query_rows(logs_query, query.started_at, query.ended_at)
        if len(rows) > MAX_ACTIVITY_DIMENSIONS:
            raise TelemetryStoreUnavailable("APM 活动维度超过单次对账上限")
        activities: list[InstanceActivity] = []
        for row in rows:
            service_name = str(row.get("resource_attr:service.name", "")).strip()
            last_seen = _number(row.get("last_seen"))
            if not service_name or last_seen is None:
                continue
            try:
                last_seen_at = datetime.fromtimestamp(last_seen / 1_000_000_000, tz=UTC)
            except (OverflowError, OSError, ValueError):
                continue
            instance_id = str(row.get("resource_attr:service.instance.id", "")).strip() or None
            activities.append(
                InstanceActivity(
                    service_namespace=str(row.get("resource_attr:service.namespace", "")),
                    service_name=service_name,
                    instance_id=instance_id,
                    environment=str(row.get("resource_attr:deployment.environment", "")),
                    version=str(row.get("resource_attr:service.version", "")),
                    last_seen_at=last_seen_at,
                )
            )
        return activities

    def service_dependencies(self, query: TopologyDependencyQuery) -> tuple[ServiceDependency, ...]:
        _validate_window(query.started_at, query.ended_at, maximum=MAX_TOPOLOGY_WINDOW)
        payload = self._request_json(
            "/select/jaeger/api/dependencies",
            params={
                "endTs": int(query.ended_at.timestamp() * 1_000),
                "lookback": int((query.ended_at - query.started_at).total_seconds() * 1_000),
            },
        )
        data = payload.get("data", [])
        if not isinstance(data, list) or len(data) > MAX_DEPENDENCIES:
            raise TelemetryStoreUnavailable("VictoriaTraces 服务依赖结果超过上限或格式无效")
        dependencies: list[ServiceDependency] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            parent = str(item.get("parent", "")).strip()
            child = str(item.get("child", "")).strip()
            try:
                calls = int(item.get("callCount", 0))
            except (TypeError, ValueError):
                continue
            if parent and child and calls > 0:
                dependencies.append(ServiceDependency(parent, child, calls))
        return tuple(dependencies)

    def _deduped_entry_query(
        self,
        namespace: str,
        service_name: str,
        environment: str,
        *,
        endpoint: str = "",
        keep_name: bool = False,
    ) -> str:
        filters = [
            "*",
            f"{_NAMESPACE_FIELD}:={_logsql_string(namespace)}",
            f"{_SERVICE_FIELD}:={_logsql_string(service_name)}",
            f"{_ENVIRONMENT_FIELD}:={_logsql_string(environment)}",
            'kind:in("2","5")',
        ]
        if endpoint:
            filters.append(f"name:={_logsql_string(endpoint)}")
        fields = "max(duration) as duration, max(status_code) as status_code"
        if keep_name:
            fields += ", max(name) as endpoint"
        return f"{' '.join(filters)} | stats by (trace_id, span_id) {fields}"

    @staticmethod
    def _bounded_spans(deduped_query: str) -> str:
        return f"{deduped_query} | limit {MAX_UNIQUE_SPANS}"

    def _reject_truncated_unique_spans(
        self,
        deduped_query: str,
        observed_count: float,
        started_at: datetime,
        ended_at: datetime,
    ) -> None:
        if observed_count < MAX_UNIQUE_SPANS:
            return
        count_query = (
            f"{deduped_query} | limit {MAX_UNIQUE_SPANS + 1} | stats count() as unique_spans"
        )
        values = self._ungrouped_values(self._stats(count_query, started_at, ended_at))
        if values.get("unique_spans", 0) > MAX_UNIQUE_SPANS:
            raise TelemetryStoreUnavailable("APM 查询唯一 Span 数超过单次聚合上限")

    def _stats(self, query: str, started_at: datetime, ended_at: datetime) -> list[dict[str, Any]]:
        payload = self._request_json(
            "/select/logsql/stats_query",
            params={"query": query, "start": started_at.isoformat(), "end": ended_at.isoformat()},
        )
        return self._stats_result(payload, expected_type="vector")

    def _stats_range(
        self,
        query: str,
        started_at: datetime,
        ended_at: datetime,
        *,
        step: int,
    ) -> list[dict[str, Any]]:
        payload = self._request_json(
            "/select/logsql/stats_query_range",
            params={
                "query": query,
                "start": started_at.isoformat(),
                "end": ended_at.isoformat(),
                "step": f"{step}s",
            },
        )
        return self._stats_result(payload, expected_type="matrix")

    @staticmethod
    def _stats_result(payload: dict[str, Any], *, expected_type: str) -> list[dict[str, Any]]:
        data = payload.get("data", {})
        result = data.get("result", []) if isinstance(data, dict) else None
        if payload.get("status") != "success" or data.get("resultType") != expected_type or not isinstance(result, list):
            raise TelemetryStoreUnavailable("VictoriaTraces 返回了无效的 LogsQL 聚合结果")
        return [item for item in result if isinstance(item, dict)]

    def _query_rows(self, query: str, started_at: datetime, ended_at: datetime) -> list[dict[str, Any]]:
        raw = self._request_bytes(
            "/select/logsql/query",
            params={
                "query": query,
                "start": started_at.isoformat(),
                "end": ended_at.isoformat(),
                "limit": MAX_ACTIVITY_DIMENSIONS + 1,
            },
        )
        rows: list[dict[str, Any]] = []
        try:
            for line in raw.splitlines():
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
        except (UnicodeDecodeError, ValueError) as exc:
            raise TelemetryStoreUnavailable("VictoriaTraces 返回了无效的 LogsQL 行结果") from exc
        return rows

    @staticmethod
    def _ungrouped_values(result: list[dict[str, Any]]) -> dict[str, float]:
        values: dict[str, float] = {}
        for series in result:
            metric = series.get("metric", {})
            raw_value = series.get("value", [])
            if not isinstance(metric, dict) or not isinstance(raw_value, list) or len(raw_value) != 2:
                continue
            name = str(metric.get("__name__", ""))
            parsed = _number(raw_value[1])
            if name and parsed is not None:
                values[name] = parsed
        return values

    @staticmethod
    def _range_values(result: list[dict[str, Any]]) -> dict[str, dict[float, float]]:
        parsed: dict[str, dict[float, float]] = {}
        for series in result:
            metric = series.get("metric", {})
            values = series.get("values", [])
            if not isinstance(metric, dict) or not isinstance(values, list):
                continue
            name = str(metric.get("__name__", ""))
            if not name:
                continue
            points: dict[float, float] = {}
            for item in values:
                if not isinstance(item, list) or len(item) != 2:
                    continue
                timestamp = _number(item[0])
                value = _number(item[1])
                if timestamp is not None and value is not None:
                    points[timestamp] = value
            parsed[name] = dict(sorted(points.items())[-MAX_RED_POINTS:])
        return parsed

    @staticmethod
    def _endpoint_red(result: list[dict[str, Any]], window_seconds: int) -> tuple[ServiceEndpointRed, ...]:
        grouped: dict[str, dict[str, float]] = {}
        for series in result:
            metric = series.get("metric", {})
            raw_value = series.get("value", [])
            if not isinstance(metric, dict) or not isinstance(raw_value, list) or len(raw_value) != 2:
                continue
            endpoint = str(metric.get("endpoint", "")).strip()[:MAX_ENDPOINT_NAME_LENGTH]
            name = str(metric.get("__name__", ""))
            value = _number(raw_value[1])
            if endpoint and name and value is not None:
                grouped.setdefault(endpoint, {})[name] = value
        endpoints: list[ServiceEndpointRed] = []
        for endpoint, values in grouped.items():
            count = values.get("requests")
            if count is None or count <= 0:
                continue
            endpoints.append(
                ServiceEndpointRed(
                    endpoint=endpoint,
                    request_rate=count / window_seconds,
                    error_rate=values.get("errors", 0.0) / count,
                    p95_ms=VictoriaTracesTelemetryStore._nanoseconds_to_ms(values.get("p95")),
                    p99_ms=VictoriaTracesTelemetryStore._nanoseconds_to_ms(values.get("p99")),
                )
            )
        return tuple(sorted(endpoints, key=lambda item: (-item.request_rate, item.endpoint))[:MAX_TOP_ENDPOINTS])

    @staticmethod
    def _nanoseconds_to_ms(value: float | None) -> float | None:
        return value / 1_000_000 if value is not None else None

    def _request_json(
        self,
        path: str,
        *,
        params: dict[str, object] | None = None,
        allow_not_found: bool = False,
    ) -> dict[str, Any] | None:
        raw = self._request_bytes(path, params=params, allow_not_found=allow_not_found)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, ValueError) as exc:
            raise TelemetryStoreUnavailable("VictoriaTraces 返回了无效 JSON") from exc
        if not isinstance(payload, dict):
            raise TelemetryStoreUnavailable("VictoriaTraces 返回了无效响应")
        return payload

    def _request_bytes(
        self,
        path: str,
        *,
        params: dict[str, object] | None = None,
        allow_not_found: bool = False,
    ) -> bytes | None:
        response = None
        try:
            response = self.session.get(
                f"{self.endpoint}{path}",
                params=params,
                timeout=self.timeout,
                verify=self.verify,
                auth=self.auth,
                headers={"Accept": "application/json"},
                stream=True,
            )
            if allow_not_found and response.status_code == 404:
                return None
            response.raise_for_status()
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_RESPONSE_BYTES:
                raise TelemetryStoreUnavailable("VictoriaTraces 响应超过大小上限")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise TelemetryStoreUnavailable("VictoriaTraces 响应超过大小上限")
                chunks.append(chunk)
            return b"".join(chunks)
        except TelemetryStoreUnavailable:
            raise
        except (requests.RequestException, TypeError, ValueError) as exc:
            raise TelemetryStoreUnavailable("VictoriaTraces 查询不可用") from exc
        finally:
            if response is not None:
                response.close()

    def _parse_trace(self, raw_trace: object) -> TraceDetail | None:
        if not isinstance(raw_trace, dict):
            return None
        trace_id = str(raw_trace.get("traceID", ""))
        raw_spans = raw_trace.get("spans", [])
        processes = raw_trace.get("processes", {})
        if not trace_id or not isinstance(raw_spans, list) or not isinstance(processes, dict):
            return None

        spans_by_id: dict[str, SpanDetail] = {}
        for raw_span in raw_spans[:_RAW_SPAN_PARSE_LIMIT]:
            if not isinstance(raw_span, dict):
                continue
            process = processes.get(raw_span.get("processID"), {})
            process = process if isinstance(process, dict) else {}
            resource_attributes = _tag_map(process.get("tags"))
            service_name = str(process.get("serviceName") or resource_attributes.get("service.name") or "")
            attributes = {**resource_attributes, **_tag_map(raw_span.get("tags"))}
            started_at = datetime.fromtimestamp(float(raw_span.get("startTime", 0)) / 1_000_000, tz=UTC)
            references = raw_span.get("references", [])
            parent_span_id = None
            if isinstance(references, list):
                parent = next(
                    (item for item in references if isinstance(item, dict) and str(item.get("refType", "")).upper() == "CHILD_OF"),
                    None,
                )
                if parent is not None:
                    parent_span_id = str(parent.get("spanID") or "") or None
            span_id = str(raw_span.get("spanID", ""))
            if not span_id or span_id in spans_by_id:
                continue
            spans_by_id[span_id] = SpanDetail(
                span_id=span_id,
                parent_span_id=parent_span_id,
                name=str(raw_span.get("operationName", "")),
                started_at=started_at,
                duration_ms=float(raw_span.get("duration", 0)) / 1000,
                status=_status_from_tags(attributes),
                attributes=attributes,
                service_namespace=str(resource_attributes.get("service.namespace", "")),
                service_name=service_name,
                environment=str(
                    resource_attributes.get(
                        "deployment.environment",
                        resource_attributes.get("deployment.environment.name", ""),
                    )
                ),
                instance_id=str(resource_attributes.get("service.instance.id") or "") or None,
                kind=str(attributes.get("span.kind", "unspecified")).removeprefix("SPAN_KIND_").casefold(),
            )
        spans = list(spans_by_id.values())
        if not spans:
            return None
        spans.sort(key=lambda item: (item.started_at, item.span_id))
        root = next((item for item in spans if item.parent_span_id is None), spans[0])
        return TraceDetail(
            trace_id=trace_id,
            spans=tuple(spans),
            service_namespace=root.service_namespace,
            service_name=root.service_name,
            environment=root.environment,
            instance_id=root.instance_id,
            truncated=len(raw_spans) > _RAW_SPAN_PARSE_LIMIT,
        )

    @staticmethod
    def _matching_span(detail: TraceDetail, query: TraceSearchQuery) -> SpanDetail | None:
        for span in detail.spans:
            if normalize_identity(span.service_name) != normalize_identity(query.service_name or ""):
                continue
            if query.service_namespace is not None and normalize_identity(span.service_namespace) != normalize_identity(query.service_namespace):
                continue
            if span.environment != query.environment:
                continue
            if query.instance_id is not None and span.instance_id != query.instance_id:
                continue
            return span
        return None

    @staticmethod
    def _summary(detail: TraceDetail, matching_span: SpanDetail) -> TraceSummary:
        started_at = min(span.started_at for span in detail.spans)
        ended_at = max(span.started_at + timedelta(milliseconds=span.duration_ms) for span in detail.spans)
        root = next((span for span in detail.spans if span.parent_span_id is None), detail.spans[0])
        return TraceSummary(
            trace_id=detail.trace_id,
            started_at=started_at,
            duration_ms=max(0, (ended_at - started_at).total_seconds() * 1000),
            service_namespace=matching_span.service_namespace,
            service_name=matching_span.service_name,
            environment=matching_span.environment,
            instance_id=matching_span.instance_id,
            status="error" if any(span.status == "error" for span in detail.spans) else "ok",
            root_span_name=root.name,
            span_count=len(detail.spans),
        )


# 兼容旧导入名；生产 wiring 已统一使用 TelemetryStore。
VictoriaTracesTraceStore = VictoriaTracesTelemetryStore
