from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.db.models.functions import TruncHour
from django.utils import timezone

from apps.apm.models import (
    ApmAlert,
    ApmAlertOutbox,
    ApmEvent,
    ApmEventSnapshot,
    ApmPolicy,
    ApmPolicyNotificationTarget,
    ApmPolicyTargetState,
)
from apps.apm.services.contracts import MetricDataState, PolicyQueryResult
from apps.apm.services.policies import DjangoApmPolicyService
from apps.apm.utils.user_display import build_user_display_map, format_user_identifiers
from apps.core.logger import apm_logger as logger
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.system_mgmt.models import User


class AlertHandlerConflict(Exception):
    """已有处理人或告警非活跃。"""


class AlertHandlerInvalid(Exception):
    """分派名单校验失败。"""


class AlertHandlerForbidden(Exception):
    """看不见或无操作权限。"""


class DjangoApmAlertService:
    @staticmethod
    def queryset(*, organization_id: int | None = None, organization_ids: Sequence[int] | None = None) -> QuerySet[ApmAlert]:
        queryset = ApmAlert.objects.select_related("policy", "service").prefetch_related(
            "events",
            "events__outbox_entries",
            "snapshots",
        )
        ids = list(organization_ids) if organization_ids is not None else [organization_id]
        return queryset.filter(build_json_membership_query(queryset, "organizations", ids))

    def list(
        self,
        *,
        organization_id: int | None = None,
        organization_ids: Sequence[int] | None = None,
        started_at: datetime,
        ended_at: datetime,
        status: str | None = None,
        status_group: str | None = None,
        severity: str | None = None,
        metric_type: str | None = None,
        service_id=None,
        keyword: str = "",
        limit: int = 50,
        my_alert: bool = False,
        actor=None,
    ) -> list[dict]:
        queryset = self.queryset(organization_id=organization_id, organization_ids=organization_ids).filter(
            last_event_at__gte=started_at,
            last_event_at__lte=ended_at,
        )
        if my_alert:
            queryset = self.filter_my_handler_alerts(queryset, actor)
        if status:
            queryset = queryset.filter(status=status)
        if status_group == "active":
            queryset = queryset.filter(status=ApmAlert.Status.ACTIVE)
        elif status_group == "history":
            queryset = queryset.filter(
                status__in=(ApmAlert.Status.RECOVERED, ApmAlert.Status.CLOSED)
            )
        if severity:
            queryset = queryset.filter(severity=severity)
        if metric_type:
            queryset = queryset.filter(metric_type=metric_type)
        if service_id:
            queryset = queryset.filter(service_id=service_id)
        if keyword:
            queryset = queryset.filter(
                Q(policy_name__icontains=keyword)
                | Q(service_name__icontains=keyword)
                | Q(service_namespace__icontains=keyword)
                | Q(endpoint__icontains=keyword)
                | Q(environment__icontains=keyword)
            )
        alerts = list(queryset.order_by("-last_event_at", "-id")[:limit])
        user_map = build_user_display_map([item for alert in alerts for item in (alert.handlers or [])])
        return [self.serialize(alert, user_map=user_map) for alert in alerts]

    def distribution(
        self,
        *,
        organization_id: int | None = None,
        organization_ids: Sequence[int] | None = None,
        started_at: datetime,
        ended_at: datetime,
        status_group: str | None = None,
        my_alert: bool = False,
        actor=None,
    ) -> list[dict]:
        event_queryset = ApmEvent.objects.exclude(
            action__in=(ApmEvent.Action.CLAIMED, ApmEvent.Action.ASSIGNED)
        )
        if status_group == "active":
            event_queryset = event_queryset.filter(alert__status=ApmAlert.Status.ACTIVE)
        elif status_group == "history":
            event_queryset = event_queryset.filter(
                alert__status__in=(ApmAlert.Status.RECOVERED, ApmAlert.Status.CLOSED)
            )
        if my_alert:
            mine = self.filter_my_handler_alerts(
                self.queryset(organization_id=organization_id, organization_ids=organization_ids),
                actor,
            )
            event_queryset = event_queryset.filter(alert_id__in=mine.values("id"))
        ids = list(organization_ids) if organization_ids is not None else [organization_id]
        rows = (
            event_queryset.filter(build_json_membership_query(event_queryset, "organizations", ids))
            .filter(occurred_at__gte=started_at, occurred_at__lte=ended_at)
            .annotate(bucket=TruncHour("occurred_at"))
            .values("bucket", "severity")
            .annotate(count=Count("id"))
            .order_by("bucket", "severity")[:1000]
        )
        buckets = {}
        for row in rows:
            bucket = row["bucket"].isoformat()
            buckets.setdefault(bucket, {"time": bucket, "critical": 0, "error": 0, "warning": 0})
            buckets[bucket][row["severity"]] = row["count"]
        return list(buckets.values())

    @staticmethod
    def serialize(alert: ApmAlert, user_map: dict[str, str] | None = None) -> dict:
        events = list(alert.events.all())
        outboxes_prefetched = all("outbox_entries" in getattr(event, "_prefetched_objects_cache", {}) for event in events)
        if outboxes_prefetched:
            delivery_statuses = [delivery.delivery_status for event in events for delivery in event.outbox_entries.all()]
        else:
            delivery_statuses = list(
                ApmAlertOutbox.objects.filter(event__alert=alert).values_list("delivery_status", flat=True)
            )
        status_set = set(delivery_statuses)
        if not status_set:
            notification_status = "none"
        elif status_set == {ApmAlertOutbox.DeliveryStatus.DELIVERED}:
            notification_status = "delivered"
        elif ApmAlertOutbox.DeliveryStatus.DELIVERED in status_set:
            notification_status = "partial"
        elif ApmAlertOutbox.DeliveryStatus.PENDING in status_set:
            notification_status = "pending"
        else:
            notification_status = "failed"
        return {
            "id": alert.id,
            "external_id": alert.external_id,
            "title": alert.policy_name,
            "policy_id": alert.policy_id_snapshot,
            "policy_name": alert.policy_name,
            "service_id": alert.service_id,
            "service_namespace": alert.service_namespace,
            "service_name": alert.service_name,
            "environment": alert.environment,
            "endpoint": alert.endpoint,
            "version": alert.version,
            "metric_type": alert.metric_type,
            "severity": alert.severity,
            "status": alert.status,
            "notification_status": notification_status,
            "organizations": list(alert.organizations or []),
            "current_value": alert.current_value,
            "operator": alert.operator,
            "handlers": list(alert.handlers or []),
            "handlers_display": format_user_identifiers(alert.handlers or [], user_map),
            "started_at": alert.started_at,
            "ended_at": alert.ended_at,
            "last_event_at": alert.last_event_at,
            "event_count": len(events),
            "events": [
                {
                    "id": event.id,
                    "event_id": event.event_id,
                    "action": event.action,
                    "severity": event.severity,
                    "value": event.value,
                    "occurred_at": event.occurred_at,
                    "title": event.title,
                    "description": event.description,
                }
                for event in sorted(events, key=lambda item: (item.occurred_at, str(item.id)))
            ],
        }

    @staticmethod
    def close(alert: ApmAlert, *, actor: str, occurred_at: datetime) -> ApmAlert:
        with transaction.atomic():
            locked = ApmAlert.objects.select_for_update().get(id=alert.id)
            if locked.status != ApmAlert.Status.ACTIVE:
                return locked
            state = (
                ApmPolicyTargetState.objects.select_for_update().filter(policy=locked.policy, active_alert_id=locked.external_id).first()
                if locked.policy_id
                else None
            )
            if locked.policy is not None and state is not None:
                result = PolicyQueryResult(
                    value=locked.current_value,
                    breached=False,
                    evaluated_at=occurred_at,
                    data_state=MetricDataState.AVAILABLE,
                )
                snapshot = DjangoApmPolicyService._record_event(
                    locked.policy,
                    state,
                    result,
                    occurred_at,
                    locked.external_id,
                    ApmEvent.Action.CLOSED,
                    {"severity": locked.severity, "comparator": "closed", "value": ""},
                )
                state.status = ApmPolicyTargetState.Status.NORMAL
                state.active_alert_id = ""
                state.current_severity = ""
                state.consecutive_hits = 0
                state.consecutive_recoveries = 0
                state.consecutive_no_data = 0
                state.save()
            else:
                event, _ = ApmEvent.objects.get_or_create(
                    event_id=f"{locked.external_id}:closed:{locked.severity}",
                    defaults={
                        "alert": locked,
                        "action": ApmEvent.Action.CLOSED,
                        "title": f"APM {locked.policy_name}人工关闭",
                        "description": f"由 {actor} 人工关闭",
                        "severity": locked.severity,
                        "service": locked.service_name,
                        "item": locked.metric_type,
                        "value": locked.current_value,
                        "resource_id": str(locked.service_id or ""),
                        "resource_name": f"{locked.service_namespace}/{locked.service_name}".lstrip("/"),
                        "policy_id": locked.policy_id_snapshot,
                        "environment": locked.environment,
                        "organizations": locked.organizations,
                        "occurred_at": occurred_at,
                        "ended_at": occurred_at,
                    },
                )
                previous = locked.snapshots.order_by("-occurred_at", "-id").first()
                snapshot = event.snapshot if hasattr(event, "snapshot") else None
                if snapshot is None:
                    snapshot = ApmEventSnapshot.objects.create(
                        alert=locked,
                        event=event,
                        source_event_id=event.event_id,
                        action=event.action,
                        occurred_at=occurred_at,
                        organizations=locked.organizations,
                        policy_snapshot=previous.policy_snapshot if previous else {"id": locked.policy_id_snapshot, "name": locked.policy_name},
                        object_snapshot=(
                            previous.object_snapshot
                            if previous
                            else {
                                "service_id": str(locked.service_id or ""),
                                "service_namespace": locked.service_namespace,
                                "service_name": locked.service_name,
                                "endpoint": locked.endpoint,
                                "environment": locked.environment,
                                "version": locked.version,
                            }
                        ),
                        evaluation_snapshot={
                            "value": str(locked.current_value) if locked.current_value is not None else None,
                            "severity": locked.severity,
                            "data_state": "available",
                            "comparator": "closed",
                            "threshold": None,
                        },
                        trace_context=previous.trace_context if previous else {},
                        pending_payload={"schema_version": 1, "event_id": event.event_id, "event_point": occurred_at.isoformat(), "series": []},
                        retention_expires_at=occurred_at + (previous.retention_expires_at - previous.occurred_at if previous else timedelta(days=90)),
                    )
                locked.status = ApmAlert.Status.CLOSED
                locked.ended_at = occurred_at
                locked.last_event_at = occurred_at
                locked.operator = actor
                locked.save(update_fields=("status", "ended_at", "last_event_at", "operator", "updated_at"))
            locked.operator = actor
            locked.status = ApmAlert.Status.CLOSED
            locked.ended_at = occurred_at
            locked.last_event_at = occurred_at
            locked.save(update_fields=("operator", "status", "ended_at", "last_event_at", "updated_at"))
        return ApmAlert.objects.get(id=alert.id)

    @staticmethod
    def notify_assigned(alert: ApmAlert) -> None:
        policy = ApmPolicy.objects.filter(id=alert.policy_id).first() if alert.policy_id else None
        if policy is None:
            return
        handlers = [str(item) for item in (alert.handlers or []) if item not in (None, "")]
        if not handlers:
            return
        title = f"APM {policy.name} 分派"
        body = alert.policy_name or policy.name
        payload = {
            "action": "assigned",
            "alert_id": str(alert.id),
            "external_id": alert.external_id,
            "organizations": list(alert.organizations or []),
            "title": title,
            "description": body,
        }
        for target in policy.notification_targets.filter(
            delivery_mode=ApmPolicyNotificationTarget.DeliveryMode.MESSAGE,
            recipient_mode=ApmPolicyNotificationTarget.RecipientMode.SYSTEM_USER,
        ).order_by("channel_id", "id"):
            ApmAlertOutbox.objects.get_or_create(
                event_key=f"assign:{alert.id}:channel:{target.channel_id}",
                defaults={
                    "event": None,
                    "channel_id": target.channel_id,
                    "channel_name": target.channel_name,
                    "channel_type": target.channel_type,
                    "delivery_mode": target.delivery_mode,
                    "receivers": handlers,
                    "recipients": handlers,
                    "title": title[:512],
                    "body": body,
                    "payload": payload,
                },
            )

    @staticmethod
    def _is_int_identifier(value) -> bool:
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (isinstance(value, str) and value.isdigit())

    @staticmethod
    def current_handler_identifier(actor) -> int | str:
        queryset = User.objects.filter(username=actor.username)
        domain = getattr(actor, "domain", None)
        if domain:
            matched = queryset.filter(domain=domain).first()
            if matched is not None:
                return matched.id
        matched = queryset.first()
        if matched is not None:
            return matched.id
        return actor.username

    @staticmethod
    def handler_match_values(actor) -> list:
        values = []
        identifier = DjangoApmAlertService.current_handler_identifier(actor)
        if identifier not in (None, ""):
            values.append(identifier)
        username = getattr(actor, "username", None)
        if username and username not in values:
            values.append(username)
        return values

    @staticmethod
    def filter_my_handler_alerts(queryset, actor):
        return queryset.filter(
            build_json_membership_query(queryset, "handlers", DjangoApmAlertService.handler_match_values(actor))
        )

    @staticmethod
    def _lookup_user(identifier) -> User | None:
        if identifier in (None, "") or isinstance(identifier, bool):
            return None
        if DjangoApmAlertService._is_int_identifier(identifier):
            user = User.objects.filter(id=int(identifier)).first()
            if user is not None:
                return user
        return User.objects.filter(username=str(identifier)).first()

    @staticmethod
    def _user_in_organizations(user, organization_ids) -> bool:
        allowed = {int(item) for item in organization_ids or [] if item not in (None, "")}
        if not allowed:
            return False
        for item in user.group_list or []:
            group_id = item.get("id") if isinstance(item, dict) else item
            if group_id in (None, ""):
                continue
            try:
                if int(group_id) in allowed:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    @staticmethod
    def _normalize_handlers(identifiers, organization_ids, *, allow_empty: bool, scope_label: str) -> list:
        if not identifiers:
            if allow_empty:
                return []
            raise AlertHandlerInvalid("至少指定一名处理人")
        resolved = []
        seen = set()
        for raw in identifiers:
            user = DjangoApmAlertService._lookup_user(raw)
            if user is None:
                raise AlertHandlerInvalid("处理人不存在")
            if user.disabled:
                raise AlertHandlerInvalid("处理人已禁用")
            if not DjangoApmAlertService._user_in_organizations(user, organization_ids):
                raise AlertHandlerInvalid(f"处理人不属于{scope_label}所属组织")
            if user.id in seen:
                continue
            seen.add(user.id)
            resolved.append(user.id)
        if not resolved:
            raise AlertHandlerInvalid("至少指定一名处理人")
        return resolved

    @staticmethod
    def normalize_assign_handlers(identifiers, organization_ids) -> list:
        return DjangoApmAlertService._normalize_handlers(
            identifiers, organization_ids, allow_empty=False, scope_label="告警"
        )

    @staticmethod
    def normalize_policy_handlers(identifiers, organization_ids) -> list:
        return DjangoApmAlertService._normalize_handlers(
            identifiers, organization_ids, allow_empty=True, scope_label="策略"
        )

    @staticmethod
    def _has_person_channel(policy) -> bool:
        if policy is None:
            return False
        return policy.notification_targets.filter(
            delivery_mode=ApmPolicyNotificationTarget.DeliveryMode.MESSAGE,
            recipient_mode=ApmPolicyNotificationTarget.RecipientMode.SYSTEM_USER,
        ).exists()

    @staticmethod
    def _lock_assignable_alert(alert_id, *, operable_qs=None) -> ApmAlert:
        try:
            locked = ApmAlert.objects.select_for_update().get(id=alert_id)
        except ApmAlert.DoesNotExist as exc:
            raise AlertHandlerForbidden("没有操作该告警的权限") from exc
        if operable_qs is not None and not operable_qs.filter(pk=locked.pk).exists():
            raise AlertHandlerForbidden("没有操作该告警的权限")
        if locked.status != ApmAlert.Status.ACTIVE:
            raise AlertHandlerConflict("只有空处理人的活跃告警可以认领或分派")
        if list(locked.handlers or []):
            raise AlertHandlerConflict("告警已有处理人")
        return locked

    @staticmethod
    def _schedule_assign_notification(alert: ApmAlert) -> None:
        policy_id = alert.policy_id
        alert_id = alert.id

        def _notify():
            policy = ApmPolicy.objects.filter(id=policy_id).first() if policy_id else None
            if policy is None or not DjangoApmAlertService._has_person_channel(policy):
                logger.debug(
                    "event=assign_notify_skipped alert_id=%s reason=%s",
                    alert_id,
                    "policy_deleted" if policy is None else "no_person_channel",
                )
                return
            current = ApmAlert.objects.filter(id=alert_id).first()
            if current is None:
                return
            DjangoApmAlertService.notify_assigned(current)

        transaction.on_commit(_notify)

    @staticmethod
    def _actor_name(actor) -> str:
        return getattr(actor, "username", "") or str(actor)

    @staticmethod
    def _handler_event_description(action, *, actor, handlers) -> str:
        names = "、".join(format_user_identifiers(handlers)) or str(handlers)
        operator = DjangoApmAlertService._actor_name(actor)
        if action == ApmEvent.Action.CLAIMED:
            return f"{operator} 认领，处理人变为 {names}"
        return f"{operator} 分派给 {names}"

    @staticmethod
    def _write_handler_event(alert: ApmAlert, *, action, actor) -> None:
        occurred_at = timezone.now()
        action_label = "认领" if action == ApmEvent.Action.CLAIMED else "分派"
        ApmEvent.objects.create(
            event_id=f"{alert.external_id}:{action}:{uuid4().hex}",
            alert=alert,
            action=action,
            title=f"APM {alert.policy_name}{action_label}",
            description=DjangoApmAlertService._handler_event_description(
                action, actor=actor, handlers=alert.handlers
            ),
            severity=alert.severity,
            service=alert.service_name,
            item=alert.metric_type,
            value=alert.current_value,
            resource_id=str(alert.service_id or ""),
            resource_name=f"{alert.service_namespace}/{alert.service_name}".lstrip("/"),
            policy_id=alert.policy_id_snapshot,
            environment=alert.environment,
            organizations=list(alert.organizations or []),
            occurred_at=occurred_at,
        )

    @staticmethod
    def claim(alert: ApmAlert, *, actor, operable_qs=None) -> ApmAlert:
        with transaction.atomic():
            locked = DjangoApmAlertService._lock_assignable_alert(alert.id, operable_qs=operable_qs)
            locked.handlers = [DjangoApmAlertService.current_handler_identifier(actor)]
            locked.save(update_fields=("handlers", "updated_at"))
            DjangoApmAlertService._write_handler_event(locked, action=ApmEvent.Action.CLAIMED, actor=actor)
        logger.info("event=alert_claimed alert_id=%s", alert.id)
        return ApmAlert.objects.get(id=alert.id)

    @staticmethod
    def assign(alert: ApmAlert, *, handlers, actor, operable_qs=None) -> ApmAlert:
        with transaction.atomic():
            locked = DjangoApmAlertService._lock_assignable_alert(alert.id, operable_qs=operable_qs)
            locked.handlers = DjangoApmAlertService.normalize_assign_handlers(handlers, locked.organizations)
            locked.save(update_fields=("handlers", "updated_at"))
            DjangoApmAlertService._write_handler_event(locked, action=ApmEvent.Action.ASSIGNED, actor=actor)
            DjangoApmAlertService._schedule_assign_notification(locked)
        logger.info("event=alert_assigned alert_id=%s handler_count=%s", alert.id, len(locked.handlers))
        return ApmAlert.objects.get(id=alert.id)
