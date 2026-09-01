from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Sequence

from django.db.models import Prefetch, QuerySet
from django.utils import timezone

from apps.apm.adapters.errors import TelemetryStoreUnavailable
from apps.apm.models import ApmAlert, ApmDeploymentEvent, ApmService, ApmServiceInstance, ApmSlo
from apps.apm.services.contracts import ServiceMetricQuery, ServiceRed
from apps.apm.services.reliability import DjangoApmReliabilityService
from apps.apm.services.status import catalog_status
from apps.core.logger import apm_logger as logger
from apps.core.utils.viewset_utils import build_json_membership_query

WINDOW_DELTAS: dict[str, timedelta] = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
}
SPARKLINE_POINTS: dict[str, int] = {
    "15m": 15,
    "1h": 24,
    "4h": 24,
    "1d": 24,
    "7d": 28,
}
ALERT_SPARKLINE_HOURS = 24
MAX_METRIC_TARGETS = 40
MAX_TOP_ROWS = 5
MAX_SLO_ROWS = 5
MAX_ALERT_ROWS = 5
MAX_RELEASE_ROWS = 5
RELEASE_LOOKBACK = timedelta(days=7)
SECTION_WORKERS = 8


@dataclass(frozen=True)
class _ServiceTarget:
    service_id: str
    namespace: str
    name: str
    environment: str
    status: str
    last_seen_at: datetime


def _section_ok(data: Any) -> dict[str, Any]:
    return {"status": "ok", "data": data}


def _section_empty(data: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "empty"}
    if data is not None:
        payload["data"] = data
    return payload


def _section_failed(error: str) -> dict[str, Any]:
    return {"status": "failed", "error": error}


def _flat_sparkline(value: float | int | None, points: int) -> list[float | None]:
    if value is None:
        return [None] * points
    numeric = float(value)
    return [numeric] * points


def _resample(values: list[float | None], points: int) -> list[float | None]:
    if points <= 0:
        return []
    if not values:
        return [None] * points
    if len(values) == points:
        return values
    if len(values) == 1:
        return [values[0]] * points
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
    return result


def _health_bucket(status: str, error_rate: float | None) -> str:
    if status == "archived" or status == "silent":
        return "unknown"
    if error_rate is not None and error_rate >= 0.05:
        return "critical"
    if error_rate is not None and error_rate >= 0.01:
        return "warning"
    return "healthy"


def _severity_label(severity: str) -> str:
    if severity in {"critical", "error"}:
        return "critical"
    return "warning"


