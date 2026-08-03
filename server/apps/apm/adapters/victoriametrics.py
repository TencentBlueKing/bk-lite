from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from uuid import UUID

import requests

from apps.apm.services.contracts import (
    InstanceActivity,
    InstanceActivityQuery,
    ServiceMetricQuery,
    ServiceEndpointRed,
    ServiceRed,
    ServiceRedPoint,
)


class TelemetryStoreUnavailable(RuntimeError):
    pass


MAX_RED_POINTS = 120
MAX_TOP_ENDPOINTS = 10
MAX_ENDPOINT_NAME_LENGTH = 256


def _promql_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _window_seconds(started_at: datetime, ended_at: datetime) -> int:
    return max(60, int((ended_at - started_at).total_seconds()))


class VictoriaMetricsMetricStore:
    """APM MetricStore 的 VictoriaMetrics adapter；只暴露受控 RED 和活动查询。"""

    def __init__(self, *, endpoint: str | None = None, session=None):
        self.endpoint = (
            endpoint
            or os.getenv("APM_VICTORIAMETRICS_QUERY_ENDPOINT")
            or os.getenv("VICTORIAMETRICS_HOST")
            or ""
        ).rstrip("/")
        self.session = session or requests.Session()
        self.timeout = (3, int(os.getenv("APM_VICTORIAMETRICS_QUERY_TIMEOUT", "15")))
        self.verify = os.getenv("VICTORIAMETRICS_SSL_VERIFY", "false").lower() == "true"
        username = os.getenv("VICTORIAMETRICS_USER", "")
        password = os.getenv("VICTORIAMETRICS_PWD", "")
        self.auth = (username, password) if username else None

    def _query(self, promql: str, *, evaluated_at: datetime) -> list[dict]:
        if not self.endpoint:
            raise TelemetryStoreUnavailable("VictoriaMetrics 查询地址未配置")
        try:
            response = self.session.get(
                f"{self.endpoint}/api/v1/query",
                params={"query": promql, "time": evaluated_at.isoformat()},
                auth=self.auth,
                verify=self.verify,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise TelemetryStoreUnavailable("VictoriaMetrics 查询不可用") from exc
        if payload.get("status") != "success":
            raise TelemetryStoreUnavailable("VictoriaMetrics 返回查询错误")
        result = payload.get("data", {}).get("result", [])
        if not isinstance(result, list):
            raise TelemetryStoreUnavailable("VictoriaMetrics 返回格式无效")
        return result

    def _query_range(
        self,
        promql: str,
        *,
        started_at: datetime,
        ended_at: datetime,
        step: int,
    ) -> list[dict]:
        if not self.endpoint:
            raise TelemetryStoreUnavailable("VictoriaMetrics 查询地址未配置")
        try:
            response = self.session.get(
                f"{self.endpoint}/api/v1/query_range",
                params={
                    "query": promql,
                    "start": started_at.isoformat(),
                    "end": ended_at.isoformat(),
                    "step": step,
                },
                auth=self.auth,
                verify=self.verify,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise TelemetryStoreUnavailable("VictoriaMetrics 查询不可用") from exc
        if payload.get("status") != "success":
            raise TelemetryStoreUnavailable("VictoriaMetrics 返回查询错误")
        result = payload.get("data", {}).get("result", [])
        if not isinstance(result, list):
            raise TelemetryStoreUnavailable("VictoriaMetrics 返回格式无效")
        return result

    @staticmethod
    def _scalar(result: list[dict]) -> float:
        if not result:
            return 0.0
        try:
            value = float(result[0]["value"][1])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise TelemetryStoreUnavailable("VictoriaMetrics 标量格式无效") from exc
        return value if math.isfinite(value) else 0.0

    @staticmethod
    def _optional_scalar(result: list[dict]) -> float | None:
        if not result:
            return None
        try:
            value = float(result[0]["value"][1])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise TelemetryStoreUnavailable("VictoriaMetrics 标量格式无效") from exc
        return value if math.isfinite(value) else None

    @staticmethod
    def _range_values(result: list[dict]) -> dict[float, float]:
        if not result:
            return {}
        if len(result) != 1:
            raise TelemetryStoreUnavailable("VictoriaMetrics 时序聚合格式无效")
        try:
            values = result[0]["values"]
        except (KeyError, TypeError, ValueError) as exc:
            raise TelemetryStoreUnavailable("VictoriaMetrics 时序格式无效") from exc
        parsed: dict[float, float] = {}
        try:
            for timestamp, value in values:
                parsed_timestamp = float(timestamp)
                parsed_value = float(value)
                if math.isfinite(parsed_timestamp):
                    parsed[parsed_timestamp] = parsed_value if math.isfinite(parsed_value) else 0.0
        except (TypeError, ValueError) as exc:
            raise TelemetryStoreUnavailable("VictoriaMetrics 时序格式无效") from exc
        return dict(sorted(parsed.items())[-MAX_RED_POINTS:])

    @staticmethod
    def _endpoint_values(result: list[dict]) -> dict[str, float]:
        values: dict[str, float] = {}
        for series in result:
            try:
                endpoint = str(series["metric"].get("span_name", "")).strip()
                value = float(series["value"][1])
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            if endpoint and math.isfinite(value):
                values[endpoint[:MAX_ENDPOINT_NAME_LENGTH]] = value
        return values

    def service_red(self, query: ServiceMetricQuery) -> ServiceRed:
        window = _window_seconds(query.started_at, query.ended_at)
        step = max(15, math.ceil(window / (MAX_RED_POINTS - 1)))
        trend_window = max(60, step * 4)
        labels = {
            "service_namespace": query.service_namespace,
            "service_name": query.service_name,
            "deployment_environment": query.environment,
        }
        selector = ",".join(f"{key}={_promql_string(value)}" for key, value in labels.items())
        entry_selector = f'{selector},span_kind=~"SPAN_KIND_SERVER|SPAN_KIND_CONSUMER"'
        rate = f"sum(rate(bklite_apm_calls_total{{{entry_selector}}}[{window}s]))"
        errors = (
            "sum(rate(bklite_apm_calls_total{"
            f'{entry_selector},status_code="STATUS_CODE_ERROR"'
            f"}}[{window}s]))"
        )
        buckets = (
            "sum(rate(bklite_apm_duration_milliseconds_bucket{"
            f"{entry_selector}"
            f"}}[{window}s])) by (le)"
        )
        request_rate = self._optional_scalar(self._query(rate, evaluated_at=query.ended_at))
        error_rate_value = self._optional_scalar(self._query(errors, evaluated_at=query.ended_at))
        p95_ms = self._optional_scalar(
            self._query(f"histogram_quantile(0.95, {buckets})", evaluated_at=query.ended_at)
        )
        p99_ms = self._optional_scalar(
            self._query(f"histogram_quantile(0.99, {buckets})", evaluated_at=query.ended_at)
        )
        error_rate = (
            (error_rate_value or 0.0) / request_rate
            if request_rate is not None and request_rate > 0
            else None
        )
        if request_rate is None or request_rate <= 0:
            p95_ms = None
            p99_ms = None
        if not query.include_breakdown:
            return ServiceRed(
                request_rate=request_rate,
                error_rate=error_rate,
                p95_ms=p95_ms,
                p99_ms=p99_ms,
            )

        trend_rate = f"sum(rate(bklite_apm_calls_total{{{entry_selector}}}[{trend_window}s]))"
        trend_errors = (
            "sum(rate(bklite_apm_calls_total{"
            f'{entry_selector},status_code="STATUS_CODE_ERROR"'
            f"}}[{trend_window}s]))"
        )
        trend_buckets = (
            "sum(rate(bklite_apm_duration_milliseconds_bucket{"
            f"{entry_selector}"
            f"}}[{trend_window}s])) by (le)"
        )
        range_options = {
            "started_at": query.started_at,
            "ended_at": query.ended_at,
            "step": step,
        }
        trend_rates = self._range_values(self._query_range(trend_rate, **range_options))
        trend_error_rates = self._range_values(self._query_range(trend_errors, **range_options))
        trend_p95 = self._range_values(
            self._query_range(f"histogram_quantile(0.95, {trend_buckets})", **range_options)
        )
        trend_p99 = self._range_values(
            self._query_range(f"histogram_quantile(0.99, {trend_buckets})", **range_options)
        )
        timeseries = tuple(
            ServiceRedPoint(
                timestamp=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                request_rate=value,
                error_rate=trend_error_rates.get(timestamp, 0.0) / value if value > 0 else None,
                p95_ms=trend_p95.get(timestamp) if value > 0 else None,
                p99_ms=trend_p99.get(timestamp) if value > 0 else None,
            )
            for timestamp, value in trend_rates.items()
        )

        endpoint_rate_query = (
            "sum(rate(bklite_apm_calls_total{"
            f"{entry_selector}"
            f"}}[{window}s])) by (span_name)"
        )
        endpoint_error_query = (
            "sum(rate(bklite_apm_calls_total{"
            f'{entry_selector},status_code="STATUS_CODE_ERROR"'
            f"}}[{window}s])) by (span_name)"
        )
        endpoint_bucket_query = (
            "sum(rate(bklite_apm_duration_milliseconds_bucket{"
            f"{entry_selector}"
            f"}}[{window}s])) by (le,span_name)"
        )
        endpoint_rates = self._endpoint_values(
            self._query(endpoint_rate_query, evaluated_at=query.ended_at)
        )
        endpoint_errors = self._endpoint_values(
            self._query(endpoint_error_query, evaluated_at=query.ended_at)
        )
        endpoint_p95 = self._endpoint_values(
            self._query(
                f"histogram_quantile(0.95, {endpoint_bucket_query})",
                evaluated_at=query.ended_at,
            )
        )
        endpoint_p99 = self._endpoint_values(
            self._query(
                f"histogram_quantile(0.99, {endpoint_bucket_query})",
                evaluated_at=query.ended_at,
            )
        )
        top_endpoints = tuple(
            ServiceEndpointRed(
                endpoint=endpoint,
                request_rate=value,
                error_rate=endpoint_errors.get(endpoint, 0.0) / value if value > 0 else None,
                p95_ms=endpoint_p95.get(endpoint) if value > 0 else None,
                p99_ms=endpoint_p99.get(endpoint) if value > 0 else None,
            )
            for endpoint, value in sorted(
                endpoint_rates.items(), key=lambda item: (-item[1], item[0])
            )[:MAX_TOP_ENDPOINTS]
        )
        return ServiceRed(
            request_rate=request_rate,
            error_rate=error_rate,
            p95_ms=p95_ms,
            p99_ms=p99_ms,
            timeseries=timeseries,
            top_endpoints=top_endpoints,
        )

    def instance_activity(self, query: InstanceActivityQuery) -> list[InstanceActivity]:
        window = _window_seconds(query.started_at, query.ended_at)
        source_filter = ""
        if query.ingest_source_id is not None:
            source_filter = f'bk_ingest_source_id={_promql_string(str(query.ingest_source_id))}'
        selector = "{" + source_filter + "}"
        dimensions = (
            "service_namespace,service_name,service_instance_id,"
            "deployment_environment,service_version,bk_ingest_source_id"
        )
        promql = (
            f"max(tlast_over_time(bklite_apm_calls_total{selector}[{window}s])) "
            f"by ({dimensions})"
        )
        result = self._query(promql, evaluated_at=query.ended_at)
        if len(result) > 10_000:
            raise TelemetryStoreUnavailable("APM 活动维度超过单次对账上限")
        activities: dict[tuple[str, ...], InstanceActivity] = {}
        for series in result:
            metric = series.get("metric", {})
            source_id = metric.get("bk_ingest_source_id", "")
            service_name = metric.get("service_name", "").strip()
            if not service_name:
                continue
            try:
                parsed_source_id = UUID(source_id)
            except (TypeError, ValueError):
                continue
            try:
                last_seen_at = datetime.fromtimestamp(float(series["value"][1]), tz=timezone.utc)
            except (KeyError, IndexError, TypeError, ValueError, OverflowError):
                continue
            instance_id = metric.get("service_instance_id", "").strip() or None
            activity = InstanceActivity(
                service_namespace=metric.get("service_namespace", ""),
                service_name=service_name,
                instance_id=instance_id,
                environment=metric.get("deployment_environment", ""),
                version=metric.get("service_version", ""),
                ingest_source_id=parsed_source_id,
                last_seen_at=last_seen_at,
            )
            key = (
                activity.service_namespace,
                activity.service_name,
                activity.instance_id or "",
                activity.environment,
                activity.version,
                str(activity.ingest_source_id),
            )
            activities[key] = activity
        return list(activities.values())
