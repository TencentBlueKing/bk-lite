from __future__ import annotations

from datetime import datetime, timedelta

from apps.apm.adapters.errors import TelemetryStoreUnavailable
from apps.apm.models import ApmSlo
from apps.apm.services.contracts import MetricDataState, MetricStore, SloEvaluation, SloMetricQuery


class DjangoApmReliabilityService:
    """隐藏 SLO 时间窗、指标查询和错误预算语义。"""

    def __init__(self, metric_store: MetricStore):
        self.metric_store = metric_store

    @staticmethod
    def _started_at(slo: ApmSlo, evaluated_at: datetime) -> datetime:
        if slo.evaluation_window == ApmSlo.EvaluationWindow.ROLLING_7D:
            return evaluated_at - timedelta(days=7)
        if slo.evaluation_window == ApmSlo.EvaluationWindow.ROLLING_30D:
            return evaluated_at - timedelta(days=30)
        return evaluated_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _budget_remaining(objective: float, current_rate: float) -> float:
        allowed_failure = 100.0 - objective
        current_failure = 100.0 - current_rate
        if allowed_failure <= 0:
            return 100.0 if current_failure <= 0 else 0.0
        return min(100.0, max(0.0, (allowed_failure - current_failure) / allowed_failure * 100.0))

    def evaluate(self, slo: ApmSlo, *, evaluated_at: datetime) -> SloEvaluation:
        started_at = self._started_at(slo, evaluated_at)
        if not slo.is_enabled:
            return SloEvaluation(
                current_rate=None,
                budget_remaining=None,
                data_state="no_data",
                started_at=started_at,
                ended_at=evaluated_at,
                reason="disabled",
            )
        try:
            measurement = self.metric_store.slo_measurement(
                SloMetricQuery(
                    service_namespace=slo.service.namespace,
                    service_name=slo.service.name,
                    environment=slo.environment,
                    endpoint=slo.endpoint,
                    sli_type=slo.sli_type,
                    latency_threshold_ms=slo.latency_threshold_ms,
                    started_at=started_at,
                    ended_at=evaluated_at,
                )
            )
        except (TelemetryStoreUnavailable, ValueError) as exc:
            return SloEvaluation(
                current_rate=None,
                budget_remaining=None,
                data_state="no_data",
                started_at=started_at,
                ended_at=evaluated_at,
                reason=str(exc),
            )
        if measurement.data_state == MetricDataState.NO_DATA or measurement.compliance_percent is None:
            return SloEvaluation(
                current_rate=None,
                budget_remaining=None,
                data_state="no_data",
                started_at=started_at,
                ended_at=evaluated_at,
                reason="no_samples",
            )
        current_rate = measurement.compliance_percent
        return SloEvaluation(
            current_rate=current_rate,
            budget_remaining=self._budget_remaining(float(slo.objective), current_rate),
            data_state="available",
            started_at=started_at,
            ended_at=evaluated_at,
        )

    @staticmethod
    def _measurement_key(slo: ApmSlo) -> tuple:
        return (
            slo.service.namespace,
            slo.service.name,
            slo.environment,
            slo.endpoint,
            slo.sli_type,
            slo.latency_threshold_ms,
            slo.evaluation_window,
            slo.is_enabled,
        )

    def _evaluation_for(self, slo: ApmSlo, cached: SloEvaluation) -> SloEvaluation:
        if cached.current_rate is None:
            return cached
        return SloEvaluation(
            current_rate=cached.current_rate,
            budget_remaining=self._budget_remaining(float(slo.objective), cached.current_rate),
            data_state=cached.data_state,
            started_at=cached.started_at,
            ended_at=cached.ended_at,
            reason=cached.reason,
        )

    def evaluate_many(self, slos: list[ApmSlo], *, evaluated_at: datetime) -> dict:
        cache: dict[tuple, SloEvaluation | Exception] = {}
        results: dict = {}
        for slo in slos:
            key = self._measurement_key(slo)
            if key not in cache:
                try:
                    cache[key] = self.evaluate(slo, evaluated_at=evaluated_at)
                except (TelemetryStoreUnavailable, ValueError) as exc:
                    cache[key] = exc
            cached = cache[key]
            results[slo.id] = self._evaluation_for(slo, cached) if isinstance(cached, SloEvaluation) else cached
        return results
