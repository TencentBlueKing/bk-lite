from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.apm.models import ApmAlert, ApmAlertOutbox, ApmEvent, ApmPolicy, ApmPolicyState
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


SEVERITY_LEVEL = {
    ApmPolicy.Severity.CRITICAL: "0",
    ApmPolicy.Severity.ERROR: "1",
    ApmPolicy.Severity.WARNING: "2",
}
MAX_NOTIFICATION_ATTEMPTS = 8
NOTIFICATION_CLAIM_TTL = timedelta(minutes=5)


class DjangoApmPolicyService:
    """封装 APM 策略查询、连续窗口状态机和 outbox 补偿。"""

    def __init__(self, metric_store: MetricStore, notification_dispatcher: NotificationDispatcher):
        self.metric_store = metric_store
        self.notification_dispatcher = notification_dispatcher

    def save_policy(self, policy: ApmPolicy) -> ApmPolicy:
        ApmPolicyState.objects.get_or_create(policy=policy)
        return policy

    @staticmethod
    def _cursor(evaluated_at: datetime) -> str:
        return evaluated_at.replace(second=0, microsecond=0).isoformat()

    @staticmethod
    def _value(policy: ApmPolicy, red) -> Decimal | None:
        values = {
            ApmPolicy.MetricType.ERROR_RATE: red.error_rate,
            ApmPolicy.MetricType.P95: red.p95_ms,
            ApmPolicy.MetricType.P99: red.p99_ms,
            ApmPolicy.MetricType.THROUGHPUT: red.request_rate,
            ApmPolicy.MetricType.NO_TRAFFIC: red.request_rate,
        }
        value = values[policy.metric_type]
        if policy.metric_type == ApmPolicy.MetricType.NO_TRAFFIC and value is None:
            value = 0
        return Decimal(str(value)) if value is not None else None

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
        if value is None:
            return PolicyQueryResult(
                value=None,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.NO_DATA,
            )
        return PolicyQueryResult(
            value=value,
            breached=self._breached(policy, value),
            evaluated_at=evaluated_at,
            data_state=MetricDataState.AVAILABLE,
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
            if result.data_state == MetricDataState.NO_DATA:
                state.save()
                return
            if state.status == ApmPolicyState.Status.NORMAL:
                state.consecutive_recoveries = 0
                state.consecutive_hits = state.consecutive_hits + 1 if result.breached else 0
                if result.breached and state.consecutive_hits >= locked_policy.duration_window:
                    external_id = f"apm-{locked_policy.id}-{uuid4().hex}"
                    state.status = ApmPolicyState.Status.FIRING
                    state.external_alert_id = external_id
                    self._record_event(locked_policy, result.value, evaluated_at, external_id, "created")
            else:
                state.consecutive_hits = 0
                state.consecutive_recoveries = state.consecutive_recoveries + 1 if not result.breached else 0
                if not result.breached and state.consecutive_recoveries >= locked_policy.recovery_window:
                    external_id = state.external_alert_id
                    self._record_event(locked_policy, result.value, evaluated_at, external_id, "recovery")
                    state.status = ApmPolicyState.Status.NORMAL
                    state.external_alert_id = ""
                    state.consecutive_recoveries = 0
            state.save()

    @staticmethod
    def _record_event(
        policy: ApmPolicy,
        value: Decimal,
        evaluated_at: datetime,
        external_id: str,
        action: str,
    ) -> ApmEvent:
        event_id = f"{external_id}:{action}"
        organizations = list(
            policy.service.organization_links.order_by("organization")
            .values_list("organization", flat=True)
            .distinct()
        )
        metric_label = policy.get_metric_type_display()
        title = f"APM {policy.name}{'触发' if action == 'created' else '恢复'}"
        description = (
            f"{policy.service.namespace}/{policy.service.name} "
            f"[{policy.environment}] {metric_label}={value}"
        )
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
            "severity": policy.severity,
            "current_value": value,
            "organizations": organizations,
            "started_at": evaluated_at,
            "last_event_at": evaluated_at,
        }
        alert, _ = ApmAlert.objects.get_or_create(external_id=external_id, defaults=alert_defaults)
        alert.policy = policy
        alert.service = policy.service
        alert.policy_id_snapshot = str(policy.id)
        alert.policy_name = policy.name
        alert.service_namespace = policy.service.namespace
        alert.service_name = policy.service.name
        alert.environment = policy.environment
        alert.metric_type = policy.metric_type
        alert.severity = policy.severity
        alert.current_value = value
        alert.organizations = organizations
        alert.last_event_at = evaluated_at
        if action == ApmEvent.Action.RECOVERY:
            alert.status = ApmAlert.Status.RECOVERED
            alert.ended_at = evaluated_at
        else:
            alert.status = ApmAlert.Status.FIRING
            alert.ended_at = None
        alert.save()

        event, _ = ApmEvent.objects.get_or_create(
            event_id=event_id,
            defaults={
                "alert": alert,
                "action": action,
                "title": title,
                "description": description,
                "severity": policy.severity,
                "service": policy.service.name,
                "item": policy.metric_type,
                "value": value,
                "resource_id": str(policy.service.id),
                "resource_name": resource_name,
                "policy_id": str(policy.id),
                "environment": policy.environment,
                "organizations": organizations,
                "occurred_at": evaluated_at,
                "ended_at": evaluated_at if action == ApmEvent.Action.RECOVERY else None,
            },
        )
        payload = {
            "event_key": event_id,
            "external_id": external_id,
            "action": action,
            "severity": policy.severity,
            "level": SEVERITY_LEVEL[policy.severity],
            "title": title,
            "description": description,
            "occurred_at": evaluated_at.isoformat(),
            "start_time": str(int(alert.started_at.timestamp())),
            "end_time": str(int(evaluated_at.timestamp())) if action == "recovery" else None,
            "rule_id": str(policy.id),
            "service": policy.service.name,
            "item": policy.metric_type,
            "value": float(value),
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
            },
        }
        if policy.notice:
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
        return event

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
