from __future__ import annotations

import math
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import NamedTuple
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.apm.adapters.errors import TelemetryStoreUnavailable
from apps.apm.models import ApmAlert, ApmAlertOutbox, ApmEvent, ApmPolicy, ApmPolicyTargetState, ApmService, ApmServiceInstance
from apps.apm.services.contracts import (
    DependencyMetricQuery,
    InstanceActivityQuery,
    MetricDataState,
    MetricStore,
    NotificationDelivery,
    NotificationDeliveryResult,
    NotificationDispatcher,
    PolicyQueryResult,
    PublishResult,
    ServiceMetricQuery,
    ServiceRedPoint,
    SloMetricQuery,
)
from apps.apm.services.metric_snapshots import ApmAlertMetricSnapshotStore, resolve_result_unit
from apps.apm.services.policy_conditions import evaluate_policy_conditions, uses_legacy_evaluation
from apps.apm.services.snapshots import ApmEventSnapshotStore
from apps.core.logger import apm_logger as logger

MAX_POLICY_TARGETS = 100
MAX_DEPENDENCY_TARGETS = 40
DRY_RUN_TARGET_LIMIT = 20
MAX_BASELINE_POLICY_TARGETS = 20
BASELINE_ZERO_REASON = "baseline_zero"
BASELINE_DAYS_INSUFFICIENT_REASON = "baseline_days_insufficient"
_EVALUATION_DELAY_RE = re.compile(r"^\s*(\d+)\s*s?\s*$")
DEFAULT_EVALUATION_DELAY_SECONDS = 60
MAX_EVALUATION_DELAY_SECONDS = 600


class PolicyTarget(NamedTuple):
    service: ApmService
    endpoint: str
    version: str
    instance_id: str
    request_count: int
    dependency: tuple | None = None


def dependency_parts(value) -> tuple[str, str, str] | None:
    if not value:
        return None
    if isinstance(value, dict):
        channel = str(value.get("channel") or "")
        system = str(value.get("system") or "")
        statement = str(value.get("statement") or "")
    else:
        channel, system, statement = (str(item) for item in value)
    if not channel or not system or not statement:
        return None
    return channel, system, statement


def dependency_label(value) -> str:
    parts = dependency_parts(value)
    if parts is None:
        return ""
    return f"{parts[1]} {parts[2]}"


def dependency_record(value) -> dict:
    parts = dependency_parts(value)
    if parts is None:
        return {}
    channel, system, statement = parts
    return {"channel": channel, "system": system, "statement": statement}


def policy_target_key(service_id, endpoint: str, version: str, instance_id: str = "", dependency=None) -> str:
    text = f"service={service_id}\x00endpoint={endpoint or ''}\x00version={version or ''}\x00instance={instance_id or ''}"
    parts = dependency_parts(dependency)
    if parts is not None:
        text += f"\x00dependency={parts[0]}\x00{parts[1]}\x00{parts[2]}"
    return sha256(text.encode()).hexdigest()


def effective_endpoint_mode(policy) -> str:
    mode = getattr(policy, "endpoint_mode", None) or ApmPolicy.EndpointMode.SERVICE
    if mode == ApmPolicy.EndpointMode.SERVICE and list(getattr(policy, "endpoints", None) or []):
        return ApmPolicy.EndpointMode.SELECTED
    return mode


def policy_organization_ids(policy) -> set[int]:
    override = getattr(policy, "_scope_organization_ids", None)
    if override is not None:
        return {int(item) for item in override}
    if not getattr(policy, "pk", None):
        return set()
    return set(policy.organization_links.values_list("organization", flat=True))


def service_visible_to_policy(policy, service) -> bool:
    """单服务策略保持组织解耦后的旧行为。多服务和应用范围才要求服务与策略组织相交。"""
    mode = getattr(policy, "scope_mode", None) or ApmPolicy.ScopeMode.SERVICE
    if mode == ApmPolicy.ScopeMode.SERVICE:
        return True
    policy_orgs = policy_organization_ids(policy)
    if not policy_orgs:
        return True
    service_orgs = set(service.organization_links.values_list("organization", flat=True))
    return bool(policy_orgs & service_orgs)


def scope_services(policy) -> list[ApmService]:
    mode = getattr(policy, "scope_mode", None) or ApmPolicy.ScopeMode.SERVICE
    if mode == ApmPolicy.ScopeMode.SERVICES:
        ordered = [str(item) for item in (getattr(policy, "service_ids", None) or [])]
        found = {
            str(item.id): item for item in ApmService.objects.filter(id__in=ordered, archived_at__isnull=True).prefetch_related("organization_links")
        }
        return [found[item] for item in ordered if item in found]
    if mode == ApmPolicy.ScopeMode.APPLICATION and getattr(policy, "application_id", None):
        return list(
            ApmService.objects.filter(application_id=policy.application_id, archived_at__isnull=True)
            .prefetch_related("organization_links")
            .order_by("normalized_namespace", "normalized_name", "id")
        )
    return [policy.service]


SEVERITY_LEVEL = {
    ApmPolicy.Severity.CRITICAL: "0",
    ApmPolicy.Severity.ERROR: "1",
    ApmPolicy.Severity.WARNING: "2",
}
MAX_NOTIFICATION_ATTEMPTS = 8
NOTIFICATION_CLAIM_TTL = timedelta(minutes=5)


def evaluation_delay() -> timedelta:
    """全局评估延迟。未设置或无法解析时用 60s，超出 0～600s 的值夹到边界。"""
    raw = os.environ.get("APM_POLICY_EVALUATION_DELAY", f"{DEFAULT_EVALUATION_DELAY_SECONDS}s")
    match = _EVALUATION_DELAY_RE.match(raw or "")
    seconds = int(match.group(1)) if match else DEFAULT_EVALUATION_DELAY_SECONDS
    seconds = min(MAX_EVALUATION_DELAY_SECONDS, max(0, seconds))
    return timedelta(seconds=seconds)


