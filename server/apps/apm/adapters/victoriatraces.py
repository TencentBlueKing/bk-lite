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
    DeploymentReleaseQuery,
    InferredDeploymentRelease,
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
    SpanPage,
    SpanSearchQuery,
    SpanSummary,
    TopologyDependencyQuery,
    TopologySampleQuery,
    TopologyTraceSample,
    TraceDetail,
    TracePage,
    TraceSearchQuery,
    TraceSummary,
)
from apps.apm.services.identity import normalize_identity
from apps.core.logger import apm_logger as logger

MAX_QUERY_WINDOW = timedelta(days=35)
MAX_TOPOLOGY_WINDOW = timedelta(days=7)
MAX_DEPLOYMENT_LOOKBACK = timedelta(days=7)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_UNIQUE_SPANS = 1_000_000
MAX_ACTIVITY_DIMENSIONS = 10_000
MAX_DEPLOYMENT_RELEASES = 10_000
MAX_DEPENDENCIES = 10_000
MAX_TOPOLOGY_SAMPLE_TRACES = 200
MAX_TOPOLOGY_SAMPLE_SPANS = 20_000
MAX_RED_POINTS = 120
MAX_TOP_ENDPOINTS = 10
MAX_ENDPOINT_NAME_LENGTH = 256
_RAW_SPAN_PARSE_LIMIT = 1001

_NAMESPACE_FIELD = "`resource_attr:service.namespace`"
_SERVICE_FIELD = "`resource_attr:service.name`"
_INSTANCE_FIELD = "`resource_attr:service.instance.id`"
_ENVIRONMENT_FIELD = "`resource_attr:deployment.environment`"
_VERSION_FIELD = "`resource_attr:service.version`"
_LANGUAGE_FIELD = "`resource_attr:telemetry.sdk.language`"
_KIND_TO_CODE = {
    "internal": "1",
    "server": "2",
    "client": "3",
    "producer": "4",
    "consumer": "5",
}
_CODE_TO_KIND = {code: name for name, code in _KIND_TO_CODE.items()}
_STATUS_TO_CODE = {"ok": "1", "error": "2"}
_MAX_SPAN_SEARCH_LIMIT = 200
_HTTP_METHOD_FIELDS = ("span_attr:http.request.method", "span_attr:http.method")
_HTTP_STATUS_FIELDS = ("span_attr:http.response.status_code", "span_attr:http.status_code")


def _tag_map(tags: object) -> dict[str, object]:
    if not isinstance(tags, list):
        return {}
    result: dict[str, object] = {}
    for tag in tags:
        if isinstance(tag, dict) and isinstance(tag.get("key"), str):
            result[tag["key"]] = tag.get("value")
    return result


