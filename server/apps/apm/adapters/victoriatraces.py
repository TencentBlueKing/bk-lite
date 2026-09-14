from __future__ import annotations

import base64
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from apps.apm.adapters.errors import TelemetryQueryTooLarge, TelemetryStoreUnavailable
from apps.apm.adapters.span_aliases import (
    DB_NAME_KEYS,
    DB_SYSTEM_KEYS,
    HOST_KEYS,
    HTTP_ENTRY_KEYS,
    MESSAGING_SYSTEM_KEYS,
    PEER_SERVICE_KEYS,
    PORT_KEYS,
    RPC_SERVICE_KEYS,
    RPC_SYSTEM_KEYS,
)
from apps.apm.services.contracts import (
    DeploymentReleaseQuery,
    InferredDeploymentRelease,
    InstanceActivity,
    InstanceActivityQuery,
    MetricDataState,
    ServiceDependency,
    ServiceEndpointRed,
    ServiceErrorBreakdown,
    ServiceErrorBreakdownQuery,
    ServiceErrorSampleTrace,
    ServiceFailedEndpoint,
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
from apps.apm.services.error_breakdown import (
    MAX_ERROR_TYPE_GROUPS,
    MAX_ERROR_TYPE_SAMPLES,
    MAX_FAILED_ENDPOINTS,
    RawErrorGroup,
    UNATTRIBUTED_ERROR_TYPE,
    attach_samples,
    merge_error_groups,
    rank_failed_endpoints,
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
# Java Span 常带 exception.stacktrace；200 条 Trace 一次拉全字段会超过 8MB。
TOPOLOGY_SPAN_FETCH_BATCH = 25
TOPOLOGY_SPAN_FETCH_SPAN_BUDGET = 4_000
TRACE_DETAIL_ATTR_BATCH = 100
ERROR_TYPE_SAMPLE_WORKERS = 4
RESPONSE_TOO_LARGE = "VictoriaTraces 响应超过大小上限"
QUERY_CAPACITY_REJECTED = "VictoriaTraces 拒绝了本次查询（超出单次查询容量），请缩小时间窗后重试"
# 全窗按 trace_id 分组的内存与分组数成正比；按窗口分层切片分别取样再轮转合并，
# 既避开 VT 单次查询内存上限，也让 15m/1h/1d/7d 覆盖不同时段而不是一律取最新 200 条。
SAMPLE_SLICE_QUARTER_HOUR = timedelta(minutes=15)
SAMPLE_SLICE_HOUR = timedelta(hours=1)
SAMPLE_SLICE_DAY = timedelta(days=1)
# 天级切片里 newest 201 条 Trace 落在最近几千条 Span 里；先 first 再 stats，
# 避免对切片内全部 Span 做 stats by (trace_id)（本机 1d 约 150 万行）。
SAMPLE_TRACE_ID_PROBE_SPANS = 5000
RED_EXACT_DEDUP_WINDOW = timedelta(days=1)
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
_TOPOLOGY_SPAN_CORE_FIELDS = (
    "trace_id",
    "span_id",
    "parent_span_id",
    "name",
    "kind",
    "status_code",
    "duration",
    "start_time_unix_nano",
    "resource_attr:service.namespace",
    "resource_attr:service.name",
    "resource_attr:deployment.environment",
    "resource_attr:service.instance.id",
)
_TOPOLOGY_SPAN_ATTR_KEYS = tuple(
    dict.fromkeys(
        (
            *DB_SYSTEM_KEYS,
            *DB_NAME_KEYS,
            *MESSAGING_SYSTEM_KEYS,
            *RPC_SYSTEM_KEYS,
            *RPC_SERVICE_KEYS,
            *PEER_SERVICE_KEYS,
            *HOST_KEYS,
            *PORT_KEYS,
            *HTTP_ENTRY_KEYS,
        )
    )
)
_EXCEPTION_TYPE_FIELD = "`event:event_attr:exception.type:0`"
_EXCEPTION_MESSAGE_FIELD = "`event:event_attr:exception.message:0`"
_SPAN_ERROR_TYPE_FIELD = "`span_attr:error.type`"
_HTTP_STATUS_FIELD = "`span_attr:http.response.status_code`"


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


def _logsql_field(name: str) -> str:
    if any(character in name for character in ".:-"):
        return f"`{name}`"
    return name


def _row_detail_attributes(row: dict[str, Any]) -> dict[str, object]:
    attributes: dict[str, object] = {}
    for key, value in row.items():
        if not isinstance(key, str):
            continue
        if key.startswith("span_attr:"):
            attributes[key.removeprefix("span_attr:")] = value
        elif key.startswith("resource_attr:"):
            attributes[key.removeprefix("resource_attr:")] = value
        elif key.startswith("event:event_attr:"):
            rest = key.removeprefix("event:event_attr:")
            suffix = rest.rsplit(":", 1)
            if len(suffix) == 2 and suffix[1].isdigit():
                rest = suffix[0]
            attributes[f"event_attr:{rest}"] = value
    return attributes


def _fields_pipe(names: tuple[str, ...]) -> str:
    return "| fields " + ", ".join(_logsql_field(name) for name in names)


def _topology_span_fields_pipe() -> str:
    names = _TOPOLOGY_SPAN_CORE_FIELDS + tuple(f"span_attr:{key}" for key in _TOPOLOGY_SPAN_ATTR_KEYS)
    return _fields_pipe(names)


def _trace_structure_fields_pipe() -> str:
    return _fields_pipe(_TOPOLOGY_SPAN_CORE_FIELDS)


def _span_search_fields_pipe() -> str:
    return _fields_pipe(_TOPOLOGY_SPAN_CORE_FIELDS + _HTTP_METHOD_FIELDS + _HTTP_STATUS_FIELDS)


def _is_response_too_large(exc: BaseException) -> bool:
    return isinstance(exc, TelemetryQueryTooLarge) and str(exc) == RESPONSE_TOO_LARGE


def _pack_trace_ids(
    items: list[tuple[str, int]],
    *,
    span_budget: int = TOPOLOGY_SPAN_FETCH_SPAN_BUDGET,
    fallback_batch: int = TOPOLOGY_SPAN_FETCH_BATCH,
) -> list[list[str]]:
    """按 Span 行数打包；没有 count 时退回固定条数分批。"""

    if not items:
        return []
    if not any(count > 0 for _, count in items):
        ids = [trace_id for trace_id, _ in items]
        return [ids[offset : offset + fallback_batch] for offset in range(0, len(ids), fallback_batch)]
    batches: list[list[str]] = []
    current: list[str] = []
    current_spans = 0
    for trace_id, count in items:
        span_count = max(1, count)
        if current and current_spans + span_count > span_budget:
            batches.append(current)
            current = []
            current_spans = 0
        current.append(trace_id)
        current_spans += span_count
        if current_spans >= span_budget:
            batches.append(current)
            current = []
            current_spans = 0
    if current:
        batches.append(current)
    return batches


def _metric_window_slices(started_at: datetime, ended_at: datetime, *, width: timedelta) -> list[tuple[datetime, datetime]]:
    if ended_at - started_at <= width:
        return [(started_at, ended_at)]
    slices: list[tuple[datetime, datetime]] = []
    cursor = started_at
    while cursor < ended_at:
        slice_ended_at = min(ended_at, cursor + width)
        slices.append((cursor, slice_ended_at))
        cursor = slice_ended_at
    return slices


def _span_kind_filter(kind: str | None, kinds: tuple[str, ...] | None) -> str | None:
    if kind is not None and kinds is not None:
        raise ValueError("kind 与 kinds 不能同时指定")
    if kind is not None:
        if kind not in _KIND_TO_CODE:
            raise ValueError("Span kind 无效")
        return f"kind:={_logsql_string(_KIND_TO_CODE[kind])}"
    if not kinds:
        return None
    codes: list[str] = []
    for item in kinds:
        if item not in _KIND_TO_CODE:
            raise ValueError("Span kind 无效")
        codes.append(_logsql_string(_KIND_TO_CODE[item]))
    return f"kind:in({','.join(codes)})"


def _validate_window(started_at: datetime, ended_at: datetime, *, maximum: timedelta = MAX_QUERY_WINDOW) -> int:
    if ended_at <= started_at:
        raise ValueError("查询结束时间必须晚于开始时间")
    window = ended_at - started_at
    if window > maximum:
        raise ValueError(f"APM 查询时间窗不能超过 {maximum.days} 天")
    return max(1, int(window.total_seconds()))


def _sample_slice_width(window: timedelta) -> timedelta:
    """短窗单片取最近；1h 按 15 分钟、1d 按小时、更长按天。"""

    if window <= SAMPLE_SLICE_QUARTER_HOUR:
        return window
    if window <= SAMPLE_SLICE_HOUR:
        return SAMPLE_SLICE_QUARTER_HOUR
    if window <= SAMPLE_SLICE_DAY:
        return SAMPLE_SLICE_HOUR
    return SAMPLE_SLICE_DAY


def _sample_slices(started_at: datetime, ended_at: datetime) -> list[tuple[datetime, datetime]]:
    """把取样窗口按分层宽度从新到旧切片；VT 的 end 为开区间，切片间无重叠无缝隙。"""

    width = _sample_slice_width(ended_at - started_at)
    slices: list[tuple[datetime, datetime]] = []
    cursor = ended_at
    while cursor > started_at:
        slice_started_at = max(started_at, cursor - width)
        slices.append((slice_started_at, cursor))
        cursor = slice_started_at
    return slices


def _topology_trace_id_query(filters: list[str], limit: int, *, slice_width: timedelta) -> str:
    """短切片全量按 trace_id 聚合；天级切片先取最近 Span 再聚合，语义仍是切片内最新 Trace。"""

    if slice_width >= SAMPLE_SLICE_DAY:
        return (
            f"{' '.join(filters)} | first {SAMPLE_TRACE_ID_PROBE_SPANS} by (_time desc) "
            f"| stats by (trace_id) max(_time) as matched_at, count() as spans "
            f"| sort by (matched_at) desc | limit {limit + 1}"
        )
    return (
        f"{' '.join(filters)} | stats by (trace_id) max(start_time_unix_nano) as matched_at, "
        f"count() as spans | sort by (matched_at) desc | limit {limit + 1}"
    )


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_vt_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return None
    numeric = _number(value)
    if numeric is not None and text[:1].isdigit():
        seconds = numeric
        if numeric > 1e16:
            seconds = numeric / 1_000_000_000
        elif numeric > 1e12:
            seconds = numeric / 1_000_000
        elif numeric > 1e11:
            seconds = numeric / 1_000
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class VictoriaTracesTelemetryStore:
    """APM 唯一遥测查询 Adapter；隐藏 Jaeger/LogsQL 与 VT 响应格式。"""

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        session: requests.Session | None = None,
    ):
        self.endpoint = (
            endpoint or os.getenv("VICTORIATRACES_HOST") or os.getenv("APM_VICTORIATRACES_QUERY_ENDPOINT") or "http://127.0.0.1:10428"
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
        ended_at = min(query.ended_at, _decode_cursor(query.cursor)) if query.cursor else query.ended_at
        filters = ["*"]
        if query.service_name is not None:
            filters.append(f"{_SERVICE_FIELD}:={_logsql_string(query.service_name)}")
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
        selected, matched_at_by_id, span_counts, _truncated = self._sample_trace_ids(
            filters,
            started_at=query.started_at,
            ended_at=ended_at,
            limit=query.limit + 1,
            fill="newest_first",
        )
        traces, _omitted = self._fetch_topology_traces(
            selected,
            started_at=query.started_at,
            ended_at=ended_at,
            span_counts=span_counts,
            fields_pipe=_trace_structure_fields_pipe(),
        )
        traces_by_id = {detail.trace_id: detail for detail in traces}
        summaries: list[tuple[datetime, TraceSummary]] = []
        for trace_id in selected:
            detail = traces_by_id.get(trace_id)
            if detail is None:
                continue
            matching_span = self._matching_span(detail, query)
            if matching_span is None:
                continue
            matched_at = matched_at_by_id.get(trace_id) or min(span.started_at for span in detail.spans)
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
        kind_filter = _span_kind_filter(query.kind, query.kinds)
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
        if kind_filter is not None:
            filters.append(kind_filter)
        if query.min_duration_ms is not None:
            filters.append(f"duration:>={int(query.min_duration_ms * 1_000_000)}")
        if query.max_duration_ms is not None:
            filters.append(f"duration:<={int(query.max_duration_ms * 1_000_000)}")

        logs_query = f"{' '.join(filters)} | sort by (_time) desc | limit {query.limit + 1} {_span_search_fields_pipe()}"
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
        ended_at = datetime.now(UTC) + timedelta(minutes=1)
        started_at = ended_at - MAX_QUERY_WINDOW
        structure_query = (
            f"trace_id:={_logsql_string(trace_id)} | limit {_RAW_SPAN_PARSE_LIMIT} {_trace_structure_fields_pipe()}"
        )
        rows = self._query_rows(structure_query, started_at, ended_at, limit=_RAW_SPAN_PARSE_LIMIT)
        detail = self._traces_from_span_rows(rows).get(trace_id)
        if detail is None:
            return None
        attributes_by_id = self._fetch_trace_span_attributes(
            trace_id,
            [span.span_id for span in detail.spans],
            started_at=started_at,
            ended_at=ended_at,
        )
        merged: list = []
        truncated = detail.truncated
        for span in detail.spans:
            # 结构阶段的属性带 span_attr:/resource_attr: 前缀，统一归一化后再与属性阶段合并，避免同一属性出现两个键。
            base = _row_detail_attributes(span.attributes)
            extra = attributes_by_id.get(span.span_id)
            if extra is None:
                truncated = True
                merged.append(replace(span, attributes=base))
                continue
            merged.append(replace(span, attributes={**base, **extra}))
        return replace(detail, spans=tuple(merged), truncated=truncated)

    def _fetch_trace_span_attributes(
        self,
        trace_id: str,
        span_ids: list[str],
        *,
        started_at: datetime,
        ended_at: datetime,
    ) -> dict[str, dict[str, object]]:
        attributes: dict[str, dict[str, object]] = {}
        for offset in range(0, len(span_ids), TRACE_DETAIL_ATTR_BATCH):
            batch = span_ids[offset : offset + TRACE_DETAIL_ATTR_BATCH]
            attributes.update(
                self._fetch_trace_span_attribute_batch(
                    trace_id,
                    batch,
                    started_at=started_at,
                    ended_at=ended_at,
                )
            )
        return attributes

    def _fetch_trace_span_attribute_batch(
        self,
        trace_id: str,
        span_ids: list[str],
        *,
        started_at: datetime,
        ended_at: datetime,
    ) -> dict[str, dict[str, object]]:
        if not span_ids:
            return {}
        quoted = ",".join(_logsql_string(span_id) for span_id in span_ids)
        logs_query = (
            f"trace_id:={_logsql_string(trace_id)} span_id:in({quoted}) | limit {len(span_ids)}"
        )
        try:
            rows = self._query_rows(logs_query, started_at, ended_at, limit=len(span_ids))
        except TelemetryStoreUnavailable as exc:
            if _is_response_too_large(exc) and len(span_ids) > 1:
                mid = max(1, len(span_ids) // 2)
                left = self._fetch_trace_span_attribute_batch(
                    trace_id,
                    span_ids[:mid],
                    started_at=started_at,
                    ended_at=ended_at,
                )
                right = self._fetch_trace_span_attribute_batch(
                    trace_id,
                    span_ids[mid:],
                    started_at=started_at,
                    ended_at=ended_at,
                )
                return {**left, **right}
            if _is_response_too_large(exc):
                logger.warning(
                    "event=apm_trace_detail_span_omitted failed_stage=get_trace error_type=%s omitted_spans=%s",
                    type(exc).__name__,
                    1,
                )
                return {}
            raise
        result: dict[str, dict[str, object]] = {}
        for row in rows:
            span_id = str(row.get("span_id", "")).strip()
            if not span_id:
                continue
            result[span_id] = _row_detail_attributes(row)
        return result

    def service_red(self, query: ServiceMetricQuery) -> ServiceRed:
        window_seconds = _validate_window(query.started_at, query.ended_at)
        # 精确路径按 (trace_id, span_id) 去重，内存与唯一 Span 数成正比，长时间窗会超出
        # VT 单次查询内存上限；超过 RED_EXACT_DEDUP_WINDOW 改用不去重的流式聚合近似。
        exact_dedup = query.ended_at - query.started_at <= RED_EXACT_DEDUP_WINDOW
        deduped = self._deduped_entry_query(
            query.service_namespace,
            query.service_name,
            query.environment,
            endpoint=query.endpoint,
            version=query.version,
        )
        entry_filters = self._entry_span_filters(
            query.service_namespace,
            query.service_name,
            query.environment,
            endpoint=query.endpoint,
            version=query.version,
        )
        final_stats = (
            'stats count() as requests, count() if (status_code:="2") as errors, '
            "quantile(0.95, duration) as p95, quantile(0.99, duration) as p99"
        )
        aggregate_base = self._bounded_spans(deduped) if exact_dedup else entry_filters
        aggregate = f"{aggregate_base} | {final_stats}"
        values = self._ungrouped_values(self._stats(aggregate, query.started_at, query.ended_at))
        requests_count = values.get("requests")
        if requests_count is None or requests_count <= 0:
            return ServiceRed(None, None, None, None)
        if exact_dedup:
            self._reject_truncated_unique_spans(deduped, requests_count, query.started_at, query.ended_at)
        errors_count = values.get("errors", 0.0) or 0.0
        timeseries: tuple[ServiceRedPoint, ...] = ()
        endpoints: tuple[ServiceEndpointRed, ...] = ()
        if query.include_breakdown:
            step = max(15, math.ceil(window_seconds / (MAX_RED_POINTS - 1)))
            range_aggregate = f"{deduped if exact_dedup else entry_filters} | {final_stats}"
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
            endpoints = self._endpoint_red(
                self._endpoint_stats_rows(query, exact_dedup=exact_dedup, entry_filters=entry_filters),
                window_seconds,
            )
        return ServiceRed(
            request_rate=requests_count / window_seconds,
            error_rate=errors_count / requests_count,
            p95_ms=self._nanoseconds_to_ms(values.get("p95")),
            p99_ms=self._nanoseconds_to_ms(values.get("p99")),
            timeseries=timeseries,
            top_endpoints=endpoints,
            request_count=int(requests_count),
            error_count=int(errors_count),
        )

    def service_error_breakdown(self, query: ServiceErrorBreakdownQuery) -> ServiceErrorBreakdown:
        if not 1 <= query.sample_limit <= 50:
            raise ValueError("sample_limit 必须在 1 到 50 之间")
        red = self.service_red(
            ServiceMetricQuery(
                service_namespace=query.service_namespace,
                service_name=query.service_name,
                environment=query.environment,
                started_at=query.started_at,
                ended_at=query.ended_at,
            )
        )
        if red.request_count is None:
            return ServiceErrorBreakdown(None, None, None, MetricDataState.NO_DATA)
        error_count = red.error_count or 0
        failed_endpoints, other_error_count = self._failed_endpoints(query, error_count)
        if error_count == 0:
            return ServiceErrorBreakdown(
                red.request_count,
                0,
                0.0,
                MetricDataState.AVAILABLE,
                failed_endpoints,
                other_error_count,
            )
        error_types = self._error_types(query)
        recent = self.search_spans(
            SpanSearchQuery(
                started_at=query.started_at,
                ended_at=query.ended_at,
                service_namespace=query.service_namespace,
                service_name=query.service_name,
                environment=query.environment,
                status="error",
                kinds=("server", "consumer"),
                limit=query.sample_limit,
            )
        )
        return ServiceErrorBreakdown(
            request_count=red.request_count,
            error_count=error_count,
            error_rate=red.error_rate,
            data_state=MetricDataState.AVAILABLE,
            failed_endpoints=failed_endpoints,
            other_error_count=other_error_count,
            error_types=error_types,
            recent_failures=recent.items,
        )

    def _failed_endpoints(
        self,
        query: ServiceErrorBreakdownQuery,
        total_errors: int,
    ) -> tuple[tuple[ServiceFailedEndpoint, ...], int]:
        exact_dedup = query.ended_at - query.started_at <= RED_EXACT_DEDUP_WINDOW
        final_stats = 'count() as requests, count() if (status_code:="2") as errors'
        if exact_dedup:
            endpoint_query = (
                f"{self._bounded_spans(self._deduped_entry_query(query.service_namespace, query.service_name, query.environment, keep_name=True))} "
                f"| stats by (endpoint) {final_stats} "
                f"| sort by (errors) desc | limit {MAX_FAILED_ENDPOINTS}"
            )
            rows = self._stats(endpoint_query, query.started_at, query.ended_at)
        else:
            endpoint_query = (
                f"{self._entry_span_filters(query.service_namespace, query.service_name, query.environment)} "
                f"| stats by (name) {final_stats} | sort by (errors) desc | limit {MAX_FAILED_ENDPOINTS}"
            )
            rows = self._stats(endpoint_query, query.started_at, query.ended_at)
        grouped: dict[str, dict[str, float]] = {}
        for series in rows:
            metric = series.get("metric", {})
            raw_value = series.get("value", [])
            if not isinstance(metric, dict) or not isinstance(raw_value, list) or len(raw_value) != 2:
                continue
            endpoint = str(metric.get("endpoint") or metric.get("name") or "").strip()[:MAX_ENDPOINT_NAME_LENGTH]
            name = str(metric.get("__name__", ""))
            value = _number(raw_value[1])
            if endpoint and name and value is not None:
                grouped.setdefault(endpoint, {})[name] = value
        return rank_failed_endpoints(
            [
                (endpoint, int(values.get("requests", 0)), int(values.get("errors", 0)))
                for endpoint, values in grouped.items()
            ],
            total_errors=total_errors,
        )

    def _error_types(self, query: ServiceErrorBreakdownQuery):
        filters = self._service_span_filters(query.service_namespace, query.service_name, query.environment)
        stats_query = (
            f"{filters} status_code:=\"2\" | stats by (kind, {_EXCEPTION_TYPE_FIELD}, {_SPAN_ERROR_TYPE_FIELD}, "
            f"status_message, {_HTTP_STATUS_FIELD}, {_EXCEPTION_MESSAGE_FIELD}) count() as c, max(_time) as last_seen "
            f"| sort by (c) desc | limit {MAX_ERROR_TYPE_GROUPS}"
        )
        rows = self._query_rows(stats_query, query.started_at, query.ended_at, limit=MAX_ERROR_TYPE_GROUPS)
        groups: list[RawErrorGroup] = []
        for row in rows:
            count = int(_number(row.get("c")) or 0)
            last_seen = _parse_vt_time(row.get("last_seen")) or query.ended_at
            groups.append(
                RawErrorGroup(
                    kind=str(row.get("kind", "")),
                    exception_type=str(row.get("event:event_attr:exception.type:0", "")).strip(),
                    span_error_type=str(row.get("span_attr:error.type", "")).strip(),
                    status_message=str(row.get("status_message", "")).strip(),
                    http_status=str(row.get("span_attr:http.response.status_code", "")).strip(),
                    exception_message=str(row.get("event:event_attr:exception.message:0", "")).strip(),
                    count=count,
                    last_seen_at=last_seen,
                )
            )
        types = merge_error_groups(groups)
        if not types:
            return ()
        samples_by_type: dict[str, tuple[ServiceErrorSampleTrace, ...]] = {}
        workers = min(ERROR_TYPE_SAMPLE_WORKERS, len(types))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._error_type_samples, query, item.error_type): item.error_type for item in types}
            for future in as_completed(futures):
                samples_by_type[futures[future]] = future.result()
        return tuple(attach_samples(item, samples_by_type[item.error_type]) for item in types)

    def _error_type_samples(self, query: ServiceErrorBreakdownQuery, error_type: str) -> tuple[ServiceErrorSampleTrace, ...]:
        filters = self._service_span_filters(query.service_namespace, query.service_name, query.environment)
        logs_query = (
            f"{filters} status_code:=\"2\" {self._error_type_predicate(error_type)} "
            f"| sort by (_time) desc | limit {MAX_ERROR_TYPE_SAMPLES}"
        )
        rows = self._query_rows(logs_query, query.started_at, query.ended_at, limit=MAX_ERROR_TYPE_SAMPLES)
        samples: list[ServiceErrorSampleTrace] = []
        for row in rows:
            summary = self._span_summary_from_row(row)
            if summary is None:
                continue
            samples.append(
                ServiceErrorSampleTrace(
                    trace_id=summary.trace_id,
                    span_id=summary.span_id,
                    endpoint=summary.name,
                    started_at=summary.started_at,
                )
            )
        return tuple(samples[:MAX_ERROR_TYPE_SAMPLES])

    @staticmethod
    def _error_type_predicate(error_type: str) -> str:
        no_exception = f"not {_EXCEPTION_TYPE_FIELD}:*"
        no_error_type = f"not {_SPAN_ERROR_TYPE_FIELD}:*"
        no_status_message = "not status_message:*"
        if error_type == UNATTRIBUTED_ERROR_TYPE:
            return (
                f"({no_exception} and {no_error_type} and {no_status_message} "
                f"and not {_HTTP_STATUS_FIELD}:~\"^5\")"
            )
        if error_type.startswith("HTTP "):
            code = error_type.removeprefix("HTTP ").strip()
            return (
                f"({no_exception} and {no_error_type} and {no_status_message} "
                f"and {_HTTP_STATUS_FIELD}:={_logsql_string(code)})"
            )
        quoted = _logsql_string(error_type)
        return (
            f"({_EXCEPTION_TYPE_FIELD}:={quoted} "
            f"or ({no_exception} and {_SPAN_ERROR_TYPE_FIELD}:={quoted}) "
            f"or ({no_exception} and {no_error_type} and status_message:={quoted}))"
        )

    def _service_span_filters(self, namespace: str, service_name: str, environment: str) -> str:
        return " ".join(
            [
                "*",
                f"{_NAMESPACE_FIELD}:={_logsql_string(namespace)}",
                f"{_SERVICE_FIELD}:={_logsql_string(service_name)}",
                f"{_ENVIRONMENT_FIELD}:={_logsql_string(environment)}",
            ]
        )

    def _endpoint_stats_rows(
        self,
        query: ServiceMetricQuery,
        *,
        exact_dedup: bool,
        entry_filters: str,
    ) -> list[dict[str, Any]]:
        final_stats = (
            'count() as requests, count() if (status_code:="2") as errors, '
            "quantile(0.95, duration) as p95, quantile(0.99, duration) as p99"
        )
        if exact_dedup:
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
                f"| stats by (endpoint) {final_stats} "
                f"| sort by (requests) desc | limit {MAX_TOP_ENDPOINTS}"
            )
            return self._stats(endpoint_query, query.started_at, query.ended_at)
        endpoint_query = (
            f"{entry_filters} | stats by (name) {final_stats} | sort by (requests) desc | limit {MAX_TOP_ENDPOINTS}"
        )
        rows = self._stats(endpoint_query, query.started_at, query.ended_at)
        remapped: list[dict[str, Any]] = []
        for row in rows:
            metric = row.get("metric")
            if not isinstance(metric, dict):
                continue
            remapped.append({**row, "metric": {**metric, "endpoint": metric.get("name", "")}})
        return remapped

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
        total = 0.0
        good = 0.0
        for slice_started_at, slice_ended_at in _metric_window_slices(
            query.started_at,
            query.ended_at,
            width=RED_EXACT_DEDUP_WINDOW,
        ):
            values = self._ungrouped_values(
                self._stats(f"{self._bounded_spans(deduped)} | stats {final}", slice_started_at, slice_ended_at)
            )
            slice_total = values.get("total")
            if slice_total is None or slice_total <= 0:
                continue
            self._reject_truncated_unique_spans(deduped, slice_total, slice_started_at, slice_ended_at)
            total += slice_total
            good += values.get(good_metric, 0.0) if good_metric else max(0.0, slice_total - values.get("bad", 0.0))
        if total <= 0:
            return SloMeasurement(None, None, None, MetricDataState.NO_DATA)
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
        selected_ids, _matched_at, span_counts, truncated = self._sample_trace_ids(
            filters,
            started_at=query.started_at,
            ended_at=query.ended_at,
            limit=query.limit,
        )
        traces, omitted = self._fetch_topology_traces(
            selected_ids,
            started_at=query.started_at,
            ended_at=query.ended_at,
            span_counts=span_counts,
        )
        return TopologyTraceSample(traces=tuple(traces), truncated=truncated, omitted_trace_fetches=omitted)

    def _sample_trace_ids(
        self,
        filters: list[str],
        *,
        started_at: datetime,
        ended_at: datetime,
        limit: int,
        fill: str = "round_robin",
    ) -> tuple[list[str], dict[str, datetime], dict[str, int], bool]:
        """按切片取 trace_id；``round_robin`` 供拓扑跨时段取样，``newest_first`` 供列表分页保持最新优先。"""

        if fill not in ("round_robin", "newest_first"):
            raise ValueError("fill 仅支持 round_robin 或 newest_first")
        per_slice_ids: list[list[str]] = []
        matched_at_by_id: dict[str, datetime] = {}
        span_counts: dict[str, int] = {}
        collected = 0
        for slice_started_at, slice_ended_at in _sample_slices(started_at, ended_at):
            if fill == "newest_first" and collected > limit:
                break
            logs_query = _topology_trace_id_query(
                filters,
                limit,
                slice_width=slice_ended_at - slice_started_at,
            )
            rows = self._query_rows(logs_query, slice_started_at, slice_ended_at, limit=limit + 1)
            slice_ids: list[str] = []
            slice_seen: set[str] = set()
            for row in rows:
                trace_id = str(row.get("trace_id", "")).strip()
                if not trace_id or trace_id in slice_seen:
                    continue
                slice_seen.add(trace_id)
                slice_ids.append(trace_id)
                span_count = int(_number(row.get("spans")) or 0)
                if span_count > span_counts.get(trace_id, 0):
                    span_counts[trace_id] = span_count
                matched_at = _parse_vt_time(row.get("matched_at"))
                if matched_at is not None:
                    previous = matched_at_by_id.get(trace_id)
                    if previous is None or matched_at > previous:
                        matched_at_by_id[trace_id] = matched_at
            per_slice_ids.append(slice_ids)
            collected += len(slice_ids)
        trace_ids: list[str] = []
        seen: set[str] = set()
        if fill == "newest_first":
            # 切片从新到旧、切片内按 matched_at 降序，顺序拼接即为全窗最新优先，游标翻页不会跳过。
            ordered = (trace_id for slice_ids in per_slice_ids for trace_id in slice_ids)
        else:
            ordered = (
                slice_ids[index]
                for index in range(max((len(ids) for ids in per_slice_ids), default=0))
                for slice_ids in per_slice_ids
                if index < len(slice_ids)
            )
        for trace_id in ordered:
            if trace_id in seen:
                continue
            seen.add(trace_id)
            trace_ids.append(trace_id)
        truncated = len(trace_ids) > limit
        selected_ids = trace_ids[:limit]
        return selected_ids, matched_at_by_id, {trace_id: span_counts.get(trace_id, 0) for trace_id in selected_ids}, truncated

    def _fetch_topology_traces(
        self,
        trace_ids: list[str],
        *,
        started_at: datetime,
        ended_at: datetime,
        span_counts: dict[str, int] | None = None,
        fields_pipe: str | None = None,
    ) -> tuple[list[TraceDetail], int]:
        """按 Span 数打包拉回构图或列表所需字段，避免 Java 堆栈等无界属性撑爆单次响应。"""

        traces: list[TraceDetail] = []
        omitted = 0
        packed = _pack_trace_ids([(trace_id, (span_counts or {}).get(trace_id, 0)) for trace_id in trace_ids])
        projection = fields_pipe if fields_pipe is not None else _topology_span_fields_pipe()
        for batch in packed:
            batch_traces, batch_omitted = self._fetch_topology_span_batch(
                batch,
                started_at=started_at,
                ended_at=ended_at,
                fields_pipe=projection,
            )
            traces.extend(batch_traces)
            omitted += batch_omitted
        return traces, omitted

    def _fetch_topology_span_batch(
        self,
        trace_ids: list[str],
        *,
        started_at: datetime,
        ended_at: datetime,
        fields_pipe: str,
    ) -> tuple[list[TraceDetail], int]:
        if not trace_ids:
            return [], 0
        quoted = ",".join(_logsql_string(trace_id) for trace_id in trace_ids)
        logs_query = f"trace_id:in({quoted}) | limit {MAX_TOPOLOGY_SAMPLE_SPANS} {fields_pipe}"
        try:
            rows = self._query_rows(logs_query, started_at, ended_at, limit=MAX_TOPOLOGY_SAMPLE_SPANS)
        except TelemetryStoreUnavailable as exc:
            if _is_response_too_large(exc) and len(trace_ids) > 1:
                mid = max(1, len(trace_ids) // 2)
                left_traces, left_omitted = self._fetch_topology_span_batch(
                    trace_ids[:mid],
                    started_at=started_at,
                    ended_at=ended_at,
                    fields_pipe=fields_pipe,
                )
                right_traces, right_omitted = self._fetch_topology_span_batch(
                    trace_ids[mid:],
                    started_at=started_at,
                    ended_at=ended_at,
                    fields_pipe=fields_pipe,
                )
                return left_traces + right_traces, left_omitted + right_omitted
            if _is_response_too_large(exc):
                logger.warning(
                    "event=apm_topology_trace_fetch_omitted failed_stage=sample_spans error_type=%s omitted_traces=%s",
                    type(exc).__name__,
                    1,
                )
                return [], 1
            logger.warning(
                "event=apm_topology_trace_fetch_failed failed_stage=sample_spans error_type=%s",
                type(exc).__name__,
            )
            raise
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
        attributes = {key: value for key, value in row.items() if isinstance(key, str) and key.startswith(("span_attr:", "resource_attr:"))}
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

    def _entry_span_filters(
        self,
        namespace: str,
        service_name: str,
        environment: str,
        *,
        endpoint: str = "",
        version: str = "",
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
        return " ".join(filters)

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
        fields = "max(duration) as duration, max(status_code) as status_code"
        if keep_name:
            fields += ", max(name) as endpoint"
        base = self._entry_span_filters(namespace, service_name, environment, endpoint=endpoint, version=version)
        return f"{base} | stats by (trace_id, span_id) {fields}"

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
                raise TelemetryQueryTooLarge(RESPONSE_TOO_LARGE)
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise TelemetryQueryTooLarge(RESPONSE_TOO_LARGE)
                chunks.append(chunk)
            return b"".join(chunks)
        except TelemetryStoreUnavailable:
            raise
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in (400, 413, 422):
                raise TelemetryQueryTooLarge(QUERY_CAPACITY_REJECTED) from exc
            raise TelemetryStoreUnavailable("VictoriaTraces 查询不可用") from exc
        except (requests.RequestException, TypeError, ValueError) as exc:
            raise TelemetryStoreUnavailable("VictoriaTraces 查询不可用") from exc
        finally:
            if response is not None:
                response.close()

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