class DjangoApmPolicyService:
    """封装 APM 策略查询、连续窗口状态机和 outbox 补偿。"""

    def __init__(self, metric_store: MetricStore, notification_dispatcher: NotificationDispatcher):
        self.metric_store = metric_store
        self.notification_dispatcher = notification_dispatcher
        self._baseline_days_fallback = False

    def save_policy(self, policy: ApmPolicy) -> ApmPolicy:
        return policy

    @staticmethod
    def _cursor(evaluated_at: datetime) -> str:
        return evaluated_at.replace(second=0, microsecond=0).isoformat()

    @staticmethod
    def _bounded_decimal(value: Decimal) -> Decimal:
        quantized = value.quantize(Decimal("0.000001"))
        text = format(quantized, "f").rstrip("0").rstrip(".")
        return Decimal(text or "0")

    @classmethod
    def _apdex(cls, satisfied, tolerating, requests) -> Decimal | None:
        if requests is None or satisfied is None or tolerating is None or int(requests) <= 0:
            return None
        score = (Decimal(int(satisfied)) + Decimal(int(tolerating)) / Decimal(2)) / Decimal(int(requests))
        return cls._bounded_decimal(score)

    @classmethod
    def _slow_rate(cls, slow_count, requests) -> Decimal | None:
        if slow_count is None or requests is None or int(requests) <= 0:
            return None
        return cls._bounded_decimal(Decimal(int(slow_count)) / Decimal(int(requests)))

    @classmethod
    def _raw_value(cls, policy: ApmPolicy, red, metric: str | None = None) -> Decimal | None:
        metric = metric or policy.metric_type
        if metric == ApmPolicy.MetricType.ERROR_COUNT:
            return None if red.error_count is None else Decimal(int(red.error_count))
        if metric == ApmPolicy.MetricType.SLOW_REQUEST_COUNT:
            return None if red.slow_count is None else Decimal(int(red.slow_count))
        if metric == ApmPolicy.MetricType.SLOW_REQUEST_RATE:
            return cls._slow_rate(red.slow_count, red.request_count)
        if metric == ApmPolicy.MetricType.APDEX:
            return cls._apdex(red.satisfied_count, red.tolerating_count, red.request_count)
        values = {
            ApmPolicy.MetricType.ERROR_RATE: red.error_rate,
            ApmPolicy.MetricType.P50: red.p50_ms,
            ApmPolicy.MetricType.P75: red.p75_ms,
            ApmPolicy.MetricType.P90: red.p90_ms,
            ApmPolicy.MetricType.P95: red.p95_ms,
            ApmPolicy.MetricType.P99: red.p99_ms,
            ApmPolicy.MetricType.LATENCY_AVG: red.avg_ms,
            ApmPolicy.MetricType.LATENCY_MAX: red.max_ms,
            ApmPolicy.MetricType.THROUGHPUT: red.request_rate,
            ApmPolicy.MetricType.NO_TRAFFIC: red.request_rate,
        }
        value = values[metric]
        if metric == ApmPolicy.MetricType.NO_TRAFFIC and value is None:
            value = 0
        return Decimal(str(value)) if value is not None else None

    @staticmethod
    def _breached(comparator: str, threshold: Decimal, value: Decimal) -> bool:
        comparators = {
            ApmPolicy.Comparator.GREATER_THAN: value > threshold,
            ApmPolicy.Comparator.GREATER_THAN_OR_EQUAL: value >= threshold,
            ApmPolicy.Comparator.LESS_THAN: value < threshold,
            ApmPolicy.Comparator.LESS_THAN_OR_EQUAL: value <= threshold,
        }
        return comparators[comparator]

    @staticmethod
    def _thresholds(policy: ApmPolicy) -> list[dict[str, str]]:
        thresholds = list(policy.thresholds or [])
        rank = {"critical": 0, "error": 1, "warning": 2}
        return sorted(thresholds, key=lambda item: rank[str(item["severity"])])

    @classmethod
    def _matching_threshold(cls, policy: ApmPolicy, value: Decimal) -> dict[str, str] | None:
        return next(
            (
                threshold
                for threshold in cls._thresholds(policy)
                if cls._breached(
                    str(threshold["comparator"]),
                    Decimal(str(threshold["value"])),
                    value,
                )
            ),
            None,
        )

    @classmethod
    def _evaluation_threshold(
        cls,
        policy: ApmPolicy,
        state: ApmPolicyTargetState,
        result: PolicyQueryResult,
    ):
        if result.threshold:
            return dict(result.threshold)
        if result.data_state == MetricDataState.NO_DATA:
            return None
        if state.status != ApmPolicyTargetState.Status.ACTIVE or not state.current_severity:
            return None
        return next(
            (threshold for threshold in cls._thresholds(policy) if str(threshold["severity"]) == state.current_severity),
            None,
        )

    @classmethod
    def _series_value(cls, policy: ApmPolicy, point, metric: str | None = None) -> Decimal | None:
        metric = metric or policy.metric_type
        if metric == ApmPolicy.MetricType.ERROR_COUNT:
            return None if point.error_count is None else Decimal(int(point.error_count))
        if metric == ApmPolicy.MetricType.SLOW_REQUEST_COUNT:
            return None if point.slow_count is None else Decimal(int(point.slow_count))
        if metric == ApmPolicy.MetricType.SLOW_REQUEST_RATE:
            return cls._slow_rate(point.slow_count, point.request_count)
        if metric == ApmPolicy.MetricType.APDEX:
            return cls._apdex(point.satisfied_count, point.tolerating_count, point.request_count)
        value = {
            ApmPolicy.MetricType.ERROR_RATE: point.error_rate,
            ApmPolicy.MetricType.P50: point.p50_ms,
            ApmPolicy.MetricType.P75: point.p75_ms,
            ApmPolicy.MetricType.P90: point.p90_ms,
            ApmPolicy.MetricType.P95: point.p95_ms,
            ApmPolicy.MetricType.P99: point.p99_ms,
            ApmPolicy.MetricType.LATENCY_AVG: point.avg_ms,
            ApmPolicy.MetricType.LATENCY_MAX: point.max_ms,
            ApmPolicy.MetricType.THROUGHPUT: point.request_rate,
            ApmPolicy.MetricType.NO_TRAFFIC: point.request_rate,
        }[metric]
        return Decimal(str(value)) if value is not None else None

    @staticmethod
    def _version_values(policy: ApmPolicy, service) -> list[str]:
        if policy.version_mode == ApmPolicy.VersionMode.SPECIFIC:
            return list(policy.versions or [])
        if policy.version_mode == ApmPolicy.VersionMode.GROUPED:
            versions = list(
                ApmServiceInstance.objects.filter(
                    service=service,
                    environment=policy.environment,
                    archived_at__isnull=True,
                )
                .exclude(version="")
                .order_by("version")
                .values_list("version", flat=True)
                .distinct()[:100]
            )
            return versions or [""]
        return [""]

    @staticmethod
    def _targets(policy: ApmPolicy) -> list[tuple[str, str]]:
        endpoints = list(policy.endpoints or []) or [""]
        versions = DjangoApmPolicyService._version_values(policy, policy.service)
        return [(endpoint, version) for endpoint in endpoints for version in versions][:MAX_POLICY_TARGETS]

    def _target_limit(self, policy: ApmPolicy) -> int:
        if (policy.compare_mode or "") == ApmPolicy.CompareMode.BASELINE_DAYS and self._baseline_days_fallback:
            return MAX_BASELINE_POLICY_TARGETS
        return MAX_POLICY_TARGETS

    @staticmethod
    def _target_key(service_id, endpoint: str, version: str, instance_id: str = "", dependency=None) -> str:
        return policy_target_key(service_id, endpoint, version, instance_id, dependency)

    def _read_window(
        self,
        policy: ApmPolicy,
        *,
        started_at: datetime,
        ended_at: datetime,
        endpoint: str,
        version: str,
        include_endpoints: bool,
        cache: dict | None = None,
        instance_id: str = "",
        service=None,
        dependency=None,
    ):
        target = service or policy.service
        slow = getattr(policy, "slow_threshold_ms", None) or None
        apdex = getattr(policy, "apdex_threshold_ms", None) or None
        parts = dependency_parts(dependency)
        key = (
            str(getattr(target, "id", "") or ""),
            target.namespace,
            target.name,
            started_at,
            ended_at,
            endpoint or "",
            version or "",
            instance_id or "",
            parts or (),
            slow,
            apdex,
            include_endpoints,
        )
        if cache is not None and key in cache:
            return cache[key]
        if parts is not None:
            red = self.metric_store.dependency_red(
                DependencyMetricQuery(
                    service_namespace=target.namespace,
                    service_name=target.name,
                    environment=policy.environment,
                    started_at=started_at,
                    ended_at=ended_at,
                    channel=parts[0],
                    system=parts[1],
                    statement=parts[2],
                    slow_threshold_ms=slow,
                    apdex_threshold_ms=apdex,
                    include_breakdown=include_endpoints,
                )
            )
            if cache is not None:
                cache[key] = red
            return red
        red = self.metric_store.service_red(
            ServiceMetricQuery(
                service_namespace=target.namespace,
                service_name=target.name,
                environment=policy.environment,
                started_at=started_at,
                ended_at=ended_at,
                include_breakdown=True,
                include_endpoints=include_endpoints,
                endpoint=endpoint or "",
                version=version or "",
                slow_threshold_ms=slow,
                apdex_threshold_ms=apdex,
                instance_id=instance_id or "",
            )
        )
        if cache is not None:
            cache[key] = red
        return red

    @staticmethod
    def _baseline_offset(policy: ApmPolicy, window_minutes: int) -> timedelta | None:
        mode = policy.compare_mode or ApmPolicy.CompareMode.ABSOLUTE
        if mode == ApmPolicy.CompareMode.PREVIOUS_WINDOW:
            return timedelta(minutes=window_minutes)
        if mode == ApmPolicy.CompareMode.OFFSET_1H:
            return timedelta(hours=1)
        if mode == ApmPolicy.CompareMode.OFFSET_24H:
            return timedelta(hours=24)
        amount = getattr(policy, "compare_offset_amount", None)
        if mode == ApmPolicy.CompareMode.OFFSET_HOURS and amount:
            return timedelta(hours=int(amount))
        if mode == ApmPolicy.CompareMode.OFFSET_DAYS and amount:
            return timedelta(days=int(amount))
        return None

    @staticmethod
    def _below_min_samples(policy: ApmPolicy, red) -> bool:
        minimum = policy.min_request_count
        if minimum is None:
            return False
        count = red.request_count if red.request_count is not None else 0
        return count < minimum

    @staticmethod
    def _sample_stdev(values: list[Decimal], mean: Decimal) -> Decimal:
        if len(values) < 2:
            return Decimal(0)
        square = sum(((item - mean) ** 2 for item in values), Decimal(0))
        return (square / Decimal(len(values) - 1)).sqrt()

    @staticmethod
    def _compared_value(current: Decimal, baseline: Decimal, kind: str) -> Decimal:
        if kind == ApmPolicy.CompareValueKind.PERCENT:
            raw = (current - baseline) / baseline * Decimal(100)
        else:
            raw = current - baseline
        quantized = raw.quantize(Decimal("0.000001"))
        text = format(quantized, "f").rstrip("0").rstrip(".")
        return Decimal(text or "0")

    @staticmethod
    def _decimal_text(value: Decimal | None) -> str | None:
        if value is None:
            return None
        rendered = format(value, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return rendered or "0"

    def _query_result(
        self,
        policy: ApmPolicy,
        *,
        value: Decimal | None,
        breached: bool | None,
        evaluated_at: datetime,
        data_state: MetricDataState,
        series,
        threshold=None,
        current_value: Decimal | None = None,
        baseline_value: Decimal | None = None,
        baseline_series=(),
        request_count: int | None = None,
        reason: str = "",
        window_ended_at: datetime | None = None,
        baseline_days_used: int | None = None,
        condition_rows=(),
        guard_rows=(),
        guard_blocked: bool = False,
        budget_remaining: Decimal | None = None,
    ) -> PolicyQueryResult:
        return PolicyQueryResult(
            value=value,
            breached=breached,
            evaluated_at=evaluated_at,
            data_state=data_state,
            series=series,
            threshold=threshold,
            current_value=current_value,
            baseline_value=baseline_value,
            baseline_series=baseline_series,
            request_count=request_count,
            reason=reason,
            result_unit=resolve_result_unit(policy),
            window_ended_at=window_ended_at,
            baseline_days_used=baseline_days_used,
            condition_rows=tuple(condition_rows),
            guard_rows=tuple(guard_rows),
            guard_blocked=guard_blocked,
            budget_remaining=budget_remaining,
        )

    def test_query(
        self,
        policy: ApmPolicy,
        *,
        evaluated_at: datetime,
        endpoint: str | None = None,
        version: str | None = None,
        cache: dict | None = None,
        instance_id: str = "",
        target_service=None,
        dependency=None,
    ) -> PolicyQueryResult:
        if getattr(policy, "metric_type", None) == ApmPolicy.MetricType.SLO_BURN_RATE:
            return self._evaluate_burn_rate(
                policy,
                evaluated_at=evaluated_at,
                target_service=target_service,
            )
        if isinstance(policy, ApmPolicy) and not uses_legacy_evaluation(policy):
            return evaluate_policy_conditions(
                self,
                policy,
                evaluated_at=evaluated_at,
                endpoint=endpoint,
                version=version,
                instance_id=instance_id,
                target_service=target_service,
                dependency=dependency,
            )
        target_endpoint, target_version = (endpoint, version) if endpoint is not None else self._targets(policy)[0]
        window = max(policy.metric_window, 1)
        window_end = evaluated_at - evaluation_delay()
        current_start = window_end - timedelta(minutes=window)
        current = self._read_window(
            policy,
            started_at=current_start,
            ended_at=window_end,
            endpoint=target_endpoint or "",
            version=target_version or "",
            include_endpoints=True,
            cache=cache,
            instance_id=instance_id,
            service=target_service,
            dependency=dependency,
        )
        current_value = self._raw_value(policy, current)
        if current_value is None:
            return self._query_result(
                policy,
                value=None,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.NO_DATA,
                series=current.timeseries,
                request_count=current.request_count,
                window_ended_at=window_end,
            )
        # 最低请求数门与比较基准正交：绝对阈值的低流量窗同样不评。
        if self._below_min_samples(policy, current):
            return self._query_result(
                policy,
                value=None,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.INSUFFICIENT_SAMPLES,
                series=current.timeseries,
                current_value=current_value,
                request_count=current.request_count,
                window_ended_at=window_end,
            )
        if (policy.compare_mode or ApmPolicy.CompareMode.ABSOLUTE) == ApmPolicy.CompareMode.BASELINE_DAYS:
            return self._compare_baseline_days(
                policy,
                evaluated_at=evaluated_at,
                current=current,
                current_value=current_value,
                current_start=current_start,
                window_end=window_end,
                endpoint=target_endpoint or "",
                version=target_version or "",
                cache=cache,
                instance_id=instance_id,
                target_service=target_service,
                dependency=dependency,
            )
        offset = self._baseline_offset(policy, window)
        if offset is None:
            threshold = self._matching_threshold(policy, current_value)
            decision = self._decision(policy, current_value, threshold)
            return self._query_result(
                policy,
                value=current_value,
                breached=decision["breached"],
                evaluated_at=evaluated_at,
                data_state=decision["data_state"],
                series=current.timeseries,
                threshold=decision["threshold"],
                current_value=current_value,
                request_count=current.request_count,
                window_ended_at=window_end,
            )
        baseline = self._read_window(
            policy,
            started_at=current_start - offset,
            ended_at=window_end - offset,
            endpoint=target_endpoint or "",
            version=target_version or "",
            include_endpoints=False,
            cache=cache,
            instance_id=instance_id,
            service=target_service,
            dependency=dependency,
        )
        baseline_value = self._raw_value(policy, baseline)
        if baseline_value is None or self._below_min_samples(policy, baseline):
            return self._query_result(
                policy,
                value=None,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.MISSING_BASELINE,
                series=current.timeseries,
                current_value=current_value,
                baseline_value=baseline_value,
                baseline_series=baseline.timeseries,
                request_count=current.request_count,
                window_ended_at=window_end,
            )
        kind = policy.compare_value_kind or ""
        if kind == ApmPolicy.CompareValueKind.PERCENT and baseline_value == 0:
            return self._query_result(
                policy,
                value=None,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.MISSING_BASELINE,
                series=current.timeseries,
                current_value=current_value,
                baseline_value=baseline_value,
                baseline_series=baseline.timeseries,
                request_count=current.request_count,
                window_ended_at=window_end,
                reason=BASELINE_ZERO_REASON,
            )
        compared = self._compared_value(current_value, baseline_value, kind)
        threshold = self._matching_threshold(policy, compared)
        decision = self._decision(policy, compared, threshold)
        return self._query_result(
            policy,
            value=compared,
            breached=decision["breached"],
            evaluated_at=evaluated_at,
            data_state=decision["data_state"],
            series=current.timeseries,
            threshold=decision["threshold"],
            current_value=current_value,
            baseline_value=baseline_value,
            baseline_series=baseline.timeseries,
            request_count=current.request_count,
            window_ended_at=window_end,
        )

    def _compare_baseline_days(
        self,
        policy: ApmPolicy,
        *,
        evaluated_at: datetime,
        current,
        current_value: Decimal,
        current_start: datetime,
        window_end: datetime,
        endpoint: str,
        version: str,
        cache: dict | None = None,
        instance_id: str = "",
        target_service=None,
        dependency=None,
    ) -> PolicyQueryResult:
        amount = int(policy.compare_offset_amount or 0)
        windows = tuple((current_start - timedelta(days=day), window_end - timedelta(days=day)) for day in range(1, max(amount, 0) + 1))
        if amount < 2:
            return self._query_result(
                policy,
                value=None,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.MISSING_BASELINE,
                series=current.timeseries,
                current_value=current_value,
                request_count=current.request_count,
                window_ended_at=window_end,
                reason=BASELINE_DAYS_INSUFFICIENT_REASON,
                baseline_days_used=0,
            )
        reds = self._read_baseline_days(
            policy,
            windows,
            endpoint=endpoint,
            version=version,
            cache=cache,
            instance_id=instance_id,
            target_service=target_service,
            dependency=dependency,
        )
        usable = []
        for red in reds:
            if not self._baseline_day_usable(policy, red):
                continue
            value = self._raw_value(policy, red)
            if value is None:
                continue
            usable.append(value)
        used = len(usable)
        if used < math.ceil(amount / 2):
            return self._query_result(
                policy,
                value=None,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.MISSING_BASELINE,
                series=current.timeseries,
                current_value=current_value,
                request_count=current.request_count,
                window_ended_at=window_end,
                reason=BASELINE_DAYS_INSUFFICIENT_REASON,
                baseline_days_used=used,
            )
        mean = sum(usable, Decimal(0)) / Decimal(used)
        baseline_value = self._bounded_decimal(mean)
        kind = policy.compare_value_kind or ""
        if kind == ApmPolicy.CompareValueKind.SIGMA and used < 3:
            return self._query_result(
                policy,
                value=None,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.MISSING_BASELINE,
                series=current.timeseries,
                current_value=current_value,
                baseline_value=baseline_value,
                request_count=current.request_count,
                window_ended_at=window_end,
                reason=BASELINE_DAYS_INSUFFICIENT_REASON,
                baseline_days_used=used,
            )
        if kind == ApmPolicy.CompareValueKind.SIGMA:
            sigma = self._sample_stdev(usable, mean)
            if sigma == 0:
                return self._query_result(
                    policy,
                    value=None,
                    breached=None,
                    evaluated_at=evaluated_at,
                    data_state=MetricDataState.MISSING_BASELINE,
                    series=current.timeseries,
                    current_value=current_value,
                    baseline_value=baseline_value,
                    request_count=current.request_count,
                    window_ended_at=window_end,
                    reason=BASELINE_DAYS_INSUFFICIENT_REASON,
                    baseline_days_used=used,
                )
            compared = self._bounded_decimal((current_value - mean) / sigma)
            threshold = self._matching_threshold(policy, compared)
            decision = self._decision(policy, compared, threshold)
            return self._query_result(
                policy,
                value=compared,
                breached=decision["breached"],
                evaluated_at=evaluated_at,
                data_state=decision["data_state"],
                series=current.timeseries,
                threshold=decision["threshold"],
                current_value=current_value,
                baseline_value=baseline_value,
                baseline_series=self._mean_line(policy, current.timeseries, baseline_value, current_start, window_end),
                request_count=current.request_count,
                window_ended_at=window_end,
                baseline_days_used=used,
            )
        if kind == ApmPolicy.CompareValueKind.PERCENT and baseline_value == 0:
            return self._query_result(
                policy,
                value=None,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.MISSING_BASELINE,
                series=current.timeseries,
                current_value=current_value,
                baseline_value=baseline_value,
                request_count=current.request_count,
                window_ended_at=window_end,
                reason=BASELINE_ZERO_REASON,
                baseline_days_used=used,
            )
        compared = self._compared_value(current_value, baseline_value, kind)
        threshold = self._matching_threshold(policy, compared)
        decision = self._decision(policy, compared, threshold)
        return self._query_result(
            policy,
            value=compared,
            breached=decision["breached"],
            evaluated_at=evaluated_at,
            data_state=decision["data_state"],
            series=current.timeseries,
            threshold=decision["threshold"],
            current_value=current_value,
            baseline_value=baseline_value,
            baseline_series=self._mean_line(policy, current.timeseries, baseline_value, current_start, window_end),
            request_count=current.request_count,
            window_ended_at=window_end,
            baseline_days_used=used,
        )

    def _read_baseline_days(
        self,
        policy: ApmPolicy,
        windows,
        *,
        endpoint: str,
        version: str,
        cache: dict | None = None,
        instance_id: str = "",
        target_service=None,
        dependency=None,
    ):
        if not self._baseline_days_fallback:
            reader_name = "dependency_red_by_day" if dependency_parts(dependency) else "service_red_by_day"
            reader = getattr(self.metric_store, reader_name, None)
            if reader is not None:
                try:
                    query = self._metric_query(
                        policy,
                        started_at=windows[-1][0],
                        ended_at=windows[0][1],
                        endpoint=endpoint,
                        version=version,
                        instance_id=instance_id,
                        service=target_service,
                        dependency=dependency,
                    )
                    reds = tuple(reader(query, windows))
                    if len(reds) != len(windows):
                        raise TelemetryStoreUnavailable("baseline")
                    return reds
                except Exception:
                    self._baseline_days_fallback = True
            else:
                self._baseline_days_fallback = True
        reds = []
        try:
            for started_at, ended_at in windows:
                reds.append(
                    self._read_window(
                        policy,
                        started_at=started_at,
                        ended_at=ended_at,
                        endpoint=endpoint,
                        version=version,
                        include_endpoints=False,
                        cache=cache,
                        instance_id=instance_id,
                        service=target_service,
                        dependency=dependency,
                    )
                )
        except Exception as exc:
            self._log_baseline_failure(policy, exc)
            raise TelemetryStoreUnavailable("baseline") from None
        return tuple(reds)

    def _metric_query(self, policy, *, started_at, ended_at, endpoint, version, instance_id: str = "", service=None, dependency=None):
        target = service or policy.service
        parts = dependency_parts(dependency)
        slow = getattr(policy, "slow_threshold_ms", None) or None
        apdex = getattr(policy, "apdex_threshold_ms", None) or None
        if parts is not None:
            return DependencyMetricQuery(
                service_namespace=target.namespace,
                service_name=target.name,
                environment=policy.environment,
                started_at=started_at,
                ended_at=ended_at,
                channel=parts[0],
                system=parts[1],
                statement=parts[2],
                slow_threshold_ms=slow,
                apdex_threshold_ms=apdex,
                include_breakdown=False,
            )
        return ServiceMetricQuery(
            service_namespace=target.namespace,
            service_name=target.name,
            environment=policy.environment,
            started_at=started_at,
            ended_at=ended_at,
            include_breakdown=False,
            include_endpoints=False,
            endpoint=endpoint or "",
            version=version or "",
            slow_threshold_ms=getattr(policy, "slow_threshold_ms", None) or None,
            apdex_threshold_ms=getattr(policy, "apdex_threshold_ms", None) or None,
            instance_id=instance_id or "",
        )

    @staticmethod
    def _baseline_day_usable(policy: ApmPolicy, red) -> bool:
        count = red.request_count if red.request_count is not None else 0
        if count <= 0:
            return False
        minimum = policy.min_request_count
        return minimum is None or count >= minimum

    @classmethod
    def _mean_line(cls, policy: ApmPolicy, series, mean: Decimal, started_at: datetime, ended_at: datetime):
        stamps = [point.timestamp for point in series] or [started_at, ended_at]
        return tuple(cls._mean_point(policy.metric_type, stamp, mean) for stamp in stamps)

    @staticmethod
    def _mean_point(metric: str, timestamp: datetime, mean: Decimal) -> ServiceRedPoint:
        value = float(mean)
        fields = {
            ApmPolicy.MetricType.ERROR_RATE: "error_rate",
            ApmPolicy.MetricType.P50: "p50_ms",
            ApmPolicy.MetricType.P75: "p75_ms",
            ApmPolicy.MetricType.P90: "p90_ms",
            ApmPolicy.MetricType.P95: "p95_ms",
            ApmPolicy.MetricType.P99: "p99_ms",
            ApmPolicy.MetricType.LATENCY_AVG: "avg_ms",
            ApmPolicy.MetricType.LATENCY_MAX: "max_ms",
            ApmPolicy.MetricType.ERROR_COUNT: "error_count",
            ApmPolicy.MetricType.SLOW_REQUEST_COUNT: "slow_count",
            ApmPolicy.MetricType.THROUGHPUT: "request_rate",
            ApmPolicy.MetricType.NO_TRAFFIC: "request_rate",
        }
        point = {
            "timestamp": timestamp,
            "request_rate": None,
            "error_rate": None,
            "p95_ms": None,
            "p99_ms": None,
        }
        field = fields.get(metric)
        if field:
            point[field] = value
        elif metric == ApmPolicy.MetricType.SLOW_REQUEST_RATE:
            point["request_count"] = 1_000_000
            point["slow_count"] = int(round(value * 1_000_000))
        elif metric == ApmPolicy.MetricType.APDEX:
            point["request_count"] = 1_000_000
            point["satisfied_count"] = int(round(value * 1_000_000))
            point["tolerating_count"] = 0
        return ServiceRedPoint(**point)

    @staticmethod
    def _log_baseline_failure(policy: ApmPolicy, exc: Exception) -> None:
        proxy = RuntimeError(type(exc).__name__)
        logger.warning(
            "event=apm_policy_baseline_failed policy_id=%s failed_stage=%s error_type=%s",
            "" if getattr(policy, "pk", None) is None else str(policy.pk),
            "baseline",
            type(exc).__name__,
            exc_info=(type(proxy), proxy, exc.__traceback__),
        )

    @staticmethod
    def _log_burn_failure(policy: ApmPolicy, exc: Exception) -> None:
        proxy = RuntimeError(type(exc).__name__)
        logger.warning(
            "event=apm_policy_burn_failed policy_id=%s failed_stage=%s error_type=%s",
            "" if getattr(policy, "pk", None) is None else str(policy.pk),
            "slo_burn_rate",
            type(exc).__name__,
            exc_info=(type(proxy), proxy, exc.__traceback__),
        )

    def _read_burn_window(self, policy: ApmPolicy, slo, service, started_at: datetime, ended_at: datetime):
        query = SloMetricQuery(
            service_namespace=service.namespace,
            service_name=service.name,
            environment=slo.environment,
            endpoint=slo.endpoint or "",
            sli_type=slo.sli_type,
            latency_threshold_ms=slo.latency_threshold_ms,
            started_at=started_at,
            ended_at=ended_at,
        )
        try:
            return self.metric_store.slo_measurement(query)
        except TelemetryStoreUnavailable:
            raise
        except Exception as exc:
            self._log_burn_failure(policy, exc)
            raise TelemetryStoreUnavailable("slo burn rate unavailable") from None

    @classmethod
    def _burn_rate(cls, objective_percent, compliance_percent) -> Decimal | None:
        objective = Decimal(str(objective_percent)) / Decimal(100)
        compliance = Decimal(str(compliance_percent)) / Decimal(100)
        allowed = Decimal(1) - objective
        if allowed <= 0:
            return None
        return cls._bounded_decimal((Decimal(1) - compliance) / allowed)

    @classmethod
    def _budget_remaining(cls, objective_percent, compliance_percent) -> Decimal:
        allowed = Decimal(100) - Decimal(str(objective_percent))
        current_failure = Decimal(100) - Decimal(str(compliance_percent))
        if allowed <= 0:
            return Decimal(100) if current_failure <= 0 else Decimal(0)
        value = (allowed - current_failure) / allowed * Decimal(100)
        if value < 0:
            value = Decimal(0)
        if value > 100:
            value = Decimal(100)
        return cls._bounded_decimal(value)

    @staticmethod
    def _burn_compliance(measurement):
        if measurement is None or measurement.compliance_percent is None:
            return None
        if measurement.data_state != MetricDataState.AVAILABLE:
            return None
        return measurement.compliance_percent

    def _evaluate_burn_rate(self, policy: ApmPolicy, *, evaluated_at: datetime, target_service) -> PolicyQueryResult:
        slo = getattr(policy, "slo", None)
        if slo is None:
            return self._query_result(
                policy,
                value=None,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.NO_DATA,
                series=(),
                reason="no_data",
                window_ended_at=evaluated_at,
            )
        source = getattr(slo, "service", None) or target_service
        ended_at = evaluated_at
        long_minutes = int(policy.burn_long_window_minutes or 0)
        short_minutes = int(policy.burn_short_window_minutes or 0)
        long_measurement = self._read_burn_window(
            policy,
            slo,
            source,
            ended_at - timedelta(minutes=long_minutes),
            ended_at,
        )
        long_compliance = self._burn_compliance(long_measurement)
        if long_compliance is None:
            return self._query_result(
                policy,
                value=None,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.NO_DATA,
                series=(),
                reason="no_data",
                window_ended_at=ended_at,
            )
        short_measurement = self._read_burn_window(
            policy,
            slo,
            source,
            ended_at - timedelta(minutes=short_minutes),
            ended_at,
        )
        short_compliance = self._burn_compliance(short_measurement)
        long_burn = self._burn_rate(slo.objective, long_compliance)
        if short_compliance is None or long_burn is None:
            return self._query_result(
                policy,
                value=long_burn,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.INSUFFICIENT_SAMPLES if short_compliance is None else MetricDataState.NO_DATA,
                series=(),
                reason="insufficient_samples" if short_compliance is None else "no_data",
                window_ended_at=ended_at,
                current_value=long_burn,
            )
        short_burn = self._burn_rate(slo.objective, short_compliance)
        if short_burn is None:
            return self._query_result(
                policy,
                value=long_burn,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.NO_DATA,
                series=(),
                reason="no_data",
                window_ended_at=ended_at,
                current_value=long_burn,
            )
        long_hit = self._matching_threshold(policy, long_burn)
        short_hit = self._matching_threshold(policy, short_burn)
        if long_hit and short_hit:
            threshold = long_hit if self._severity_rank(str(long_hit["severity"])) >= self._severity_rank(str(short_hit["severity"])) else short_hit
            breached = True
            value = long_burn if threshold is long_hit else short_burn
        else:
            threshold = None
            breached = False
            value = long_burn
        return self._query_result(
            policy,
            value=value,
            breached=breached,
            evaluated_at=evaluated_at,
            data_state=MetricDataState.AVAILABLE,
            series=(),
            threshold=threshold,
            current_value=long_burn,
            baseline_value=short_burn,
            window_ended_at=ended_at,
            budget_remaining=self._budget_remaining(slo.objective, long_compliance),
        )

    def retire_policies_for_slo(self, slo, *, evaluated_at: datetime) -> None:
        policies = ApmPolicy.objects.filter(slo=slo).select_related("service", "slo")
        for policy in policies:
            for state in list(policy.target_states.filter(status=ApmPolicyTargetState.Status.ACTIVE)):
                if state.active_alert_id:
                    result = self._query_result(
                        policy,
                        value=None,
                        breached=False,
                        evaluated_at=evaluated_at,
                        data_state=MetricDataState.AVAILABLE,
                        series=(),
                    )
                    self._record_event(
                        policy,
                        state,
                        result,
                        evaluated_at,
                        state.active_alert_id,
                        ApmEvent.Action.RECOVERED,
                        {"severity": state.current_severity or ApmPolicy.Severity.WARNING, "comparator": "gt", "value": ""},
                    )
                state.delete()
            policy.is_enabled = False
            policy.save(update_fields=["is_enabled", "updated_at"])

    def _decision(self, policy: ApmPolicy, value: Decimal, threshold):
        """有恢复线且落在两线之间记 hold。越线优先于恢复线。"""
        if threshold is not None:
            return {
                "breached": True,
                "data_state": MetricDataState.AVAILABLE,
                "threshold": threshold,
            }
        recovery = getattr(policy, "recovery_threshold", None) or {}
        if recovery and value is not None and not self._breached(str(recovery["comparator"]), Decimal(str(recovery["value"])), value):
            return {
                "breached": False,
                "data_state": MetricDataState.HOLD,
                "threshold": None,
            }
        return {
            "breached": False,
            "data_state": MetricDataState.AVAILABLE,
            "threshold": None,
        }

    def _log_scope_failure(self, policy, stage: str, exc: Exception) -> None:
        proxy = RuntimeError(type(exc).__name__)
        logger.warning(
            "event=apm_policy_scope_failed policy_id=%s failed_stage=%s error_type=%s",
            "" if getattr(policy, "pk", None) is None else str(policy.pk),
            stage,
            type(exc).__name__,
            exc_info=(type(proxy), proxy, exc.__traceback__),
        )

    def _window_bounds(self, policy, evaluated_at: datetime) -> tuple[datetime, datetime]:
        window = max(policy.metric_window, 1)
        window_end = evaluated_at - evaluation_delay()
        return window_end - timedelta(minutes=window), window_end

    def _active_endpoints(self, policy, service, started_at: datetime, ended_at: datetime) -> list[tuple[str, int]]:
        query = ServiceMetricQuery(
            service_namespace=service.namespace,
            service_name=service.name,
            environment=policy.environment,
            started_at=started_at,
            ended_at=ended_at,
            include_breakdown=False,
            include_endpoints=False,
        )
        try:
            rows = self.metric_store.service_endpoints(query, limit=MAX_POLICY_TARGETS)
        except TelemetryStoreUnavailable:
            raise
        except Exception as exc:
            self._log_scope_failure(policy, "service_endpoints", exc)
            raise TelemetryStoreUnavailable("service_endpoints") from None
        ranked = [(row.endpoint, int((row.request_rate or 0) * 1_000_000)) for row in rows if row.endpoint]
        ranked.sort(key=lambda item: -item[1])
        return ranked

    def _active_instances(self, policy, service, started_at: datetime, ended_at: datetime) -> list[tuple[str, int]]:
        try:
            activities = self.metric_store.instance_activity(InstanceActivityQuery(started_at=started_at, ended_at=ended_at))
        except TelemetryStoreUnavailable:
            raise
        except Exception as exc:
            self._log_scope_failure(policy, "instance_activity", exc)
            raise TelemetryStoreUnavailable("instance_activity") from None
        ids = []
        for item in activities:
            if item.service_name != service.name or (item.service_namespace or "") != (service.namespace or ""):
                continue
            if item.environment != policy.environment or not item.instance_id:
                continue
            ids.append(item.instance_id)
        return [(item, 0) for item in dict.fromkeys(ids)]

    def _active_dependencies(self, policy, service, started_at: datetime, ended_at: datetime) -> list[tuple[tuple[str, str, str], int]]:
        try:
            rows = self.metric_store.client_db_rollups(service.namespace, service.name, policy.environment, started_at, ended_at)
        except TelemetryStoreUnavailable:
            raise
        except Exception as exc:
            self._log_scope_failure(policy, "client_db_rollups", exc)
            raise TelemetryStoreUnavailable("client_db_rollups") from None
        ranked = []
        for row in rows:
            parts = dependency_parts(row)
            if parts is None:
                continue
            ranked.append((parts, int(row.get("call_count") or 0)))
        ranked.sort(key=lambda item: -item[1])
        return ranked

    def _expand_dependencies(self, policy, service, *, evaluated_at: datetime):
        started_at, ended_at = self._window_bounds(policy, evaluated_at)
        configured = [dependency_parts(item) for item in (getattr(policy, "dependencies", None) or [])]
        configured = [item for item in configured if item is not None]
        if configured:
            rows = [(item, 0) for item in configured]
        else:
            rows = self._active_dependencies(policy, service, started_at, ended_at)
        limit = min(self._target_limit(policy), MAX_DEPENDENCY_TARGETS)
        product = [PolicyTarget(service, "", "", "", count, item) for item, count in rows[:limit]]
        return product, len(rows) > limit, [], [], [item for item, _count in rows]

    def _expand_service(self, policy, service, *, evaluated_at: datetime):
        if getattr(policy, "metric_type", None) == ApmPolicy.MetricType.SLO_BURN_RATE:
            slo = getattr(policy, "slo", None)
            endpoint = "" if slo is None else (slo.endpoint or "")
            return [PolicyTarget(service, endpoint, "", "", 0)], False, [endpoint], [], []
        if (getattr(policy, "target_kind", None) or ApmPolicy.TargetKind.ENTRY) == ApmPolicy.TargetKind.DEPENDENCY:
            return self._expand_dependencies(policy, service, evaluated_at=evaluated_at)
        started_at, ended_at = self._window_bounds(policy, evaluated_at)
        mode = effective_endpoint_mode(policy)
        if mode == ApmPolicy.EndpointMode.ALL:
            endpoint_rows = self._active_endpoints(policy, service, started_at, ended_at)
        elif mode == ApmPolicy.EndpointMode.SELECTED:
            names = list(policy.endpoints or []) or [""]
            endpoint_rows = [(name, 0) for name in names]
        else:
            endpoint_rows = [("", 0)]
        versions = self._version_values(policy, service) or [""]
        if (getattr(policy, "instance_mode", None) or ApmPolicy.InstanceMode.ALL) == ApmPolicy.InstanceMode.GROUPED:
            instance_rows = self._active_instances(policy, service, started_at, ended_at)
        else:
            instance_rows = [("", 0)]
        product = [
            PolicyTarget(service, endpoint, version, instance_id, int(endpoint_count or instance_count or 0))
            for endpoint, endpoint_count in endpoint_rows
            for version in versions
            for instance_id, instance_count in instance_rows
        ]
        product.sort(key=lambda item: -item.request_count)
        limit = self._target_limit(policy)
        return (
            product[:limit],
            len(product) > limit,
            [name for name, _count in endpoint_rows],
            [item for item, _count in instance_rows],
            [],
        )

    def _close_absent_targets(
        self,
        policy,
        service,
        *,
        known_endpoints,
        known_instances,
        known_dependencies,
        evaluated_at: datetime,
        cursor: str,
    ) -> None:
        dynamic_endpoints = effective_endpoint_mode(policy) == ApmPolicy.EndpointMode.ALL
        dynamic_instances = (getattr(policy, "instance_mode", None) or ApmPolicy.InstanceMode.ALL) == ApmPolicy.InstanceMode.GROUPED
        dependency_mode = (getattr(policy, "target_kind", None) or ApmPolicy.TargetKind.ENTRY) == ApmPolicy.TargetKind.DEPENDENCY
        burn = getattr(policy, "metric_type", None) == ApmPolicy.MetricType.SLO_BURN_RATE
        if not dynamic_endpoints and not dynamic_instances and not dependency_mode and not burn:
            return
        endpoint_set = set(known_endpoints)
        instance_set = set(known_instances)
        dependency_set = {dependency_parts(item) for item in (known_dependencies or [])}
        dependency_set.discard(None)
        states = list(ApmPolicyTargetState.objects.filter(policy=policy, service=service))
        for state in states:
            ident = dependency_parts(getattr(state, "dependency", None))
            absent = (
                (burn and state.endpoint not in endpoint_set)
                or (dynamic_endpoints and bool(state.endpoint) and state.endpoint not in endpoint_set)
                or (dynamic_instances and bool(state.instance_id) and state.instance_id not in instance_set)
                or (dependency_mode and ident is not None and ident not in dependency_set)
            )
            if not absent or state.evaluation_cursor == cursor:
                continue
            state.missed_rounds = (state.missed_rounds or 0) + 1
            state.evaluation_cursor = cursor
            if state.missed_rounds < (policy.recover_after or 1):
                state.save(update_fields=["missed_rounds", "evaluation_cursor", "updated_at"])
                continue
            if state.status == ApmPolicyTargetState.Status.ACTIVE and state.active_alert_id:
                result = self._query_result(
                    policy,
                    value=None,
                    breached=False,
                    evaluated_at=evaluated_at,
                    data_state=MetricDataState.AVAILABLE,
                    series=(),
                )
                self._record_event(
                    policy,
                    state,
                    result,
                    evaluated_at,
                    state.active_alert_id,
                    ApmEvent.Action.RECOVERED,
                    {"severity": state.current_severity or ApmPolicy.Severity.WARNING, "comparator": "gt", "value": ""},
                )
            state.delete()

    @staticmethod
    def _invisible_item(service) -> dict:
        return {
            "service": service.name,
            "instance": "",
            "dependency": "",
            "endpoint": "",
            "version": "",
            "verdict": "service_not_visible",
            "current_value": None,
            "baseline_value": None,
            "compared_value": None,
            "request_count": None,
            "matched_threshold": None,
            "reason": "服务不在策略组织可见范围",
            "hit_history_text": "",
            "baseline_days_used": None,
        }

    def _replay_history(self, policy: ApmPolicy, window: int) -> timedelta:
        mode = policy.compare_mode or ApmPolicy.CompareMode.ABSOLUTE
        if mode == ApmPolicy.CompareMode.BASELINE_DAYS:
            return timedelta(days=int(policy.compare_offset_amount or 0))
        if mode == ApmPolicy.CompareMode.PREVIOUS_WINDOW:
            return timedelta(minutes=window)
        offset = self._baseline_offset(policy, window)
        return offset or timedelta(0)

    def _replay_ends(self, window_end: datetime, window: int) -> list[datetime]:
        slots = (24 * 60) // window
        return [window_end - timedelta(minutes=window * (slots - 1 - index)) for index in range(slots)]

    def _read_replay_series(self, policy, target: PolicyTarget, started_at: datetime, ended_at: datetime, window: int) -> dict:
        query = self._metric_query(
            policy,
            started_at=started_at,
            ended_at=ended_at,
            endpoint=target.endpoint,
            version=target.version,
            instance_id=target.instance_id,
            service=target.service,
            dependency=target.dependency,
        )
        reader_name = "dependency_red_by_window" if dependency_parts(target.dependency) else "service_red_by_window"
        reader = getattr(self.metric_store, reader_name, None)
        if reader is None:
            return {}
        return {end: red for end, red in reader(query, window)}

    def _replay_compared(self, policy: ApmPolicy, series: dict, end: datetime, window: int) -> Decimal | None:
        current = series.get(end)
        if current is None:
            return None
        current_value = self._raw_value(policy, current)
        if current_value is None:
            return None
        mode = policy.compare_mode or ApmPolicy.CompareMode.ABSOLUTE
        kind = policy.compare_value_kind or ""
        if mode == ApmPolicy.CompareMode.ABSOLUTE or kind == "":
            return current_value
        if mode == ApmPolicy.CompareMode.BASELINE_DAYS:
            amount = int(policy.compare_offset_amount or 0)
            usable = []
            for day in range(1, amount + 1):
                red = series.get(end - timedelta(days=day))
                if red is None or not self._baseline_day_usable(policy, red):
                    continue
                value = self._raw_value(policy, red)
                if value is not None:
                    usable.append(value)
            if kind == ApmPolicy.CompareValueKind.SIGMA and len(usable) < 3:
                return None
            if len(usable) < math.ceil(amount / 2):
                return None
            mean = sum(usable, Decimal(0)) / Decimal(len(usable))
            if kind == ApmPolicy.CompareValueKind.SIGMA:
                sigma = self._sample_stdev(usable, mean)
                if sigma == 0:
                    return None
                return self._bounded_decimal((current_value - mean) / sigma)
            if kind == ApmPolicy.CompareValueKind.PERCENT and mean == 0:
                return None
            return self._compared_value(current_value, mean, kind)
        baseline_end = end - (self._replay_history(policy, window) or timedelta(0))
        baseline = series.get(baseline_end)
        if baseline is None:
            return None
        baseline_value = self._raw_value(policy, baseline)
        if baseline_value is None:
            return None
        if kind == ApmPolicy.CompareValueKind.PERCENT and baseline_value == 0:
            return None
        return self._compared_value(current_value, baseline_value, kind)

    def _replay_target(self, policy: ApmPolicy, target: PolicyTarget, *, evaluated_at: datetime) -> dict:
        if getattr(policy, "metric_type", None) == ApmPolicy.MetricType.SLO_BURN_RATE:
            return self._replay_burn(policy, target, evaluated_at)
        window = max(int(policy.metric_window or 1), 1)
        _start, window_end = self._window_bounds(policy, evaluated_at)
        ends = self._replay_ends(window_end, window)
        if not ends:
            return {"windows": 0, "hits": 0, "hit_at": []}
        history = self._replay_history(policy, window)
        series = self._read_replay_series(
            policy,
            target,
            ends[0] - timedelta(minutes=window) - history,
            ends[-1],
            window,
        )
        hits = []
        for end in ends:
            value = self._replay_compared(policy, series, end, window)
            if value is not None and self._matching_threshold(policy, value):
                hits.append(end.isoformat())
        return {"windows": len(ends), "hits": len(hits), "hit_at": hits}

    def _replay_burn(self, policy: ApmPolicy, target: PolicyTarget, evaluated_at: datetime) -> dict:
        short = int(policy.burn_short_window_minutes or 0)
        long = int(policy.burn_long_window_minutes or 0)
        slo = getattr(policy, "slo", None)
        if short < 1 or long < 1 or slo is None:
            return {"windows": 0, "hits": 0, "hit_at": []}
        ends = self._replay_ends(evaluated_at, short)
        if not ends:
            return {"windows": 0, "hits": 0, "hit_at": []}
        source = getattr(slo, "service", None) or target.service
        query = SloMetricQuery(
            service_namespace=source.namespace,
            service_name=source.name,
            environment=slo.environment,
            endpoint=slo.endpoint or "",
            sli_type=slo.sli_type,
            latency_threshold_ms=slo.latency_threshold_ms,
            started_at=ends[0] - timedelta(minutes=long),
            ended_at=ends[-1],
        )
        reader = getattr(self.metric_store, "slo_compliance_by_window", None)
        buckets = {} if reader is None else {end: (total, good) for end, total, good in reader(query, short)}
        hits = []
        for end in ends:
            long_compliance = self._bucket_compliance(buckets, end - timedelta(minutes=long), end, short)
            short_compliance = self._bucket_compliance(buckets, end - timedelta(minutes=short), end, short)
            if long_compliance is None or short_compliance is None:
                continue
            long_burn = self._burn_rate(slo.objective, long_compliance)
            short_burn = self._burn_rate(slo.objective, short_compliance)
            if long_burn is None or short_burn is None:
                continue
            if self._matching_threshold(policy, long_burn) and self._matching_threshold(policy, short_burn):
                hits.append(end.isoformat())
        return {"windows": len(ends), "hits": len(hits), "hit_at": hits}

    @staticmethod
    def _bucket_compliance(buckets: dict, start: datetime, end: datetime, step_minutes: int) -> float | None:
        total = 0.0
        good = 0.0
        found = False
        cursor = end
        step = timedelta(minutes=step_minutes)
        while cursor > start:
            item = buckets.get(cursor)
            if item is not None:
                found = True
                total += item[0]
                good += item[1]
            cursor -= step
        if not found or total <= 0:
            return None
        return good / total * 100

    def dry_run(
        self,
        policy: ApmPolicy,
        *,
        evaluated_at: datetime,
        saved_policy: ApmPolicy | None = None,
        replay_hours: int = 0,
    ) -> dict:
        """只读复用 test_query。不写目标状态、告警、事件、快照或通知。"""
        states = {}
        if saved_policy is not None and getattr(saved_policy, "pk", None):
            states = {
                (
                    str(state.service_id or ""),
                    state.endpoint,
                    state.version,
                    getattr(state, "instance_id", "") or "",
                    dependency_parts(getattr(state, "dependency", None)) or (),
                ): state
                for state in saved_policy.target_states.all()
            }
        items = []
        expanded: list[PolicyTarget] = []
        scope_truncated = False
        for service in scope_services(policy):
            if not service_visible_to_policy(policy, service):
                items.append(self._invisible_item(service))
                continue
            targets, capped, _endpoints, _instances, _dependencies = self._expand_service(policy, service, evaluated_at=evaluated_at)
            scope_truncated = scope_truncated or capped
            expanded.extend(targets)
        for target in expanded[:DRY_RUN_TARGET_LIMIT]:
            result = self.test_query(
                policy,
                evaluated_at=evaluated_at,
                endpoint=target.endpoint,
                version=target.version,
                instance_id=target.instance_id,
                target_service=target.service,
                dependency=target.dependency,
            )
            identity = (
                str(target.service.id),
                target.endpoint,
                target.version,
                target.instance_id,
                dependency_parts(target.dependency) or (),
            )
            state = states.get(identity)
            if state is None:
                state = states.get(("", target.endpoint, target.version, target.instance_id, dependency_parts(target.dependency) or ()))
            verdict = self._dry_run_verdict(result, state)
            history_text = self._hit_history_text(policy, state, result)
            item = {
                "service": target.service.name,
                "instance": target.instance_id,
                "dependency": dependency_label(target.dependency),
                "endpoint": target.endpoint,
                "version": target.version,
                "verdict": verdict,
                "current_value": self._decimal_text(result.current_value),
                "baseline_value": self._decimal_text(result.baseline_value),
                "compared_value": self._decimal_text(result.value),
                "request_count": result.request_count,
                "matched_threshold": dict(result.threshold) if result.threshold and result.breached else None,
                "reason": history_text or self._dry_run_reason(policy, result, state, verdict),
                "hit_history_text": history_text,
                "baseline_days_used": result.baseline_days_used,
            }
            if replay_hours:
                item["replay"] = self._replay_target(policy, target, evaluated_at=evaluated_at)
            if result.condition_rows or result.guard_rows or result.guard_blocked:
                item["conditions"] = [
                    {
                        "ref": row["ref"],
                        "current_value": self._decimal_text(row.get("current_value")),
                        "baseline_value": self._decimal_text(row.get("baseline_value")),
                        "compared_value": self._decimal_text(row.get("compared_value")),
                        "matched_severity": row.get("matched_severity"),
                    }
                    for row in result.condition_rows
                ]
                item["guards"] = [
                    {
                        "ref": row["ref"],
                        "value": self._decimal_text(row.get("value")),
                        "matched": bool(row.get("matched")),
                    }
                    for row in result.guard_rows
                ]
            items.append(item)
        return {
            "evaluated_at": evaluated_at,
            "compare_mode": policy.compare_mode or ApmPolicy.CompareMode.ABSOLUTE,
            "compare_offset_amount": policy.compare_offset_amount,
            "compare_value_kind": policy.compare_value_kind or "",
            "result_unit": resolve_result_unit(policy),
            "slow_threshold_ms": getattr(policy, "slow_threshold_ms", None),
            "apdex_threshold_ms": getattr(policy, "apdex_threshold_ms", None),
            "total_targets": len(expanded),
            "truncated": scope_truncated or len(expanded) > DRY_RUN_TARGET_LIMIT,
            "items": items,
        }

    def _dry_run_verdict(self, result: PolicyQueryResult, state: ApmPolicyTargetState | None) -> str:
        if result.guard_blocked:
            return "guard_not_met"
        if result.data_state == MetricDataState.MISSING_CONDITION_DATA:
            return "missing_condition_data"
        if result.data_state == MetricDataState.HOLD:
            active = state is not None and state.status == ApmPolicyTargetState.Status.ACTIVE
            return "hold" if active else "ok"
        if result.data_state == MetricDataState.NO_DATA:
            return "no_data"
        if result.data_state == MetricDataState.MISSING_BASELINE:
            return "missing_baseline"
        if result.data_state == MetricDataState.INSUFFICIENT_SAMPLES:
            return "insufficient_samples"
        matched = result.threshold if result.breached else None
        active = state is not None and state.status == ApmPolicyTargetState.Status.ACTIVE
        if matched and active and self._severity_rank(matched["severity"]) < self._severity_rank(state.current_severity):
            return "would_escalate"
        if matched and not active:
            return "would_trigger"
        if active and not matched:
            return "would_recover"
        return "ok"

    def _dry_run_reason(self, policy: ApmPolicy, result: PolicyQueryResult, state, verdict: str) -> str:
        if verdict == "guard_not_met":
            return "前置条件未满足"
        if verdict == "missing_condition_data":
            return "条件缺数据"
        if verdict == "hold":
            return "恢复带内"
        if result.data_state == MetricDataState.INSUFFICIENT_SAMPLES:
            return "样本不足"
        if result.data_state == MetricDataState.MISSING_BASELINE:
            if result.reason == BASELINE_ZERO_REASON:
                return "对照值为 0，无法计算变化率"
            if result.reason == BASELINE_DAYS_INSUFFICIENT_REASON:
                return "可用天数不足"
            return "对照缺失"
        if verdict in {"would_trigger", "would_escalate"}:
            if getattr(policy, "trigger_window", None):
                return ""
            needed = policy.trigger_after or 1
            hits = 1 if state is None else state.consecutive_hits + 1
            if needed > 1 and hits < needed:
                return f"本轮命中 {hits}/{needed}，现网不会建告警"
            return ""
        if verdict == "would_recover":
            return f"需连续 {policy.recover_after} 次"
        return ""

    @classmethod
    def _hit_history_text(cls, policy: ApmPolicy, state, result: PolicyQueryResult) -> str:
        window = getattr(policy, "trigger_window", None)
        if not window or not result.breached:
            return ""
        needed = policy.trigger_after or 1
        prior = "" if state is None else (state.hit_history or "")
        counted = (prior + "1")[-int(window) :].count("1")
        if counted >= needed:
            return ""
        if not prior:
            return f"本轮命中 1 / {needed}（{window} 轮内）"
        return f"近 {window} 轮命中 {counted} / {needed}"

    def evaluate(self, policy_id: UUID, *, evaluated_at: datetime, service_id=None) -> None:
        policy = (
            ApmPolicy.objects.select_related("service", "application", "slo", "slo__service").prefetch_related("organization_links").get(id=policy_id)
        )
        if not policy.is_enabled:
            return
        cursor = self._cursor(evaluated_at)
        services = scope_services(policy)
        if service_id is not None:
            services = [item for item in services if str(item.id) == str(service_id)]
        for service in services:
            if not service_visible_to_policy(policy, service):
                continue
            targets, _capped, known_endpoints, known_instances, known_dependencies = self._expand_service(policy, service, evaluated_at=evaluated_at)
            for index, target in enumerate(targets):
                # 基线按天回退在首个目标查询后才把上限收到 20，必须在每个目标前重读。
                if index >= self._target_limit(policy):
                    break
                self._evaluate_target(policy, target, evaluated_at=evaluated_at, cursor=cursor)
            self._close_absent_targets(
                policy,
                service,
                known_endpoints=known_endpoints,
                known_instances=known_instances,
                known_dependencies=known_dependencies,
                evaluated_at=evaluated_at,
                cursor=cursor,
            )

    def _evaluate_target(self, policy, target: PolicyTarget, *, evaluated_at: datetime, cursor: str) -> None:
        target_key = self._target_key(target.service.id, target.endpoint, target.version, target.instance_id, target.dependency)
        state, _ = ApmPolicyTargetState.objects.get_or_create(
            policy=policy,
            target_key=target_key,
            defaults={
                "endpoint": target.endpoint,
                "version": target.version,
                "instance_id": target.instance_id,
                "dependency": dependency_record(target.dependency),
                "service": target.service,
            },
        )
        if state.evaluation_cursor == cursor:
            return
        try:
            result = self.test_query(
                policy,
                evaluated_at=evaluated_at,
                endpoint=target.endpoint,
                version=target.version,
                instance_id=target.instance_id,
                target_service=target.service,
                dependency=target.dependency,
            )
        except Exception:
            ApmPolicyTargetState.objects.filter(policy=policy, target_key=target_key).exclude(evaluation_cursor=cursor).update(
                last_failed_at=timezone.now()
            )
            raise

        with transaction.atomic():
            locked_policy = (
                ApmPolicy.objects.select_related("service", "application", "slo")
                .prefetch_related("organization_links")
                .select_for_update(of=("self",))
                .get(id=policy.id)
            )
            state, _ = ApmPolicyTargetState.objects.select_for_update().get_or_create(
                policy=locked_policy,
                target_key=target_key,
                defaults={
                    "endpoint": target.endpoint,
                    "version": target.version,
                    "instance_id": target.instance_id,
                    "dependency": dependency_record(target.dependency),
                    "service": target.service,
                },
            )
            if not locked_policy.is_enabled or state.evaluation_cursor == cursor or locked_policy.updated_at != policy.updated_at:
                return
            state.service = target.service
            state.instance_id = target.instance_id
            state.dependency = dependency_record(target.dependency)
            state.endpoint = target.endpoint
            state.version = target.version
            state.missed_rounds = 0
            active_alert = ApmAlert.objects.filter(external_id=state.active_alert_id).first() if state.active_alert_id else None
            evaluation_threshold = self._evaluation_threshold(
                locked_policy,
                state,
                result,
            )
            event_snapshot = self._advance_target(locked_policy, state, result, evaluated_at)
            alert = event_snapshot.alert if event_snapshot is not None else active_alert
            if alert is not None:
                ApmAlertMetricSnapshotStore.record(
                    alert=alert,
                    event=event_snapshot.event if event_snapshot is not None else None,
                    policy=locked_policy,
                    result=result,
                    threshold=evaluation_threshold,
                )
            state.evaluation_cursor = cursor
            state.last_succeeded_at = evaluated_at
            state.last_failed_at = None
            state.save()

    def _advance_target(self, policy, state, result, evaluated_at):
        if result.data_state in {
            MetricDataState.MISSING_BASELINE,
            MetricDataState.INSUFFICIENT_SAMPLES,
            MetricDataState.MISSING_CONDITION_DATA,
        }:
            return None
        threshold = dict(result.threshold) if result.threshold else None
        recover_after = policy.recover_after
        if result.data_state == MetricDataState.NO_DATA:
            state.consecutive_hits = 0
            state.consecutive_recoveries = 0
            state.consecutive_no_data += 1
            return None

        state.consecutive_no_data = 0
        if result.data_state == MetricDataState.HOLD:
            self._remember_hit(state, False)
            if state.status == ApmPolicyTargetState.Status.ACTIVE:
                return None
            state.consecutive_recoveries = 0
            state.consecutive_hits = 0
            return None

        hit = threshold is not None
        self._remember_hit(state, hit)
        if state.status == ApmPolicyTargetState.Status.NORMAL:
            state.consecutive_recoveries = 0
            state.consecutive_hits = state.consecutive_hits + 1 if hit else 0
            if hit and self._trigger_ready(policy, state):
                return self._open_alert(policy, state, result, evaluated_at, threshold)
            return None

        if hit:
            state.consecutive_recoveries = 0
            if self._severity_rank(threshold["severity"]) < self._severity_rank(state.current_severity):
                state.consecutive_hits += 1
                if self._trigger_ready(policy, state):
                    state.consecutive_hits = 0
                    state.hit_history = ""
                    state.current_severity = threshold["severity"]
                    return self._record_event(
                        policy,
                        state,
                        result,
                        evaluated_at,
                        state.active_alert_id,
                        ApmEvent.Action.ESCALATED,
                        threshold,
                    )
            else:
                state.consecutive_hits = 0
            return None

        state.consecutive_hits = 0
        state.consecutive_recoveries += 1
        if state.consecutive_recoveries >= recover_after:
            recovery_marker = {
                "severity": state.current_severity,
                "comparator": "recovered",
                "value": "",
            }
            snapshot = self._record_event(
                policy,
                state,
                result,
                evaluated_at,
                state.active_alert_id,
                ApmEvent.Action.RECOVERED,
                recovery_marker,
            )
            state.status = ApmPolicyTargetState.Status.NORMAL
            state.current_severity = ""
            state.active_alert_id = ""
            state.consecutive_recoveries = 0
            state.hit_history = ""
            return snapshot
        return None

    @staticmethod
    def _remember_hit(state, hit: bool) -> None:
        state.hit_history = ((getattr(state, "hit_history", "") or "") + ("1" if hit else "0"))[-20:]

    @staticmethod
    def _trigger_ready(policy, state) -> bool:
        needed = policy.trigger_after or 1
        window = getattr(policy, "trigger_window", None)
        if not window:
            return state.consecutive_hits >= needed
        return (state.hit_history or "")[-int(window) :].count("1") >= needed

    def _open_alert(self, policy, state, result, evaluated_at, threshold):
        state.status = ApmPolicyTargetState.Status.ACTIVE
        state.current_severity = threshold["severity"]
        state.active_alert_id = f"apm-{policy.id}-{uuid4().hex}"
        state.consecutive_hits = 0
        state.hit_history = ""
        return self._record_event(
            policy,
            state,
            result,
            evaluated_at,
            state.active_alert_id,
            ApmEvent.Action.TRIGGERED,
            threshold,
        )

    @staticmethod
    def _severity_rank(severity):
        return {"critical": 0, "error": 1, "warning": 2, "": 99}[severity]

    @staticmethod
    def _record_event(
        policy: ApmPolicy,
        state: ApmPolicyTargetState,
        result: PolicyQueryResult,
        evaluated_at: datetime,
        external_id: str,
        action: str,
        threshold: dict[str, str],
    ):
        event_id = f"{external_id}:{action}:{threshold['severity']}"
        organizations = list(policy.organization_links.order_by("organization").values_list("organization", flat=True).distinct())
        metric_label = policy.get_metric_type_display()
        action_label = {
            ApmEvent.Action.TRIGGERED: "触发",
            ApmEvent.Action.ESCALATED: "级别升级",
            ApmEvent.Action.RECOVERED: "恢复",
            ApmEvent.Action.CLOSED: "人工关闭",
        }[action]
        title = f"APM {policy.name}{action_label}"
        target_service = state.service or policy.service
        shown = result.value if result.value is not None else "无数据"
        description = f"{target_service.namespace}/{target_service.name} [{policy.environment}] {metric_label}={shown}"
        if result.condition_rows:
            parts = []
            for row in result.condition_rows:
                current = DjangoApmPolicyService._decimal_text(row.get("compared_value")) or "无数据"
                line_threshold = row.get("threshold_value") or "—"
                parts.append(f"{row['ref']}: 当前 {current}（阈值 {line_threshold}）")
            description = "；".join(parts)
        elif (policy.compare_mode or ApmPolicy.CompareMode.ABSOLUTE) != ApmPolicy.CompareMode.ABSOLUTE:
            current = result.current_value if result.current_value is not None else "无数据"
            baseline = result.baseline_value if result.baseline_value is not None else "无数据"
            compared = result.value if result.value is not None else "无数据"
            description = (
                f"{target_service.namespace}/{target_service.name} " f"[{policy.environment}] {metric_label} 当前 {current}，对照 {baseline}，变化 {compared}"
            )
        resource_name = f"{target_service.namespace}/{target_service.name}".lstrip("/")
        alert_defaults = {
            "policy": policy,
            "service": target_service,
            "policy_id_snapshot": str(policy.id),
            "policy_name": policy.name,
            "service_namespace": target_service.namespace,
            "service_name": target_service.name,
            "environment": policy.environment,
            "metric_type": policy.metric_type,
            "severity": threshold["severity"],
            "current_value": result.value,
            "organizations": organizations,
            "handlers": list(policy.handlers or []),
            "started_at": evaluated_at,
            "last_event_at": evaluated_at,
            "endpoint": state.endpoint,
            "version": state.version,
            "instance_id": state.instance_id or "",
            "dependency": dependency_record(getattr(state, "dependency", None)),
        }
        alert, created = ApmAlert.objects.get_or_create(external_id=external_id, defaults=alert_defaults)
        alert.policy = policy
        alert.service = target_service
        alert.policy_id_snapshot = str(policy.id)
        alert.policy_name = policy.name
        alert.service_namespace = target_service.namespace
        alert.service_name = target_service.name
        alert.environment = policy.environment
        alert.metric_type = policy.metric_type
        alert.severity = threshold["severity"]
        alert.current_value = result.value
        if created or not alert.organizations:
            alert.organizations = organizations
        alert.last_event_at = evaluated_at
        alert.endpoint = state.endpoint
        alert.version = state.version
        alert.instance_id = state.instance_id or ""
        alert.dependency = dependency_record(getattr(state, "dependency", None))
        if action == ApmEvent.Action.RECOVERED:
            alert.status = ApmAlert.Status.RECOVERED
            alert.ended_at = evaluated_at
        elif action == ApmEvent.Action.CLOSED:
            alert.status = ApmAlert.Status.CLOSED
            alert.ended_at = evaluated_at
        else:
            alert.status = ApmAlert.Status.ACTIVE
            alert.ended_at = None
        alert.save()

        event, _ = ApmEvent.objects.get_or_create(
            event_id=event_id,
            defaults={
                "alert": alert,
                "action": action,
                "title": title,
                "description": description,
                "severity": threshold["severity"],
                "service": target_service.name,
                "item": policy.metric_type,
                "value": result.value,
                "resource_id": str(target_service.id),
                "resource_name": resource_name,
                "policy_id": str(policy.id),
                "environment": policy.environment,
                "organizations": organizations,
                "occurred_at": evaluated_at,
                "ended_at": evaluated_at if action in {ApmEvent.Action.RECOVERED, ApmEvent.Action.CLOSED} else None,
            },
        )
        snapshot = ApmEventSnapshotStore.stage(
            event=event,
            policy=policy,
            result=result,
            endpoint=state.endpoint,
            version=state.version,
            threshold=threshold,
            service=target_service,
            dependency=dependency_label(getattr(state, "dependency", None)),
        )
        payload = {
            "event_key": event_id,
            "external_id": external_id,
            "action": action,
            "severity": threshold["severity"],
            "level": SEVERITY_LEVEL[threshold["severity"]],
            "title": title,
            "description": description,
            "occurred_at": evaluated_at.isoformat(),
            "start_time": str(int(alert.started_at.timestamp())),
            "end_time": str(int(evaluated_at.timestamp())) if action in {"recovered", "closed"} else None,
            "rule_id": str(policy.id),
            "service": target_service.name,
            "item": policy.metric_type,
            "value": float(result.value) if result.value is not None else None,
            "resource_id": str(target_service.id),
            "resource_type": "apm_service",
            "resource_name": resource_name,
            "organizations": organizations,
            "tags": {},
            "labels": {
                "policy_id": str(policy.id),
                "policy_name": policy.name,
                "environment": policy.environment,
                "service_namespace": target_service.namespace,
                "service_name": target_service.name,
                "endpoint": state.endpoint,
                "version": state.version,
                **({"instance": state.instance_id} if state.instance_id else {}),
                "target_kind": getattr(policy, "target_kind", None) or ApmPolicy.TargetKind.ENTRY,
                **({"dependency": dependency_label(state.dependency)} if dependency_label(getattr(state, "dependency", None)) else {}),
                "compare_mode": policy.compare_mode or ApmPolicy.CompareMode.ABSOLUTE,
                "compare_offset_amount": policy.compare_offset_amount,
                "metric_type": policy.metric_type,
            },
        }
        if policy.metric_type == ApmPolicy.MetricType.SLO_BURN_RATE:
            slo = getattr(policy, "slo", None)
            payload["labels"]["slo_name"] = "" if slo is None else slo.name
            payload["labels"]["burn_rate"] = "" if result.value is None else str(result.value)
            payload["labels"]["budget_remaining"] = "" if getattr(result, "budget_remaining", None) is None else str(result.budget_remaining)
        for row in result.condition_rows:
            rendered = DjangoApmPolicyService._decimal_text(row.get("compared_value"))
            if rendered is not None:
                payload["labels"][f"{row['ref']}_value"] = rendered
        for target in policy.notification_targets.order_by("channel_id", "id"):
            recipients = [] if target.recipient_mode == "none" else list(target.recipients)
            ApmAlertOutbox.objects.get_or_create(
                event_key=f"{event_id}:channel:{target.channel_id}",
                defaults={
                    "event": event,
                    "channel_id": target.channel_id,
                    "channel_name": target.channel_name,
                    "channel_type": target.channel_type,
                    "delivery_mode": target.delivery_mode,
                    "receivers": recipients,
                    "recipients": recipients,
                    "title": title,
                    "body": description,
                    "payload": payload,
                },
            )
        return snapshot

    @staticmethod
    def _as_delivery(outbox: ApmAlertOutbox) -> NotificationDelivery:
        if outbox.channel_id is None:
            raise ValueError("APM 通知投递缺少渠道 ID")
        organizations = outbox.payload.get("organizations", [])
        return NotificationDelivery(
            delivery_key=outbox.event_key,
            channel_id=outbox.channel_id,
            organization_ids=tuple(int(value) for value in organizations),
            recipients=tuple(str(receiver) for receiver in outbox.recipients),
            title=outbox.title,
            body=outbox.body,
            event_payload=outbox.payload,
        )

    @staticmethod
    def _claim(outbox_id: UUID, *, now: datetime) -> ApmAlertOutbox | None:
        with transaction.atomic():
            outbox = ApmAlertOutbox.objects.select_for_update().get(id=outbox_id)
            if outbox.delivery_status != ApmAlertOutbox.DeliveryStatus.PENDING:
                return None
            if outbox.next_retry_at is not None and outbox.next_retry_at > now:
                return None
            if outbox.claimed_at is not None and outbox.claimed_at > now - NOTIFICATION_CLAIM_TTL:
                return None
            outbox.claimed_at = now
            outbox.save(update_fields=("claimed_at", "updated_at"))
            return outbox

    def retry_pending_events(self, *, limit: int = 100) -> PublishResult:
        if limit < 1:
            return PublishResult(accepted=0)
        now = timezone.now()
        ids = list(
            ApmAlertOutbox.objects.filter(
                delivery_status=ApmAlertOutbox.DeliveryStatus.PENDING,
            )
            .filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))
            .filter(Q(claimed_at__isnull=True) | Q(claimed_at__lte=now - NOTIFICATION_CLAIM_TTL))
            .order_by("created_at", "id")
            .values_list("id", flat=True)[: min(limit, 1000)]
        )
        accepted = duplicates = failed = 0
        for outbox_id in ids:
            outbox = self._claim(outbox_id, now=now)
            if outbox is None:
                continue
            try:
                result = self.notification_dispatcher.dispatch(self._as_delivery(outbox))
            except Exception:
                result = NotificationDeliveryResult(
                    delivered=False,
                    code="dispatcher_exception",
                    retryable=True,
                    message="通知 dispatcher 执行异常。",
                )
            if result.delivered:
                ApmAlertOutbox.objects.filter(id=outbox_id).update(
                    delivery_status=ApmAlertOutbox.DeliveryStatus.DELIVERED,
                    attempts=outbox.attempts + 1,
                    next_retry_at=None,
                    claimed_at=None,
                    last_error_code="",
                    last_error_message="",
                    delivered_at=timezone.now(),
                    failed_at=None,
                )
                accepted += 1
            else:
                failed += 1
                self._mark_failed(outbox_id, result)
        return PublishResult(accepted=accepted, duplicates=duplicates, failed=failed)

    @staticmethod
    def _mark_failed(outbox_id: UUID, result: NotificationDeliveryResult) -> None:
        with transaction.atomic():
            outbox = ApmAlertOutbox.objects.select_for_update().get(id=outbox_id)
            outbox.attempts += 1
            outbox.claimed_at = None
            outbox.last_error_code = result.code[:128]
            outbox.last_error_message = result.message[:512]
            if not result.retryable or outbox.attempts >= MAX_NOTIFICATION_ATTEMPTS:
                outbox.delivery_status = ApmAlertOutbox.DeliveryStatus.FAILED
                outbox.next_retry_at = None
                outbox.failed_at = timezone.now()
            else:
                delay_seconds = min(300, 2 ** min(outbox.attempts, MAX_NOTIFICATION_ATTEMPTS))
                outbox.next_retry_at = timezone.now() + timedelta(seconds=delay_seconds)
            outbox.save(
                update_fields=(
                    "attempts",
                    "claimed_at",
                    "last_error_code",
                    "last_error_message",
                    "delivery_status",
                    "next_retry_at",
                    "failed_at",
                    "updated_at",
                )
            )
