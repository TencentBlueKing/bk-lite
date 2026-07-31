from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID

import requests

from apps.apm.services.contracts import (
    InstanceActivity,
    InstanceActivityQuery,
    ServiceMetricQuery,
    ServiceRed,
)


class TelemetryStoreUnavailable(RuntimeError):
    pass


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

    @staticmethod
    def _scalar(result: list[dict]) -> float:
        if not result:
            return 0.0
        try:
            return float(result[0]["value"][1])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise TelemetryStoreUnavailable("VictoriaMetrics 标量格式无效") from exc

    def service_red(self, query: ServiceMetricQuery) -> ServiceRed:
        window = _window_seconds(query.started_at, query.ended_at)
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
        request_rate = self._scalar(self._query(rate, evaluated_at=query.ended_at))
        error_rate_value = self._scalar(self._query(errors, evaluated_at=query.ended_at))
        p95_ms = self._scalar(
            self._query(f"histogram_quantile(0.95, {buckets})", evaluated_at=query.ended_at)
        )
        p99_ms = self._scalar(
            self._query(f"histogram_quantile(0.99, {buckets})", evaluated_at=query.ended_at)
        )
        return ServiceRed(
            request_rate=request_rate,
            error_rate=error_rate_value / request_rate if request_rate > 0 else 0.0,
            p95_ms=p95_ms,
            p99_ms=p99_ms,
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