class ApmDashboardService:
    """首页聚合层：分项独立失败，不维护独立缓存。"""

    def __init__(
        self,
        *,
        metric_store=None,
        reliability: DjangoApmReliabilityService | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ):
        self.metric_store = metric_store
        if reliability is not None:
            self.reliability = reliability
        elif metric_store is not None:
            self.reliability = DjangoApmReliabilityService(metric_store=metric_store)
        else:
            self.reliability = None
        self.now_fn = now_fn or timezone.now

    def build(self, *, organization_id: int | None = None, window: str, organization_ids: Sequence[int] | None = None) -> dict[str, Any]:
        if window not in WINDOW_DELTAS:
            raise ValueError(f"不支持的时间窗: {window}")
        ids = tuple(organization_ids) if organization_ids is not None else (organization_id,)
        ended_at = self.now_fn()
        started_at = ended_at - WINDOW_DELTAS[window]
        services = list(self._visible_services(ids))
        empty = len(services) == 0
        if empty:
            return {
                "empty": True,
                "window": window,
                "kpis": _section_empty(),
                "health": _section_empty(),
                "slos": _section_empty(),
                "alerts": _section_empty(),
                "top_error_rate": _section_empty(),
                "top_p95": _section_empty(),
                "releases": _section_empty({"items": []}),
            }

        targets = self._metric_targets(services, ended_at)
        red_by_key = self._load_service_red(targets, started_at, ended_at)

        return {
            "empty": False,
            "window": window,
            "kpis": self._safe_section(lambda: self._build_kpis(ids, services, started_at, ended_at, window, targets, red_by_key)),
            "health": self._safe_section(lambda: self._build_health(targets, red_by_key)),
            "slos": self._safe_section(lambda: self._build_slos(ids)),
            "alerts": self._safe_section(lambda: self._build_alerts(ids)),
            "top_error_rate": self._safe_section(lambda: self._build_top_error_rate(targets, red_by_key)),
            "top_p95": self._safe_section(lambda: self._build_top_p95(targets, red_by_key)),
            "releases": self._safe_section(lambda: self._build_releases(ids)),
        }

    @staticmethod
    def _safe_section(builder: Callable[[], Any]) -> dict[str, Any]:
        try:
            data = builder()
            if isinstance(data, dict) and data.get("status") in {"ok", "empty", "failed"}:
                return data
            return _section_ok(data)
        except Exception as exc:  # noqa: BLE001 - 分项失败不得拖垮整页
            logger.exception("APM dashboard section failed: %s", exc)
            return _section_failed(str(exc) or exc.__class__.__name__)

    def _visible_services(self, organization_ids: Sequence[int]) -> QuerySet[ApmService]:
        return (
            ApmService.objects.filter(
                organization_links__organization__in=organization_ids,
                archived_at__isnull=True,
            )
            .select_related("application")
            .prefetch_related(
                Prefetch(
                    "instances",
                    queryset=ApmServiceInstance.objects.order_by("-last_seen_at"),
                )
            )
            .distinct()
            .order_by("-last_seen_at", "id")
        )

    def _metric_targets(self, services: list[ApmService], observed_at: datetime) -> list[_ServiceTarget]:
        targets: list[_ServiceTarget] = []
        for service in services:
            status = catalog_status(last_seen_at=service.last_seen_at, archived_at=service.archived_at, observed_at=observed_at)
            views = service.instances.all()
            environments: dict[str, datetime] = {}
            for instance in views:
                environment = instance.environment or ""
                previous = environments.get(environment)
                if previous is None or instance.last_seen_at > previous:
                    environments[environment] = instance.last_seen_at
            if not environments:
                environments[""] = service.last_seen_at
            for environment, last_seen_at in sorted(environments.items()):
                targets.append(
                    _ServiceTarget(
                        service_id=str(service.id),
                        namespace=service.namespace,
                        name=service.name,
                        environment=environment,
                        status=status,
                        last_seen_at=last_seen_at,
                    )
                )
        targets.sort(key=lambda item: (0 if item.status == "active" else 1, -item.last_seen_at.timestamp(), item.name))
        return targets[:MAX_METRIC_TARGETS]

    def _load_service_red(
        self,
        targets: list[_ServiceTarget],
        started_at: datetime,
        ended_at: datetime,
    ) -> dict[str, ServiceRed | None]:
        if self.metric_store is None or not targets:
            return {}
        results: dict[str, ServiceRed | None] = {}

        def _fetch(target: _ServiceTarget) -> tuple[str, ServiceRed | None]:
            key = f"{target.service_id}:{target.environment}"
            query = ServiceMetricQuery(
                service_namespace=target.namespace,
                service_name=target.name,
                environment=target.environment,
                started_at=started_at,
                ended_at=ended_at,
                include_breakdown=True,
            )
            try:
                return key, self.metric_store.service_red(query)
            except TelemetryStoreUnavailable:
                return key, None
            except Exception as exc:  # noqa: BLE001
                logger.warning("APM dashboard RED query failed for %s: %s", key, exc)
                return key, None

        with ThreadPoolExecutor(max_workers=min(SECTION_WORKERS, len(targets))) as pool:
            futures = [pool.submit(_fetch, target) for target in targets]
            for future in as_completed(futures):
                key, value = future.result()
                results[key] = value
        return results

    def _build_kpis(
        self,
        organization_ids: Sequence[int],
        services: list[ApmService],
        started_at: datetime,
        ended_at: datetime,
        window: str,
        targets: list[_ServiceTarget],
        red_by_key: dict[str, ServiceRed | None],
    ) -> dict[str, Any]:
        points = SPARKLINE_POINTS[window]
        in_window = [service for service in services if service.last_seen_at >= started_at]
        app_count = len({service.namespace for service in in_window})
        service_count = len({service.name for service in in_window})
        alert_count = self._active_alert_queryset(organization_ids).count()

        request_rate = 0.0
        error_rate_sum = 0.0
        p95_weight = 0.0
        p95_weighted = 0.0
        has_request = False
        has_error = False
        has_p95 = False
        request_series: list[list[float | None]] = []
        error_series: list[list[float | None]] = []
        p95_series: list[list[float | None]] = []

        for target in targets:
            red = red_by_key.get(f"{target.service_id}:{target.environment}")
            if red is None:
                continue
            if red.request_rate is not None:
                has_request = True
                request_rate += red.request_rate
            if red.request_rate is not None and red.error_rate is not None:
                has_error = True
                error_rate_sum += red.request_rate * red.error_rate
            if red.p95_ms is not None and red.request_rate is not None and red.request_rate > 0:
                has_p95 = True
                p95_weight += red.request_rate
                p95_weighted += red.p95_ms * red.request_rate
            elif red.p95_ms is not None and not has_p95:
                has_p95 = True
                p95_weight = 1.0
                p95_weighted = red.p95_ms

            if red.timeseries:
                request_series.append(_resample([point.request_rate for point in red.timeseries], points))
                error_series.append(
                    _resample(
                        [
                            None if point.request_rate is None or point.error_rate is None else point.request_rate * point.error_rate
                            for point in red.timeseries
                        ],
                        points,
                    )
                )
                p95_series.append(_resample([point.p95_ms for point in red.timeseries], points))

        p95_ms = (p95_weighted / p95_weight) if has_p95 and p95_weight > 0 else None
        return {
            "application_count": app_count,
            "service_count": service_count,
            "active_alert_count": alert_count,
            "request_rate": request_rate if has_request else None,
            "error_request_rate": error_rate_sum if has_error else None,
            "p95_ms": p95_ms,
            "sparklines": {
                "application_count": _flat_sparkline(app_count, points),
                "service_count": _flat_sparkline(service_count, points),
                "active_alert_count": self._alert_sparkline(organization_ids, ended_at),
                "request_rate": self._sum_series(request_series, points) if has_request else _flat_sparkline(None, points),
                "error_request_rate": self._sum_series(error_series, points) if has_error else _flat_sparkline(None, points),
                "p95_ms": self._avg_series(p95_series, points) if has_p95 else _flat_sparkline(None, points),
            },
        }

    def _alert_sparkline(self, organization_ids: Sequence[int], ended_at: datetime) -> list[float | None]:
        started_at = ended_at - timedelta(hours=ALERT_SPARKLINE_HOURS)
        queryset = ApmAlert.objects.filter(started_at__gte=started_at, started_at__lte=ended_at)
        queryset = queryset.filter(build_json_membership_query(queryset, "organizations", list(organization_ids)))
        buckets = [0.0] * ALERT_SPARKLINE_HOURS
        for started in queryset.values_list("started_at", flat=True):
            hour_index = int((started - started_at).total_seconds() // 3600)
            if 0 <= hour_index < ALERT_SPARKLINE_HOURS:
                buckets[hour_index] += 1.0
        # 累计未恢复快照感：用后缀累计近似近窗告警密度
        cumulative = 0.0
        series: list[float | None] = []
        for count in buckets:
            cumulative += count
            series.append(cumulative)
        return series

    @staticmethod
    def _sum_series(series_list: list[list[float | None]], points: int) -> list[float | None]:
        if not series_list:
            return _flat_sparkline(None, points)
        result: list[float | None] = []
        for index in range(points):
            total = 0.0
            seen = False
            for series in series_list:
                value = series[index] if index < len(series) else None
                if value is None:
                    continue
                seen = True
                total += value
            result.append(total if seen else None)
        return result

    @staticmethod
    def _avg_series(series_list: list[list[float | None]], points: int) -> list[float | None]:
        if not series_list:
            return _flat_sparkline(None, points)
        result: list[float | None] = []
        for index in range(points):
            total = 0.0
            count = 0
            for series in series_list:
                value = series[index] if index < len(series) else None
                if value is None:
                    continue
                total += value
                count += 1
            result.append(total / count if count else None)
        return result

    def _build_health(self, targets: list[_ServiceTarget], red_by_key: dict[str, ServiceRed | None]) -> dict[str, Any]:
        # 按服务去重：同一服务多环境取最差健康档
        rank = {"critical": 0, "warning": 1, "unknown": 2, "healthy": 3}
        by_service: dict[str, str] = {}
        for target in targets:
            red = red_by_key.get(f"{target.service_id}:{target.environment}")
            error_rate = red.error_rate if red is not None else None
            bucket = _health_bucket(target.status, error_rate)
            previous = by_service.get(target.service_id)
            if previous is None or rank[bucket] < rank[previous]:
                by_service[target.service_id] = bucket
        counts = {"healthy": 0, "warning": 0, "critical": 0, "unknown": 0}
        for bucket in by_service.values():
            counts[bucket] += 1
        total = sum(counts.values())
        return {
            "total": total,
            "buckets": [
                {"key": "healthy", "label": "健康", "count": counts["healthy"]},
                {"key": "warning", "label": "警告", "count": counts["warning"]},
                {"key": "critical", "label": "严重", "count": counts["critical"]},
                {"key": "unknown", "label": "未知", "count": counts["unknown"]},
            ],
        }

    def _build_slos(self, organization_ids: Sequence[int]) -> dict[str, Any]:
        if self.reliability is None:
            raise RuntimeError("MetricStore 未配置")
        slos = list(
            ApmSlo.objects.filter(
                is_enabled=True,
                service__organization_links__organization__in=organization_ids,
                service__archived_at__isnull=True,
            )
            .select_related("service")
            .distinct()
            .order_by("name", "id")[: MAX_SLO_ROWS * 3]
        )
        rows = []
        for slo in slos:
            evaluation = self.reliability.evaluate(slo, evaluated_at=self.now_fn())
            if evaluation.current_rate is None:
                continue
            objective = float(slo.objective)
            met = evaluation.current_rate >= objective
            rows.append(
                {
                    "id": str(slo.id),
                    "service_id": str(slo.service_id),
                    "service_name": slo.service.name,
                    "environment": slo.environment,
                    "objective": objective,
                    "current_rate": evaluation.current_rate,
                    "met": met,
                }
            )
            if len(rows) >= MAX_SLO_ROWS:
                break
        if not rows:
            return _section_empty({"items": []})
        return {"items": rows}

    def _build_releases(self, organization_ids: Sequence[int]) -> dict[str, Any]:
        ended_at = self.now_fn()
        started_at = ended_at - RELEASE_LOOKBACK
        visible_ids = ApmService.objects.filter(
            organization_links__organization__in=organization_ids,
            archived_at__isnull=True,
        ).values_list("id", flat=True)
        events = list(
            ApmDeploymentEvent.objects.filter(
                service_id__in=visible_ids,
                deployed_at__gte=started_at,
                deployed_at__lte=ended_at,
            )
            .select_related("service")
            .order_by("-deployed_at", "-id")[:MAX_RELEASE_ROWS]
        )
        if not events:
            return _section_empty({"items": []})
        return {
            "items": [
                {
                    "id": str(event.id),
                    "service_id": str(event.service_id),
                    "service_name": event.service.name,
                    "environment": event.environment,
                    "version": event.version,
                    "deployed_at": event.deployed_at,
                    "deployed_by": event.deployed_by,
                    "status": event.status,
                    "source": event.source,
                }
                for event in events
            ]
        }

    def _build_alerts(self, organization_ids: Sequence[int]) -> dict[str, Any]:
        alerts = list(self._active_alert_queryset(organization_ids).order_by("-last_event_at", "-id")[:MAX_ALERT_ROWS])
        if not alerts:
            return _section_empty({"items": []})
        return {
            "items": [
                {
                    "id": str(alert.id),
                    "service": alert.service_name,
                    "service_id": str(alert.service_id) if alert.service_id else None,
                    "name": alert.policy_name,
                    "severity": _severity_label(alert.severity),
                    "environment": alert.environment,
                    "started_at": alert.started_at,
                }
                for alert in alerts
            ]
        }

    def _build_top_error_rate(self, targets: list[_ServiceTarget], red_by_key: dict[str, ServiceRed | None]) -> dict[str, Any]:
        rows = []
        for target in targets:
            red = red_by_key.get(f"{target.service_id}:{target.environment}")
            if red is None or red.error_rate is None:
                continue
            rows.append(
                {
                    "service_id": target.service_id,
                    "service_name": target.name,
                    "environment": target.environment,
                    "value": red.error_rate * 100,
                    "sub_value": red.p95_ms,
                }
            )
        rows.sort(key=lambda item: item["value"], reverse=True)
        rows = rows[:MAX_TOP_ROWS]
        if not rows:
            return _section_empty({"items": []})
        return {"items": rows}

    def _build_top_p95(self, targets: list[_ServiceTarget], red_by_key: dict[str, ServiceRed | None]) -> dict[str, Any]:
        rows = []
        for target in targets:
            red = red_by_key.get(f"{target.service_id}:{target.environment}")
            if red is None or red.p95_ms is None:
                continue
            rows.append(
                {
                    "service_id": target.service_id,
                    "service_name": target.name,
                    "environment": target.environment,
                    "value": red.p95_ms,
                    "sub_value": red.request_rate,
                }
            )
        rows.sort(key=lambda item: item["value"], reverse=True)
        rows = rows[:MAX_TOP_ROWS]
        if not rows:
            return _section_empty({"items": []})
        return {"items": rows}

    @staticmethod
    def _active_alert_queryset(organization_ids: Sequence[int]) -> QuerySet[ApmAlert]:
        queryset = ApmAlert.objects.filter(status=ApmAlert.Status.ACTIVE)
        return queryset.filter(build_json_membership_query(queryset, "organizations", list(organization_ids)))
