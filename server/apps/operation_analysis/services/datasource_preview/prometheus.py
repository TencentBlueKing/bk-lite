from datetime import timedelta
from typing import Any

from apps.core.utils.time_util import parse_rfc3339_range_utc, rfc3339_to_timestamp
from apps.operation_analysis.services.datasource_preview.base import (
    BaseConnectorExecutor,
    ConnectorError,
    ExecuteResult,
    PreviewResult,
)
from apps.operation_analysis.services.datasource_preview.prometheus_client import PrometheusHttpClient
from apps.operation_analysis.services.datasource_preview.prometheus_transform import (
    clamp_max_series,
    transform_instant_result,
    transform_range_result,
)
from apps.operation_analysis.services.datasource_preview.schema import infer_fields

MAX_RANGE_SPAN = timedelta(days=31)
DEFAULT_STEP = "1m"


class PrometheusConnectorExecutor(BaseConnectorExecutor):
    source_type = "prometheus"

    def __init__(self, client=None):
        self.client = client or PrometheusHttpClient()

    def test_connection(self, connection_config: dict[str, Any]) -> None:
        self.client.healthy(connection_config)

    def execute(self, connection_config: dict[str, Any], params: dict[str, Any]) -> ExecuteResult:
        query = str(params.get("query") or "").strip()
        if not query:
            raise ConnectorError("Prometheus 查询不能为空", code="prometheus_query_required", status_code=400)

        query_type = str(params.get("query_type") or "range").lower()
        if query_type not in {"range", "instant"}:
            raise ConnectorError(
                "Prometheus query_type 仅支持 range 或 instant",
                code="prometheus_query_type_invalid",
                status_code=400,
            )

        max_series = clamp_max_series(params.get("max_series"))

        if query_type == "instant":
            query_time = None
            time_range = params.get("time_range")
            if time_range is not None:
                try:
                    _, end_dt = parse_rfc3339_range_utc(time_range)
                    query_time = rfc3339_to_timestamp(end_dt)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ConnectorError(
                        "Prometheus time_range 必须是包含两个 RFC3339 时间戳的数组",
                        code="prometheus_time_range_invalid",
                        status_code=400,
                    ) from exc
            payload = self.client.query(connection_config, query=query, time=query_time)
            data, warnings = transform_instant_result(payload["data"], max_series)
            return ExecuteResult(data=data, warnings=warnings)

        time_range = params.get("time_range")
        try:
            start_dt, end_dt = parse_rfc3339_range_utc(time_range)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ConnectorError(
                "Prometheus time_range 必须是包含两个 RFC3339 时间戳的数组",
                code="prometheus_time_range_invalid",
                status_code=400,
            ) from exc

        if end_dt - start_dt > MAX_RANGE_SPAN:
            raise ConnectorError(
                "Prometheus 查询时间范围不能超过 31 天",
                code="prometheus_range_too_large",
                status_code=400,
            )

        step = str(params.get("step") or "").strip() or DEFAULT_STEP
        start = rfc3339_to_timestamp(start_dt)
        end = rfc3339_to_timestamp(end_dt)
        payload = self.client.query_range(
            connection_config,
            query=query,
            start=start,
            end=end,
            step=step,
        )
        data, warnings = transform_range_result(payload["data"], max_series)
        return ExecuteResult(data=data, warnings=warnings)

    def preview(
        self,
        connection_config: dict[str, Any],
        query_config: dict[str, Any],
        limit: int = 100,
    ) -> PreviewResult:
        result = self.execute(connection_config, query_config)
        items = _flatten_execute_data(result.data)
        safe_limit = max(int(limit or 100), 1)
        limited_items = items[:safe_limit]
        return PreviewResult(
            items=limited_items,
            count=len(items),
            fields=infer_fields(limited_items),
            warnings=result.warnings,
        )


def _flatten_execute_data(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        items: list[dict[str, Any]] = []
        for series, points in data.items():
            if not isinstance(points, list):
                continue
            for point in points:
                if not isinstance(point, dict):
                    continue
                items.append(
                    {
                        "series": series,
                        "name": point.get("name"),
                        "value": point.get("value"),
                    }
                )
        return items

    return []
