from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.apm.models import ApmAlert, ApmAlertOutbox, ApmEvent, ApmPolicy, ApmPolicyTargetState, ApmServiceInstance
from apps.apm.services.contracts import (
    MetricDataState,
    MetricStore,
    NotificationDelivery,
    NotificationDeliveryResult,
    NotificationDispatcher,
    PolicyQueryResult,
    PublishResult,
    ServiceMetricQuery,
)
from apps.apm.services.metric_snapshots import ApmAlertMetricSnapshotStore, resolve_result_unit
from apps.apm.services.snapshots import ApmEventSnapshotStore

MAX_POLICY_TARGETS = 100
DRY_RUN_TARGET_LIMIT = 20
BASELINE_ZERO_REASON = "baseline_zero"
_EVALUATION_DELAY_RE = re.compile(r"^\s*(\d+)\s*s?\s*$")
DEFAULT_EVALUATION_DELAY_SECONDS = 60
MAX_EVALUATION_DELAY_SECONDS = 600
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
            if (
                state.status == ApmPolicyTargetState.Status.NORMAL
                and policy.no_data_after
                and policy.no_data_severity
                and state.consecutive_no_data + 1 >= policy.no_data_after
            ):
                return {
                    "severity": policy.no_data_severity,
                    "comparator": "no_data",
                    "value": "",
                }
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

    @classmethod
    def _aggregate(cls, policy: ApmPolicy, red, metric: str | None = None) -> Decimal | None:
        metric = metric or policy.metric_type
        if metric in ApmPolicy.COUNT_METRIC_TYPES:
            return cls._raw_value(policy, red, metric)
        values = [cls._series_value(policy, point, metric) for point in red.timeseries]
        values = [value for value in values if value is not None]
        if not values:
            return cls._raw_value(policy, red, metric)
        if policy.aggregation == ApmPolicy.Aggregation.MAXIMUM:
            return max(values)
        if policy.aggregation == ApmPolicy.Aggregation.MINIMUM:
            return min(values)
        if policy.aggregation == ApmPolicy.Aggregation.LAST:
            return values[-1]
        return sum(values, Decimal(0)) / Decimal(len(values))

    @staticmethod
    def _targets(policy: ApmPolicy) -> list[tuple[str, str]]:
        endpoints = list(policy.endpoints or []) or [""]
        if policy.version_mode == ApmPolicy.VersionMode.SPECIFIC:
            versions = list(policy.versions or [])
        elif policy.version_mode == ApmPolicy.VersionMode.GROUPED:
            versions = list(
                ApmServiceInstance.objects.filter(
                    service=policy.service,
                    environment=policy.environment,
                    archived_at__isnull=True,
                )
                .exclude(version="")
                .order_by("version")
                .values_list("version", flat=True)
                .distinct()[:100]
            )
            if not versions:
                versions = [""]
        else:
            versions = [""]
        return [(endpoint, version) for endpoint in endpoints for version in versions][:MAX_POLICY_TARGETS]

    @staticmethod
    def _target_key(endpoint: str, version: str) -> str:
        return sha256(f"endpoint={endpoint}\x00version={version}".encode()).hexdigest()

    def _read_window(
        self,
        policy: ApmPolicy,
        *,
        started_at: datetime,
        ended_at: datetime,
        endpoint: str,
        version: str,
        include_endpoints: bool,
    ):
        return self.metric_store.service_red(
            ServiceMetricQuery(
                service_namespace=policy.service.namespace,
                service_name=policy.service.name,
                environment=policy.environment,
                started_at=started_at,
                ended_at=ended_at,
                include_breakdown=True,
                include_endpoints=include_endpoints,
                endpoint=endpoint or "",
                version=version or "",
                slow_threshold_ms=getattr(policy, "slow_threshold_ms", None) or None,
                apdex_threshold_ms=getattr(policy, "apdex_threshold_ms", None) or None,
            )
        )

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
        guards=(),
        guard_blocked: bool = False,
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
            guards=tuple(guards),
            guard_blocked=guard_blocked,
        )

    def test_query(
        self,
        policy: ApmPolicy,
        *,
        evaluated_at: datetime,
        endpoint: str | None = None,
        version: str | None = None,
    ) -> PolicyQueryResult:
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
        )
        current_value = self._aggregate(policy, current)
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
        offset = self._baseline_offset(policy, window)
        if offset is None:
            threshold = self._matching_threshold(policy, current_value)
            decision = self._decision(policy, current, current_value, threshold)
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
                guards=decision["guards"],
                guard_blocked=decision["guard_blocked"],
            )
        baseline = self._read_window(
            policy,
            started_at=current_start - offset,
            ended_at=window_end - offset,
            endpoint=target_endpoint or "",
            version=target_version or "",
            include_endpoints=False,
        )
        baseline_value = self._aggregate(policy, baseline)
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
        decision = self._decision(policy, current, compared, threshold)
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
            guards=decision["guards"],
            guard_blocked=decision["guard_blocked"],
        )

    def _decision(self, policy: ApmPolicy, red, value: Decimal, threshold):
        """前置不满足按未越线；有恢复线且落在两线之间记 hold。越线优先于恢复线。"""
        guards = self._guard_rows(policy, red)
        blocked = any(not item["matched"] for item in guards)
        if blocked:
            return {
                "breached": False,
                "data_state": MetricDataState.AVAILABLE,
                "threshold": None,
                "guards": guards,
                "guard_blocked": True,
            }
        if threshold is not None:
            return {
                "breached": True,
                "data_state": MetricDataState.AVAILABLE,
                "threshold": threshold,
                "guards": guards,
                "guard_blocked": False,
            }
        recovery = getattr(policy, "recovery_threshold", None) or {}
        if recovery and value is not None and not self._breached(str(recovery["comparator"]), Decimal(str(recovery["value"])), value):
            return {
                "breached": False,
                "data_state": MetricDataState.HOLD,
                "threshold": None,
                "guards": guards,
                "guard_blocked": False,
            }
        return {
            "breached": False,
            "data_state": MetricDataState.AVAILABLE,
            "threshold": None,
            "guards": guards,
            "guard_blocked": False,
        }

    def _guard_rows(self, policy: ApmPolicy, red) -> tuple[dict, ...]:
        rows = []
        for guard in list(getattr(policy, "guard_conditions", None) or []):
            metric = str(guard.get("metric_type") or "")
            value = self._aggregate(policy, red, metric)
            matched = value is not None and self._breached(str(guard.get("comparator")), Decimal(str(guard.get("value"))), value)
            rows.append(
                {
                    "metric_type": metric,
                    "value": self._decimal_text(value),
                    "matched": matched,
                }
            )
        return tuple(rows)

    def dry_run(
        self,
        policy: ApmPolicy,
        *,
        evaluated_at: datetime,
        saved_policy: ApmPolicy | None = None,
    ) -> dict:
        """只读复用 test_query。不写目标状态、告警、事件、快照或通知。"""
        targets = self._targets(policy)
        states = {}
        if saved_policy is not None and getattr(saved_policy, "pk", None):
            states = {(state.endpoint, state.version): state for state in saved_policy.target_states.all()}
        items = []
        for endpoint, version in targets[:DRY_RUN_TARGET_LIMIT]:
            result = self.test_query(policy, evaluated_at=evaluated_at, endpoint=endpoint, version=version)
            state = states.get((endpoint, version))
            verdict = self._dry_run_verdict(result, state)
            history_text = self._hit_history_text(policy, state, result)
            items.append(
                {
                    "endpoint": endpoint,
                    "version": version,
                    "verdict": verdict,
                    "current_value": self._decimal_text(result.current_value),
                    "baseline_value": self._decimal_text(result.baseline_value),
                    "compared_value": self._decimal_text(result.value),
                    "request_count": result.request_count,
                    "matched_threshold": dict(result.threshold) if result.threshold and result.breached else None,
                    "reason": history_text or self._dry_run_reason(policy, result, state, verdict),
                    "guards": [dict(item) for item in result.guards],
                    "hit_history_text": history_text,
                }
            )
        return {
            "evaluated_at": evaluated_at,
            "compare_mode": policy.compare_mode or ApmPolicy.CompareMode.ABSOLUTE,
            "compare_offset_amount": policy.compare_offset_amount,
            "compare_value_kind": policy.compare_value_kind or "",
            "result_unit": resolve_result_unit(policy),
            "slow_threshold_ms": getattr(policy, "slow_threshold_ms", None),
            "apdex_threshold_ms": getattr(policy, "apdex_threshold_ms", None),
            "total_targets": len(targets),
            "truncated": len(targets) > DRY_RUN_TARGET_LIMIT,
            "items": items,
        }

    def _dry_run_verdict(self, result: PolicyQueryResult, state: ApmPolicyTargetState | None) -> str:
        if result.guard_blocked:
            return "guard_not_met"
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
        if result.guard_blocked:
            return "前置条件不满足"
        if verdict == "hold":
            return "恢复带内"
        if result.data_state == MetricDataState.INSUFFICIENT_SAMPLES:
            return "样本不足"
        if result.data_state == MetricDataState.MISSING_BASELINE:
            if result.reason == BASELINE_ZERO_REASON:
                return "对照值为 0，无法计算变化率"
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

    def evaluate(self, policy_id: UUID, *, evaluated_at: datetime) -> None:
        policy = ApmPolicy.objects.select_related("service").prefetch_related("organization_links").get(id=policy_id)
        if not policy.is_enabled:
            return
        cursor = self._cursor(evaluated_at)
        for endpoint, version in self._targets(policy):
            target_key = self._target_key(endpoint, version)
            state, _ = ApmPolicyTargetState.objects.get_or_create(
                policy=policy,
                target_key=target_key,
                defaults={"endpoint": endpoint, "version": version},
            )
            if state.evaluation_cursor == cursor:
                continue
            try:
                result = self.test_query(policy, evaluated_at=evaluated_at, endpoint=endpoint, version=version)
            except Exception:
                ApmPolicyTargetState.objects.filter(policy=policy, target_key=target_key).exclude(evaluation_cursor=cursor).update(
                    last_failed_at=timezone.now()
                )
                raise

            with transaction.atomic():
                locked_policy = (
                    ApmPolicy.objects.select_related("service").prefetch_related("organization_links").select_for_update().get(id=policy_id)
                )
                state, _ = ApmPolicyTargetState.objects.select_for_update().get_or_create(
                    policy=locked_policy,
                    target_key=target_key,
                    defaults={"endpoint": endpoint, "version": version},
                )
                if not locked_policy.is_enabled or state.evaluation_cursor == cursor or locked_policy.updated_at != policy.updated_at:
                    continue
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
        if result.data_state in {MetricDataState.MISSING_BASELINE, MetricDataState.INSUFFICIENT_SAMPLES}:
            return None
        threshold = dict(result.threshold) if result.threshold else None
        recover_after = policy.recover_after
        if result.data_state == MetricDataState.NO_DATA:
            state.consecutive_hits = 0
            state.consecutive_recoveries = 0
            state.consecutive_no_data += 1
            if (
                state.status == ApmPolicyTargetState.Status.NORMAL
                and policy.no_data_after
                and policy.no_data_severity
                and state.consecutive_no_data >= policy.no_data_after
            ):
                threshold = {"severity": policy.no_data_severity, "comparator": "no_data", "value": ""}
                return self._open_alert(policy, state, result, evaluated_at, threshold)
            return None

        state.consecutive_no_data = 0
        if result.data_state == MetricDataState.HOLD:
            self._remember_hit(state, False)
            if state.status == ApmPolicyTargetState.Status.ACTIVE:
                return None
            state.consecutive_recoveries = 0
            state.consecutive_hits = 0
            return None

        hit = threshold is not None and not result.guard_blocked
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
        shown = result.value if result.value is not None else "无数据"
        description = f"{policy.service.namespace}/{policy.service.name} [{policy.environment}] {metric_label}={shown}"
        if (policy.compare_mode or ApmPolicy.CompareMode.ABSOLUTE) != ApmPolicy.CompareMode.ABSOLUTE:
            current = result.current_value if result.current_value is not None else "无数据"
            baseline = result.baseline_value if result.baseline_value is not None else "无数据"
            compared = result.value if result.value is not None else "无数据"
            description = (
                f"{policy.service.namespace}/{policy.service.name} " f"[{policy.environment}] {metric_label} 当前 {current}，对照 {baseline}，变化 {compared}"
            )
        guards = list(getattr(policy, "guard_conditions", None) or [])
        if guards:
            parts = []
            for guard in guards:
                metric = ApmPolicy.MetricType(str(guard["metric_type"])).label
                comparator = ApmPolicy.Comparator(str(guard["comparator"])).label
                parts.append(f"{metric} {comparator} {guard['value']}")
            description = f"{description}；前置条件 {'，'.join(parts)}"
        resource_name = f"{policy.service.namespace}/{policy.service.name}".lstrip("/")
        alert_defaults = {
            "policy": policy,
            "service": policy.service,
            "policy_id_snapshot": str(policy.id),
            "policy_name": policy.name,
            "service_namespace": policy.service.namespace,
            "service_name": policy.service.name,
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
        }
        alert, created = ApmAlert.objects.get_or_create(external_id=external_id, defaults=alert_defaults)
        alert.policy = policy
        alert.service = policy.service
        alert.policy_id_snapshot = str(policy.id)
        alert.policy_name = policy.name
        alert.service_namespace = policy.service.namespace
        alert.service_name = policy.service.name
        alert.environment = policy.environment
        alert.metric_type = policy.metric_type
        alert.severity = threshold["severity"]
        alert.current_value = result.value
        if created or not alert.organizations:
            alert.organizations = organizations
        alert.last_event_at = evaluated_at
        alert.endpoint = state.endpoint
        alert.version = state.version
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
                "service": policy.service.name,
                "item": policy.metric_type,
                "value": result.value,
                "resource_id": str(policy.service.id),
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
            "service": policy.service.name,
            "item": policy.metric_type,
            "value": float(result.value) if result.value is not None else None,
            "resource_id": str(policy.service.id),
            "resource_type": "apm_service",
            "resource_name": resource_name,
            "organizations": organizations,
            "tags": {},
            "labels": {
                "policy_id": str(policy.id),
                "policy_name": policy.name,
                "environment": policy.environment,
                "service_namespace": policy.service.namespace,
                "service_name": policy.service.name,
                "endpoint": state.endpoint,
                "version": state.version,
                "compare_mode": policy.compare_mode or ApmPolicy.CompareMode.ABSOLUTE,
                "compare_offset_amount": policy.compare_offset_amount,
                "metric_type": policy.metric_type,
            },
        }
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