def _exception_event_attributes(logs: object) -> dict[str, object]:
    """从 Jaeger logs 中提取 OTel exception Span Event 的受控字段。"""

    if not isinstance(logs, list):
        return {}
    result: dict[str, object] = {}
    for log in logs[:32]:
        if not isinstance(log, dict):
            continue
        fields = _tag_map(log.get("fields"))
        if str(fields.get("event", fields.get("name", ""))).casefold() != "exception" and not any(
            key in fields for key in ("exception.type", "exception.message", "exception.stacktrace")
        ):
            continue
        for key in ("exception.type", "exception.message", "exception.stacktrace"):
            if key in fields:
                result[f"event_attr:{key}"] = fields[key]
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
        self.endpoint = (
            endpoint
            or os.getenv("VICTORIATRACES_HOST")
            or os.getenv("APM_VICTORIATRACES_QUERY_ENDPOINT")
            or "http://127.0.0.1:10428"
        ).rstrip("/")
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
        if query.service_name is None:
            return self._search_unscoped_traces(query)
        ended_at = min(query.ended_at, _decode_cursor(query.cursor)) if query.cursor else query.ended_at
        tags: dict[str, str] = {}
        if query.environment is not None:
            tags["resource_attr:deployment.environment"] = query.environment
        if query.service_namespace is not None:
            tags["resource_attr:service.namespace"] = query.service_namespace
        if query.instance_id is not None:
            tags["resource_attr:service.instance.id"] = query.instance_id
        if query.status == "error":
            tags["error"] = "true"

        params: dict[str, object] = {
            "service": query.service_name,
            "tags": json.dumps(tags, ensure_ascii=False, separators=(",", ":")),
            "start": int(query.started_at.timestamp() * 1_000_000),
            "end": int(ended_at.timestamp() * 1_000_000),
            "limit": query.limit + 1,
        }
        if query.span_name:
            params["operation"] = query.span_name
        if query.min_duration_ms is not None:
            params["minDuration"] = f"{int(query.min_duration_ms * 1_000_000)}ns"
        if query.max_duration_ms is not None:
            params["maxDuration"] = f"{int(query.max_duration_ms * 1_000_000)}ns"

        payload = self._request_json("/select/jaeger/api/traces", params=params)
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

    def _search_unscoped_traces(self, query: TraceSearchQuery) -> TracePage:
        """空服务检索先按 trace_id 有界聚合，避免同一 Trace 跨页重复。"""

        ended_at = min(query.ended_at, _decode_cursor(query.cursor)) if query.cursor else query.ended_at
        filters = ["*"]
        if query.service_namespace is not None:
            filters.append(f"{_NAMESPACE_FIELD}:={_logsql_string(query.service_namespace)}")
        if query.environment is not None:
            filters.append(f"{_ENVIRONMENT_FIELD}:={_logsql_string(query.environment)}")
        if query.instance_id is not None:
            filters.append(f"{_INSTANCE_FIELD}:={_logsql_string(query.instance_id)}")
        if query.span_name:
            filters.append(f"name:={_logsql_string(query.span_name)}")
        if query.status is not None:
            filters.append(f"status_code:={_logsql_string(_STATUS_TO_CODE[query.status])}")
        if query.min_duration_ms is not None:
            filters.append(f"duration:>={int(query.min_duration_ms * 1_000_000)}")
        if query.max_duration_ms is not None:
            filters.append(f"duration:<={int(query.max_duration_ms * 1_000_000)}")
        logs_query = (
            f"{' '.join(filters)} | stats by (trace_id) max(start_time_unix_nano) as matched_at "
            f"| sort by (matched_at) desc | limit {query.limit + 1}"
        )
        rows = self._query_rows(logs_query, query.started_at, ended_at, limit=query.limit + 1)
        summaries: list[tuple[datetime, TraceSummary]] = []
        for row in rows:
            trace_id = str(row.get("trace_id", "")).strip()
            matched_at_ns = _number(row.get("matched_at"))
            if not trace_id or matched_at_ns is None:
                continue
            try:
                matched_at = datetime.fromtimestamp(matched_at_ns / 1_000_000_000, tz=UTC)
            except (OverflowError, OSError, ValueError):
                continue
            detail = self.get_trace(trace_id)
            if detail is None:
                continue
            matching_span = self._matching_span(detail, query)
            if matching_span is not None:
                summaries.append((matched_at, self._summary(detail, matching_span)))
        summaries.sort(key=lambda item: (item[0], item[1].trace_id), reverse=True)
        page_pairs = summaries[: query.limit]
        page_items = tuple(summary for _, summary in page_pairs)
        next_cursor = _encode_cursor(page_pairs[-1][0]) if len(summaries) > query.limit and page_pairs else None
        return TracePage(items=page_items, next_cursor=next_cursor)

    def search_spans(self, query: SpanSearchQuery) -> SpanPage:
        _validate_window(query.started_at, query.ended_at)
        if not 1 <= query.limit <= _MAX_SPAN_SEARCH_LIMIT:
            raise ValueError(f"Span 查询 limit 必须在 1 到 {_MAX_SPAN_SEARCH_LIMIT} 之间")
        if query.status is not None and query.status not in _STATUS_TO_CODE:
            raise ValueError("status 仅支持 ok 或 error")
        if query.kind is not None and query.kind not in _KIND_TO_CODE:
            raise ValueError("Span kind 无效")
        if query.min_duration_ms is not None and query.min_duration_ms < 0:
            raise ValueError("min_duration_ms 不能为负数")
        if query.max_duration_ms is not None and query.max_duration_ms < 0:
            raise ValueError("max_duration_ms 不能为负数")
        if query.min_duration_ms is not None and query.max_duration_ms is not None and query.min_duration_ms > query.max_duration_ms:
            raise ValueError("min_duration_ms 不能大于 max_duration_ms")

        ended_at = min(query.ended_at, _decode_cursor(query.cursor)) if query.cursor else query.ended_at
        filters = ["*"]
        if query.service_name is not None:
            filters.append(f"{_SERVICE_FIELD}:={_logsql_string(query.service_name)}")
        if query.environment is not None:
            filters.append(f"{_ENVIRONMENT_FIELD}:={_logsql_string(query.environment)}")
        if query.service_namespace is not None:
            filters.append(f"{_NAMESPACE_FIELD}:={_logsql_string(query.service_namespace)}")
        if query.instance_id is not None:
            filters.append(f"{_INSTANCE_FIELD}:={_logsql_string(query.instance_id)}")
        if query.span_name:
            filters.append(f"name:={_logsql_string(query.span_name)}")
        if query.status is not None:
            filters.append(f"status_code:={_logsql_string(_STATUS_TO_CODE[query.status])}")
        if query.kind is not None:
            filters.append(f"kind:={_logsql_string(_KIND_TO_CODE[query.kind])}")
        if query.min_duration_ms is not None:
            filters.append(f"duration:>={int(query.min_duration_ms * 1_000_000)}")
        if query.max_duration_ms is not None:
            filters.append(f"duration:<={int(query.max_duration_ms * 1_000_000)}")

        logs_query = f"{' '.join(filters)} | sort by (_time) desc | limit {query.limit + 1}"
        rows = self._query_rows(logs_query, query.started_at, ended_at, limit=query.limit + 1)
        items: list[SpanSummary] = []
        for row in rows:
            summary = self._span_summary_from_row(row)
            if summary is not None:
                items.append(summary)
        items.sort(key=lambda item: (item.started_at, item.span_id), reverse=True)
        page_items = tuple(items[: query.limit])
        next_cursor = _encode_cursor(page_items[-1].started_at) if len(items) > query.limit and page_items else None
        return SpanPage(items=page_items, next_cursor=next_cursor)

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
        deduped = self._deduped_entry_query(
            query.service_namespace,
            query.service_name,
            query.environment,
            endpoint=query.endpoint,
            version=query.version,
        )
        aggregate = (
            f'{self._bounded_spans(deduped)} | stats count() as requests, count() if (status_code:="2") as errors, '
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
                f'{deduped} | stats count() as requests, count() if (status_code:="2") as errors, '
                "quantile(0.95, duration) as p95, quantile(0.99, duration) as p99"
            )
            ranged = self._range_values(self._stats_range(range_aggregate, query.started_at, query.ended_at, step=step))
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
            endpoint_deduped = self._deduped_entry_query(
                query.service_namespace,
                query.service_name,
                query.environment,
                endpoint=query.endpoint,
                version=query.version,
                keep_name=True,
            )
            endpoint_query = (
                f"{self._bounded_spans(endpoint_deduped)} "
                '| stats by (endpoint) count() as requests, count() if (status_code:="2") as errors, '
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
            final = 'count() as total, count() if (status_code:="2") as bad'
            good_metric = None
        else:
            if query.latency_threshold_ms is None or query.latency_threshold_ms <= 0:
                raise ValueError("时延 SLO 必须提供正数阈值")
            threshold_ns = query.latency_threshold_ms * 1_000_000
            final = f"count() as total, count() if (duration:<={threshold_ns}) as good"
            good_metric = "good"
        values = self._ungrouped_values(self._stats(f"{self._bounded_spans(deduped)} | stats {final}", query.started_at, query.ended_at))
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
            f"{_ENVIRONMENT_FIELD}, {_VERSION_FIELD}, {_LANGUAGE_FIELD}) max(end_time_unix_nano) as last_seen "
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
                    language=str(row.get("resource_attr:telemetry.sdk.language", "")),
                )
            )
        return activities

    def deployment_releases(self, query: DeploymentReleaseQuery) -> list[InferredDeploymentRelease]:
        _validate_window(query.started_at, query.ended_at, maximum=MAX_DEPLOYMENT_LOOKBACK)
        logs_query = (
            f"{_SERVICE_FIELD}:* | stats by ({_NAMESPACE_FIELD}, {_SERVICE_FIELD}, "
            f"{_ENVIRONMENT_FIELD}, {_VERSION_FIELD}) "
            "min(start_time_unix_nano) as first_seen, max(end_time_unix_nano) as last_seen "
            f'| filter {_VERSION_FIELD}:!="" '
            f"| sort by (first_seen) desc | limit {MAX_DEPLOYMENT_RELEASES + 1}"
        )
        rows = self._query_rows(logs_query, query.started_at, query.ended_at)
        if len(rows) > MAX_DEPLOYMENT_RELEASES:
            raise TelemetryStoreUnavailable("APM 部署版本维度超过单次聚合上限")
        releases: list[InferredDeploymentRelease] = []
        for row in rows:
            service_name = str(row.get("resource_attr:service.name", "")).strip()
            version = str(row.get("resource_attr:service.version", "")).strip()
            if not service_name or not version:
                continue
            first_seen = _number(row.get("first_seen"))
            last_seen = _number(row.get("last_seen"))
            if first_seen is None or last_seen is None:
                continue
            try:
                first_seen_at = datetime.fromtimestamp(first_seen / 1_000_000_000, tz=UTC)
                last_seen_at = datetime.fromtimestamp(last_seen / 1_000_000_000, tz=UTC)
            except (OverflowError, OSError, ValueError):
                continue
            releases.append(
                InferredDeploymentRelease(
                    service_namespace=str(row.get("resource_attr:service.namespace", "")),
                    service_name=service_name,
                    environment=str(row.get("resource_attr:deployment.environment", "")),
                    version=version,
                    first_seen_at=first_seen_at,
                    last_seen_at=last_seen_at,
                )
            )
        return releases

    def sample_traces(self, query: TopologySampleQuery) -> TopologyTraceSample:
        _validate_window(query.started_at, query.ended_at, maximum=MAX_TOPOLOGY_WINDOW)
        if query.limit < 1 or query.limit > MAX_TOPOLOGY_SAMPLE_TRACES:
            raise ValueError(f"拓扑样本 limit 必须在 1 到 {MAX_TOPOLOGY_SAMPLE_TRACES} 之间")
        if query.status is not None and query.status not in _STATUS_TO_CODE:
            raise ValueError("status 仅支持 ok 或 error")
        if query.min_duration_ms is not None and query.min_duration_ms < 0:
            raise ValueError("min_duration_ms 不能为负数")
        if not query.service_names:
            return TopologyTraceSample((), False)

        filters = ["*", self._service_name_filter(query.service_names)]
        if query.environment is not None:
            filters.append(f"{_ENVIRONMENT_FIELD}:={_logsql_string(query.environment)}")
        if query.span_name:
            filters.append(f"name:={_logsql_string(query.span_name)}")
        if query.status == "error":
            filters.append(f"status_code:={_logsql_string(_STATUS_TO_CODE[query.status])}")
        if query.min_duration_ms is not None:
            filters.append(f"duration:>={int(query.min_duration_ms * 1_000_000)}")
        logs_query = (
            f"{' '.join(filters)} | stats by (trace_id) max(start_time_unix_nano) as matched_at "
            f"| sort by (matched_at) desc | limit {query.limit + 1}"
        )
        rows = self._query_rows(logs_query, query.started_at, query.ended_at, limit=query.limit + 1)
        trace_ids: list[str] = []
        seen: set[str] = set()
        for row in rows:
            trace_id = str(row.get("trace_id", "")).strip()
            if not trace_id or trace_id in seen:
                continue
            seen.add(trace_id)
            trace_ids.append(trace_id)
        truncated = len(trace_ids) > query.limit
        selected_ids = trace_ids[: query.limit]
        traces, omitted = self._fetch_topology_traces(
            selected_ids,
            started_at=query.started_at,
            ended_at=query.ended_at,
        )
        return TopologyTraceSample(traces=tuple(traces), truncated=truncated, omitted_trace_fetches=omitted)

    def _fetch_topology_traces(
        self,
        trace_ids: list[str],
        *,
        started_at: datetime,
        ended_at: datetime,
    ) -> tuple[list[TraceDetail], int]:
        """一次 LogsQL 拉回样本 Trace 的 Span，避免逐条打 Jaeger get_trace。"""

        if not trace_ids:
            return [], 0
        quoted = ",".join(_logsql_string(trace_id) for trace_id in trace_ids)
        logs_query = f"trace_id:in({quoted}) | limit {MAX_TOPOLOGY_SAMPLE_SPANS}"
        try:
            rows = self._query_rows(logs_query, started_at, ended_at, limit=MAX_TOPOLOGY_SAMPLE_SPANS)
        except TelemetryStoreUnavailable as exc:
            logger.warning(
                "event=apm_topology_trace_fetch_failed failed_stage=sample_spans error_type=%s",
                type(exc).__name__,
            )
            return [], len(trace_ids)
        traces_by_id = self._traces_from_span_rows(rows)
        traces: list[TraceDetail] = []
        omitted = 0
        for trace_id in trace_ids:
            detail = traces_by_id.get(trace_id)
            if detail is None:
                omitted += 1
                continue
            traces.append(detail)
        return traces, omitted

    @classmethod
    def _traces_from_span_rows(cls, rows: list[dict[str, Any]]) -> dict[str, TraceDetail]:
        grouped: dict[str, list[SpanDetail]] = {}
        truncated_ids: set[str] = set()
        for row in rows:
            trace_id = str(row.get("trace_id", "")).strip()
            if not trace_id:
                continue
            spans = grouped.setdefault(trace_id, [])
            if len(spans) >= _RAW_SPAN_PARSE_LIMIT:
                truncated_ids.add(trace_id)
                continue
            span = cls._span_detail_from_row(row)
            if span is None:
                continue
            if any(item.span_id == span.span_id for item in spans):
                continue
            spans.append(span)
        traces: dict[str, TraceDetail] = {}
        for trace_id, spans in grouped.items():
            if not spans:
                continue
            spans.sort(key=lambda item: (item.started_at, item.span_id))
            root = next((item for item in spans if item.parent_span_id is None), spans[0])
            traces[trace_id] = TraceDetail(
                trace_id=trace_id,
                spans=tuple(spans),
                service_namespace=root.service_namespace,
                service_name=root.service_name,
                environment=root.environment,
                instance_id=root.instance_id,
                truncated=trace_id in truncated_ids,
            )
        return traces

    @staticmethod
    def _span_detail_from_row(row: dict[str, Any]) -> SpanDetail | None:
        span_id = str(row.get("span_id", "")).strip()
        service_name = str(row.get("resource_attr:service.name", "")).strip()
        if not span_id or not service_name:
            return None
        started_raw = _number(row.get("start_time_unix_nano"))
        if started_raw is None:
            return None
        try:
            started_at = datetime.fromtimestamp(started_raw / 1_000_000_000, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
        parent_span_id = str(row.get("parent_span_id", "")).strip()
        if not parent_span_id or set(parent_span_id) <= {"0"}:
            parent_span_id = None
        attributes = {
            key: value
            for key, value in row.items()
            if isinstance(key, str) and key.startswith(("span_attr:", "resource_attr:"))
        }
        return SpanDetail(
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=str(row.get("name", "")),
            started_at=started_at,
            duration_ms=(_number(row.get("duration")) or 0.0) / 1_000_000,
            status="error" if str(row.get("status_code", "")).strip() == "2" else "ok",
            attributes=attributes,
            service_namespace=str(row.get("resource_attr:service.namespace", "")),
            service_name=service_name,
            environment=str(row.get("resource_attr:deployment.environment", "")),
            instance_id=str(row.get("resource_attr:service.instance.id", "")).strip() or None,
            kind=_CODE_TO_KIND.get(str(row.get("kind", "")).strip(), "unspecified"),
        )

    @staticmethod
    def _service_name_filter(service_names: tuple[str, ...]) -> str:
        quoted = ",".join(_logsql_string(name) for name in service_names if name)
        return f"{_SERVICE_FIELD}:in({quoted})"

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
        version: str = "",
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
        if version:
            filters.append(f"{_VERSION_FIELD}:={_logsql_string(version)}")
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
        count_query = f"{deduped_query} | limit {MAX_UNIQUE_SPANS + 1} | stats count() as unique_spans"
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

    def _query_rows(
        self,
        query: str,
        started_at: datetime,
        ended_at: datetime,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        raw = self._request_bytes(
            "/select/logsql/query",
            params={
                "query": query,
                "start": started_at.isoformat(),
                "end": ended_at.isoformat(),
                "limit": limit if limit is not None else MAX_ACTIVITY_DIMENSIONS + 1,
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
            attributes = {
                **resource_attributes,
                **_tag_map(raw_span.get("tags")),
                **_exception_event_attributes(raw_span.get("logs")),
            }
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
    def _span_summary_from_row(row: dict[str, Any]) -> SpanSummary | None:
        trace_id = str(row.get("trace_id", "")).strip()
        span_id = str(row.get("span_id", "")).strip()
        service_name = str(row.get("resource_attr:service.name", "")).strip()
        if not trace_id or not span_id or not service_name:
            return None
        started_raw = _number(row.get("start_time_unix_nano"))
        if started_raw is None:
            return None
        try:
            started_at = datetime.fromtimestamp(started_raw / 1_000_000_000, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
        duration_ns = _number(row.get("duration")) or 0.0
        status_code = str(row.get("status_code", "")).strip()
        kind_code = str(row.get("kind", "")).strip()
        http_method = next(
            (str(row[field]).strip() for field in _HTTP_METHOD_FIELDS if str(row.get(field, "")).strip()),
            None,
        )
        http_status = next(
            (str(row[field]).strip() for field in _HTTP_STATUS_FIELDS if str(row.get(field, "")).strip()),
            None,
        )
        instance_id = str(row.get("resource_attr:service.instance.id", "")).strip() or None
        return SpanSummary(
            trace_id=trace_id,
            span_id=span_id,
            started_at=started_at,
            duration_ms=duration_ns / 1_000_000,
            service_namespace=str(row.get("resource_attr:service.namespace", "")),
            service_name=service_name,
            environment=str(row.get("resource_attr:deployment.environment", "")),
            instance_id=instance_id,
            status="error" if status_code == "2" else "ok",
            name=str(row.get("name", "")),
            kind=_CODE_TO_KIND.get(kind_code, "unspecified"),
            http_method=http_method,
            http_status_code=http_status,
        )

    @staticmethod
    def _matching_span(detail: TraceDetail, query: TraceSearchQuery) -> SpanDetail | None:
        for span in detail.spans:
            if query.service_name is not None and normalize_identity(span.service_name) != normalize_identity(query.service_name):
                continue
            if query.service_namespace is not None and normalize_identity(span.service_namespace) != normalize_identity(query.service_namespace):
                continue
            if query.environment is not None and span.environment != query.environment:
                continue
            if query.instance_id is not None and span.instance_id != query.instance_id:
                continue
            if query.span_name and span.name != query.span_name:
                continue
            if query.status and span.status != query.status:
                continue
            if query.min_duration_ms is not None and span.duration_ms < query.min_duration_ms:
                continue
            if query.max_duration_ms is not None and span.duration_ms > query.max_duration_ms:
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
