from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.apm.models import ApmAlertOutbox, ApmPolicy, ApmPolicyState
from apps.apm.services.contracts import (
    AlertPublisher,
    ApmAlertEvent,
    MetricStore,
    PolicyQueryResult,
    PublishResult,
    ServiceMetricQuery,
)


SEVERITY_LEVEL = {
    ApmPolicy.Severity.CRITICAL: "0",
    ApmPolicy.Severity.ERROR: "1",
    ApmPolicy.Severity.WARNING: "2",
}


class DjangoApmPolicyService:
    """封装 APM 策略查询、连续窗口状态机和 outbox 补偿。"""

    def __init__(self, metric_store: MetricStore, alert_publisher: AlertPublisher):
        self.metric_store = metric_store
        self.alert_publisher = alert_publisher

    def save_policy(self, policy: ApmPolicy) -> ApmPolicy:
        ApmPolicyState.objects.get_or_create(policy=policy)
        return policy

    @staticmethod
    def _cursor(evaluated_at: datetime) -> str:
        return evaluated_at.replace(second=0, microsecond=0).isoformat()

    @staticmethod
    def _value(policy: ApmPolicy, red) -> Decimal:
        values = {
            ApmPolicy.MetricType.ERROR_RATE: red.error_rate,
            ApmPolicy.MetricType.P95: red.p95_ms,
            ApmPolicy.MetricType.P99: red.p99_ms,
            ApmPolicy.MetricType.THROUGHPUT: red.request_rate,
            ApmPolicy.MetricType.NO_TRAFFIC: red.request_rate,
        }
        return Decimal(str(values[policy.metric_type]))

    @staticmethod
    def _breached(policy: ApmPolicy, value: Decimal) -> bool:
        comparators = {
            ApmPolicy.Comparator.GREATER_THAN: value > policy.threshold,
            ApmPolicy.Comparator.GREATER_THAN_OR_EQUAL: value >= policy.threshold,
            ApmPolicy.Comparator.LESS_THAN: value < policy.threshold,
            ApmPolicy.Comparator.LESS_THAN_OR_EQUAL: value <= policy.threshold,
        }
        return comparators[policy.comparator]

    def test_query(self, policy: ApmPolicy, *, evaluated_at: datetime) -> PolicyQueryResult:
        window = max(policy.duration_window, 1)
        red = self.metric_store.service_red(
            ServiceMetricQuery(
                service_namespace=policy.service.namespace,
                service_name=policy.service.name,
                environment=policy.environment,
                started_at=evaluated_at - timedelta(minutes=window),
                ended_at=evaluated_at,
            )
        )
        value = self._value(policy, red)
        return PolicyQueryResult(
            value=value,
            breached=self._breached(policy, value),
            evaluated_at=evaluated_at,
        )

    def evaluate(self, policy_id: UUID, *, evaluated_at: datetime) -> None:
        policy = ApmPolicy.objects.select_related("service").get(id=policy_id)
        if not policy.is_enabled:
            return
        state, _ = ApmPolicyState.objects.get_or_create(policy=policy)
        cursor = self._cursor(evaluated_at)
        if state.evaluation_cursor == cursor:
            return

        try:
            result = self.test_query(policy, evaluated_at=evaluated_at)
        except Exception:
            ApmPolicyState.objects.filter(policy=policy).exclude(evaluation_cursor=cursor).update(
                last_failed_at=timezone.now()
            )
            raise

        with transaction.atomic():
            locked_policy = ApmPolicy.objects.select_related("service").select_for_update().get(id=policy_id)
            state, _ = ApmPolicyState.objects.select_for_update().get_or_create(policy=locked_policy)
            if (
                not locked_policy.is_enabled
                or state.evaluation_cursor == cursor
                or locked_policy.updated_at != policy.updated_at
            ):
                return

            state.evaluation_cursor = cursor
            state.last_succeeded_at = evaluated_at
            state.last_failed_at = None
            if state.status == ApmPolicyState.Status.NORMAL:
                state.consecutive_recoveries = 0
                state.consecutive_hits = state.consecutive_hits + 1 if result.breached else 0
                if result.breached and state.consecutive_hits >= locked_policy.duration_window:
                    external_id = f"apm-{locked_policy.id}-{uuid4().hex}"
                    state.status = ApmPolicyState.Status.FIRING
                    state.external_alert_id = external_id
                    self._enqueue(locked_policy, result.value, evaluated_at, external_id, "created")
            else:
                state.consecutive_hits = 0
                state.consecutive_recoveries = state.consecutive_recoveries + 1 if not result.breached else 0
                if not result.breached and state.consecutive_recoveries >= locked_policy.recovery_window:
                    external_id = state.external_alert_id
                    self._enqueue(locked_policy, result.value, evaluated_at, external_id, "recovery")
                    state.status = ApmPolicyState.Status.NORMAL
                    state.external_alert_id = ""
                    state.consecutive_recoveries = 0
            state.save()

    @staticmethod
    def _enqueue(
        policy: ApmPolicy,
        value: Decimal,
        evaluated_at: datetime,
        external_id: str,
        action: str,
    ) -> None:
        event_key = f"{external_id}:{action}"
        organizations = list(
            policy.service.organization_links.order_by("organization")
            .values_list("organization", flat=True)
            .distinct()
        )
        metric_label = policy.get_metric_type_display()
        payload = {
            "event_key": event_key,
            "external_id": external_id,
            "action": action,
            "severity": policy.severity,
            "level": SEVERITY_LEVEL[policy.severity],
            "title": f"APM {policy.name}{'触发' if action == 'created' else '恢复'}",
            "description": (
                f"{policy.service.namespace}/{policy.service.name} "
                f"[{policy.environment}] {metric_label}={value}"
            ),
            "occurred_at": evaluated_at.isoformat(),
            "start_time": str(int(evaluated_at.timestamp())),
            "end_time": str(int(evaluated_at.timestamp())) if action == "recovery" else None,
            "rule_id": str(policy.id),
            "service": policy.service.name,
            "item": policy.metric_type,
            "value": float(value),
            "resource_id": str(policy.service.id),
            "resource_type": "apm_service",
            "resource_name": f"{policy.service.namespace}/{policy.service.name}".lstrip("/"),
            "organizations": organizations,
            "tags": {},
            "labels": {
                "policy_id": str(policy.id),
                "policy_name": policy.name,
                "environment": policy.environment,
                "service_namespace": policy.service.namespace,
                "service_name": policy.service.name,
            },
        }
        ApmAlertOutbox.objects.get_or_create(
            event_key=event_key,
            defaults={"payload": payload},
        )

    @staticmethod
    def _as_event(outbox: ApmAlertOutbox) -> ApmAlertEvent:
        payload = outbox.payload
        return ApmAlertEvent(
            event_key=outbox.event_key,
            external_id=payload["external_id"],
            status=payload["action"],
            severity=payload["severity"],
            title=payload["title"],
            occurred_at=datetime.fromisoformat(payload["occurred_at"]),
            payload=payload,
        )

    def retry_pending_events(self, *, limit: int = 100) -> PublishResult:
        if limit < 1:
            return PublishResult(accepted=0)
        now = timezone.now()
        ids = list(
            ApmAlertOutbox.objects.filter(
                delivery_status=ApmAlertOutbox.DeliveryStatus.PENDING,
            )
            .filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))
            .order_by("created_at", "id")
            .values_list("id", flat=True)[: min(limit, 1000)]
        )
        accepted = duplicates = failed = 0
        for outbox_id in ids:
            outbox = ApmAlertOutbox.objects.get(id=outbox_id)
            try:
                result = self.alert_publisher.publish([self._as_event(outbox)])
            except Exception:
                failed += 1
                self._mark_failed(outbox_id)
                continue
            if result.accepted + result.duplicates == 1 and result.failed == 0:
                ApmAlertOutbox.objects.filter(id=outbox_id).update(
                    delivery_status=ApmAlertOutbox.DeliveryStatus.DELIVERED,
                    attempts=outbox.attempts + 1,
                    next_retry_at=None,
                )
                accepted += result.accepted
                duplicates += result.duplicates
            else:
                failed += 1
                self._mark_failed(outbox_id)
        return PublishResult(accepted=accepted, duplicates=duplicates, failed=failed)

    @staticmethod
    def _mark_failed(outbox_id: UUID) -> None:
        with transaction.atomic():
            outbox = ApmAlertOutbox.objects.select_for_update().get(id=outbox_id)
            outbox.attempts += 1
            delay_seconds = min(300, 2 ** min(outbox.attempts, 8))
            outbox.next_retry_at = timezone.now() + timedelta(seconds=delay_seconds)
            outbox.save(update_fields=("attempts", "next_retry_at", "updated_at"))
