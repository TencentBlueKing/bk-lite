from __future__ import annotations

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
from apps.apm.services.metric_snapshots import ApmAlertMetricSnapshotStore
from apps.apm.services.snapshots import ApmEventSnapshotStore

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
        return policy

    @staticmethod
    def _cursor(evaluated_at: datetime) -> str:
        return evaluated_at.replace(second=0, microsecond=0).isoformat()

    @staticmethod
    def _raw_value(policy: ApmPolicy, red) -> Decimal | None:
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

    @staticmethod
    def _series_value(policy: ApmPolicy, point) -> Decimal | None:
        value = {
            ApmPolicy.MetricType.ERROR_RATE: point.error_rate,
            ApmPolicy.MetricType.P95: point.p95_ms,
            ApmPolicy.MetricType.P99: point.p99_ms,
            ApmPolicy.MetricType.THROUGHPUT: point.request_rate,
            ApmPolicy.MetricType.NO_TRAFFIC: point.request_rate,
        }[policy.metric_type]
        return Decimal(str(value)) if value is not None else None

    @classmethod
    def _aggregate(cls, policy: ApmPolicy, red) -> Decimal | None:
        values = [cls._series_value(policy, point) for point in red.timeseries]
        values = [value for value in values if value is not None]
        if not values:
            return cls._raw_value(policy, red)
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
        return [(endpoint, version) for endpoint in endpoints for version in versions]

    @staticmethod
    def _target_key(endpoint: str, version: str) -> str:
        return sha256(f"endpoint={endpoint}\x00version={version}".encode()).hexdigest()

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
        red = self.metric_store.service_red(
            ServiceMetricQuery(
                service_namespace=policy.service.namespace,
                service_name=policy.service.name,
                environment=policy.environment,
                started_at=evaluated_at - timedelta(minutes=window),
                ended_at=evaluated_at,
                include_breakdown=True,
                endpoint=target_endpoint or "",
                version=target_version or "",
            )
        )
        value = self._aggregate(policy, red)
        if value is None:
            return PolicyQueryResult(
                value=None,
                breached=None,
                evaluated_at=evaluated_at,
                data_state=MetricDataState.NO_DATA,
                series=red.timeseries,
            )
        threshold = self._matching_threshold(policy, value)
        return PolicyQueryResult(
            value=value,
            breached=threshold is not None,
            evaluated_at=evaluated_at,
            data_state=MetricDataState.AVAILABLE,
            series=red.timeseries,
            threshold=threshold,
        )

    def evaluate(self, policy_id: UUID, *, evaluated_at: datetime) -> None:
        policy = ApmPolicy.objects.select_related("service").get(id=policy_id)
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
                locked_policy = ApmPolicy.objects.select_related("service").select_for_update().get(id=policy_id)
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
        threshold = dict(result.threshold) if result.threshold else None
        trigger_after = policy.trigger_after
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
        if state.status == ApmPolicyTargetState.Status.NORMAL:
            state.consecutive_recoveries = 0
            state.consecutive_hits = state.consecutive_hits + 1 if threshold else 0
            if threshold and state.consecutive_hits >= trigger_after:
                return self._open_alert(policy, state, result, evaluated_at, threshold)
            return None

        if threshold:
            state.consecutive_recoveries = 0
            if self._severity_rank(threshold["severity"]) < self._severity_rank(state.current_severity):
                state.consecutive_hits += 1
                if state.consecutive_hits >= trigger_after:
                    state.consecutive_hits = 0
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
            recovery_threshold = {
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
                recovery_threshold,
            )
            state.status = ApmPolicyTargetState.Status.NORMAL
            state.current_severity = ""
            state.active_alert_id = ""
            state.consecutive_recoveries = 0
            return snapshot
        return None

    def _open_alert(self, policy, state, result, evaluated_at, threshold):
        state.status = ApmPolicyTargetState.Status.ACTIVE
        state.current_severity = threshold["severity"]
        state.active_alert_id = f"apm-{policy.id}-{uuid4().hex}"
        state.consecutive_hits = 0
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
        organizations = list(policy.service.organization_links.order_by("organization").values_list("organization", flat=True).distinct())
        metric_label = policy.get_metric_type_display()
        action_label = {
            ApmEvent.Action.TRIGGERED: "触发",
            ApmEvent.Action.ESCALATED: "级别升级",
            ApmEvent.Action.RECOVERED: "恢复",
            ApmEvent.Action.CLOSED: "人工关闭",
        }[action]
        title = f"APM {policy.name}{action_label}"
        description = (
            f"{policy.service.namespace}/{policy.service.name} "
            f"[{policy.environment}] {metric_label}={result.value if result.value is not None else '无数据'}"
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
            "severity": threshold["severity"],
            "current_value": result.value,
            "organizations": organizations,
            "started_at": evaluated_at,
            "last_event_at": evaluated_at,
            "endpoint": state.endpoint,
            "version": state.version,
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
        alert.severity = threshold["severity"]
        alert.current_value = result.value
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
