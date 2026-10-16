from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from django.db import transaction
from django.db.models import Q

from apps.core.utils.viewset_utils import build_json_membership_query
from apps.rum.services.control import ControlError

CLAIM_TTL_SECONDS = 300


def parse_dt(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def fmt_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def org_ids(values) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for item in values or []:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number <= 0 or number in seen:
            continue
        seen.add(number)
        out.append(number)
    return out


def overlaps_orgs(organizations, visible: set[int] | None) -> bool:
    if visible is None:
        return True
    return bool(set(org_ids(organizations)) & set(visible))


def _now_stamp() -> str:
    return fmt_dt(datetime.now(timezone.utc)) or ""


class MemoryPolicyStore:
    def __init__(self):
        self._items: dict[str, dict] = {}
        self._seq = 0

    def list(self, visible_orgs: set[int] | None = None) -> list[dict]:
        rows = [dict(item) for item in self._items.values() if overlaps_orgs(item.get("organizations"), visible_orgs)]
        rows.sort(key=lambda row: row.get("updatedAt") or "", reverse=True)
        return rows

    def list_enabled(self) -> list[dict]:
        return [dict(item) for item in self._items.values() if item.get("enabled")]

    def get(self, policy_id: str, visible_orgs: set[int] | None = None) -> dict | None:
        item = self._items.get(policy_id)
        if item is None or not overlaps_orgs(item.get("organizations"), visible_orgs):
            return None
        return dict(item)

    def save(self, policy: dict) -> dict:
        item = dict(policy)
        if not item.get("id"):
            self._seq += 1
            item["id"] = f"policy-{self._seq}"
            item["createdAt"] = item.get("createdAt") or _now_stamp()
        item["updatedAt"] = _now_stamp()
        item.setdefault("organizations", [])
        item.setdefault("notificationTargets", [])
        item.setdefault("handlers", [])
        item.setdefault("consecutiveHits", 0)
        item.setdefault("consecutiveRecoveries", 0)
        item.setdefault("consecutiveNoData", 0)
        item.setdefault("evaluationCursor", "")
        item.setdefault("lastEvaluationResult", "")
        self._items[item["id"]] = item
        return dict(item)

    def delete(self, policy_id: str) -> None:
        if policy_id not in self._items:
            raise ControlError("not_found", "monitor not found")
        del self._items[policy_id]

    @contextmanager
    def locked(self, policy_id: str) -> Iterator[dict | None]:
        item = self._items.get(policy_id)
        if item is None:
            yield None
            return
        yield item
        item["updatedAt"] = _now_stamp()


class MemoryEventStore:
    def __init__(self):
        self.alerts: dict[str, dict] = {}
        self.events: dict[str, dict] = {}
        self.deliveries: dict[str, dict] = {}
        self._seq = 0

    def _next(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{self._seq}"

    def list_alerts(
        self,
        page: int,
        limit: int,
        *,
        visible_orgs: set[int] | None = None,
        status_group: str = "",
        application: str = "",
        keyword: str = "",
        handler: str = "",
    ) -> tuple[list[dict], int]:
        rows = [dict(item) for item in self.alerts.values() if overlaps_orgs(item.get("organizations"), visible_orgs)]
        if status_group == "active":
            rows = [row for row in rows if row.get("status") == "active"]
        elif status_group == "history":
            rows = [row for row in rows if row.get("status") in {"recovered", "closed"}]
        if application:
            rows = [row for row in rows if row.get("application") == application]
        if keyword:
            needle = keyword.lower()
            rows = [
                row
                for row in rows
                if needle in str(row.get("policyName") or "").lower()
                or needle in str(row.get("application") or "").lower()
                or needle in str(row.get("metric") or "").lower()
            ]
        if handler:
            rows = [row for row in rows if handler in {str(item) for item in row.get("handlers") or []}]
        rows.sort(key=lambda row: row.get("lastEventAt") or row.get("startedAt") or "", reverse=True)
        total = len(rows)
        start = (page - 1) * limit
        return rows[start : start + limit], total

    def list_page(self, page: int, limit: int) -> tuple[list[dict], int]:
        return self.list_alerts(page, limit)

    def get_alert(self, alert_id: str, visible_orgs: set[int] | None = None) -> dict | None:
        item = self.alerts.get(alert_id)
        if item is None or not overlaps_orgs(item.get("organizations"), visible_orgs):
            return None
        return dict(item)

    def get(self, alert_id: str) -> dict | None:
        return self.get_alert(alert_id)

    def active_for_policy(self, policy_id: str) -> dict | None:
        rows = [
            item
            for item in self.alerts.values()
            if item.get("policyId") == policy_id and item.get("status") == "active"
        ]
        if not rows:
            return None
        rows.sort(key=lambda row: row.get("startedAt") or "", reverse=True)
        return dict(rows[0])

    def latest_open(self, policy_id: str) -> dict | None:
        return self.active_for_policy(policy_id)

    def active_policy_ids(self) -> set[str]:
        return {item["policyId"] for item in self.alerts.values() if item.get("status") == "active" and item.get("policyId")}

    def create_alert(self, alert: dict) -> dict:
        item = dict(alert)
        item["id"] = item.get("id") or self._next("alert")
        item.setdefault("createdAt", _now_stamp())
        self.alerts[item["id"]] = item
        return dict(item)

    def create(self, alert: dict) -> dict:
        return self.create_alert(alert)

    def save_alert(self, alert: dict) -> dict:
        item = dict(alert)
        if not item.get("id") or item["id"] not in self.alerts:
            return self.create_alert(item)
        self.alerts[item["id"]] = item
        return dict(item)

    def save(self, alert: dict) -> dict:
        return self.save_alert(alert)

    def add_event(self, event: dict) -> dict:
        key = event.get("eventKey") or ""
        for item in self.events.values():
            if item.get("eventKey") == key:
                return dict(item)
        item = dict(event)
        item["id"] = item.get("id") or self._next("event")
        self.events[item["id"]] = item
        return dict(item)

    def list_events(self, alert_id: str) -> list[dict]:
        rows = [dict(item) for item in self.events.values() if item.get("alertId") == alert_id]
        rows.sort(key=lambda row: (row.get("occurredAt") or "", row.get("id") or ""))
        return rows

    def add_delivery(self, delivery: dict) -> dict:
        key = delivery.get("deliveryKey") or ""
        for item in self.deliveries.values():
            if item.get("deliveryKey") == key:
                return dict(item)
        item = dict(delivery)
        item["id"] = item.get("id") or self._next("delivery")
        item.setdefault("status", "pending")
        item.setdefault("attempts", 0)
        self.deliveries[item["id"]] = item
        return dict(item)

    def list_deliveries(self, alert_id: str) -> list[dict]:
        rows = [dict(item) for item in self.deliveries.values() if item.get("alertId") == alert_id]
        rows.sort(key=lambda row: row.get("createdAt") or row.get("id") or "")
        return rows

    def due_delivery_ids(self, now: datetime, limit: int = 100) -> list[str]:
        due: list[dict] = []
        for item in self.deliveries.values():
            if item.get("status") != "pending":
                continue
            retry_at = parse_dt(item.get("nextRetryAt"))
            if retry_at is not None and retry_at > now:
                continue
            claimed = parse_dt(item.get("claimedAt"))
            if claimed is not None and (now - claimed).total_seconds() < CLAIM_TTL_SECONDS:
                continue
            due.append(item)
        due.sort(key=lambda row: row.get("createdAt") or "")
        return [item["id"] for item in due[:limit]]

    def claim_delivery(self, delivery_id: str, now: datetime) -> dict | None:
        item = self.deliveries.get(delivery_id)
        if item is None or item.get("status") != "pending":
            return None
        retry_at = parse_dt(item.get("nextRetryAt"))
        if retry_at is not None and retry_at > now:
            return None
        claimed = parse_dt(item.get("claimedAt"))
        if claimed is not None and (now - claimed).total_seconds() < CLAIM_TTL_SECONDS:
            return None
        item["claimedAt"] = fmt_dt(now)
        return dict(item)

    def save_delivery(self, delivery: dict) -> dict:
        item = dict(delivery)
        self.deliveries[item["id"]] = item
        return dict(item)


def _serialize_target(item) -> dict:
    return {
        "channelId": item.channel_id,
        "channelName": item.channel_name,
        "channelType": item.channel_type,
        "deliveryMode": item.delivery_mode,
        "recipientMode": item.recipient_mode,
        "recipients": list(item.recipients or []),
    }


def _serialize_policy(item) -> dict:
    organizations = list(item.organization_links.order_by("organization").values_list("organization", flat=True))
    targets = [_serialize_target(target) for target in item.notification_targets.order_by("channel_id", "id")]
    return {
        "id": item.id,
        "name": item.name,
        "application": item.application,
        "organizations": organizations,
        "metric": item.metric,
        "severity": item.severity,
        "comparator": item.comparator,
        "warnThreshold": item.warn_threshold,
        "criticalThreshold": item.critical_threshold,
        "evaluationWindowMinutes": item.evaluation_window_minutes,
        "forDurationSec": item.for_duration_sec,
        "noDataAfter": item.no_data_after,
        "renotifyMinutes": item.renotify_minutes,
        "handlers": list(item.handlers or []),
        "notificationTargets": targets,
        "enabled": item.enabled,
        "consecutiveHits": item.consecutive_hits,
        "consecutiveRecoveries": item.consecutive_recoveries,
        "consecutiveNoData": item.consecutive_no_data,
        "evaluationCursor": item.evaluation_cursor,
        "lastSucceededAt": fmt_dt(item.last_succeeded_at),
        "lastFailedAt": fmt_dt(item.last_failed_at),
        "lastEvaluationResult": item.last_evaluation_result,
        "createdAt": fmt_dt(item.created_at),
        "updatedAt": fmt_dt(item.updated_at),
    }


def _serialize_alert(item) -> dict:
    return {
        "id": item.id,
        "policyId": item.policy_id_snapshot,
        "policyName": item.policy_name,
        "application": item.application,
        "metric": item.metric,
        "comparator": item.comparator,
        "warnThreshold": item.warn_threshold,
        "criticalThreshold": item.critical_threshold,
        "severity": item.severity,
        "status": item.status,
        "currentValue": item.current_value,
        "organizations": list(item.organizations or []),
        "handlers": list(item.handlers or []),
        "operator": item.operator,
        "renotifyCount": item.renotify_count,
        "startedAt": fmt_dt(item.started_at),
        "endedAt": fmt_dt(item.ended_at),
        "lastEventAt": fmt_dt(item.last_event_at),
        "lastNotifiedAt": fmt_dt(item.last_notified_at),
        "createdAt": fmt_dt(item.created_at),
    }


def _serialize_event(item) -> dict:
    return {
        "id": item.id,
        "eventKey": item.event_key,
        "alertId": item.alert_id,
        "action": item.action,
        "occurredAt": fmt_dt(item.occurred_at),
        "severity": item.severity,
        "value": item.value,
        "content": dict(item.content or {}),
        "organizations": list(item.organizations or []),
    }


def _serialize_delivery(item) -> dict:
    return {
        "id": item.id,
        "deliveryKey": item.delivery_key,
        "eventId": item.event_id,
        "alertId": item.alert_id,
        "channelId": item.channel_id,
        "channelName": item.channel_name,
        "channelType": item.channel_type,
        "deliveryMode": item.delivery_mode,
        "recipients": list(item.recipients or []),
        "title": item.title,
        "body": item.body,
        "payload": dict(item.payload or {}),
        "status": item.status,
        "attempts": item.attempts,
        "nextRetryAt": fmt_dt(item.next_retry_at),
        "claimedAt": fmt_dt(item.claimed_at),
        "lastErrorCode": item.last_error_code,
        "lastErrorMessage": item.last_error_message,
        "deliveredAt": fmt_dt(item.delivered_at),
        "failedAt": fmt_dt(item.failed_at),
        "createdAt": fmt_dt(item.created_at),
    }


def _apply_policy(item, policy: dict) -> None:
    item.name = policy["name"]
    item.application = policy["application"]
    item.metric = policy["metric"]
    item.severity = policy.get("severity") or "warning"
    item.comparator = policy.get("comparator") or ">="
    item.warn_threshold = policy.get("warnThreshold") or 0
    item.critical_threshold = policy.get("criticalThreshold") or 0
    item.evaluation_window_minutes = int(policy.get("evaluationWindowMinutes") or 15)
    item.for_duration_sec = int(policy.get("forDurationSec") if policy.get("forDurationSec") is not None else 300)
    item.no_data_after = int(policy.get("noDataAfter") if policy.get("noDataAfter") is not None else 3)
    item.renotify_minutes = policy.get("renotifyMinutes")
    item.handlers = list(policy.get("handlers") or [])
    item.enabled = bool(policy.get("enabled", True))
    item.consecutive_hits = int(policy.get("consecutiveHits") or 0)
    item.consecutive_recoveries = int(policy.get("consecutiveRecoveries") or 0)
    item.consecutive_no_data = int(policy.get("consecutiveNoData") or 0)
    item.evaluation_cursor = policy.get("evaluationCursor") or ""
    item.last_succeeded_at = parse_dt(policy.get("lastSucceededAt"))
    item.last_failed_at = parse_dt(policy.get("lastFailedAt"))
    item.last_evaluation_result = policy.get("lastEvaluationResult") or ""


def _replace_policy_children(item, policy: dict) -> None:
    from apps.rum.models import RumAlertPolicyNotificationTarget, RumAlertPolicyOrganization

    item.organization_links.all().delete()
    RumAlertPolicyOrganization.objects.bulk_create(
        [RumAlertPolicyOrganization(policy=item, organization=organization) for organization in org_ids(policy.get("organizations"))]
    )
    item.notification_targets.all().delete()
    RumAlertPolicyNotificationTarget.objects.bulk_create(
        [
            RumAlertPolicyNotificationTarget(
                policy=item,
                channel_id=int(target["channelId"]),
                channel_name=target.get("channelName") or "",
                channel_type=target.get("channelType") or "",
                delivery_mode=target.get("deliveryMode") or "message",
                recipient_mode=target.get("recipientMode") or "none",
                recipients=list(target.get("recipients") or []),
            )
            for target in policy.get("notificationTargets") or []
        ]
    )


class DjangoPolicyStore:
    def _queryset(self):
        from apps.rum.models import RumAlertPolicy

        return RumAlertPolicy.objects.prefetch_related("organization_links", "notification_targets")

    def list(self, visible_orgs: set[int] | None = None) -> list[dict]:
        qs = self._queryset()
        if visible_orgs is not None:
            if not visible_orgs:
                return []
            qs = qs.filter(organization_links__organization__in=list(visible_orgs)).distinct()
        return [_serialize_policy(item) for item in qs.order_by("-updated_at")]

    def list_enabled(self) -> list[dict]:
        return [_serialize_policy(item) for item in self._queryset().filter(enabled=True).order_by("-updated_at")]

    def get(self, policy_id: str, visible_orgs: set[int] | None = None) -> dict | None:
        from apps.rum.models import RumAlertPolicy

        try:
            item = self._queryset().get(pk=policy_id)
        except RumAlertPolicy.DoesNotExist:
            return None
        policy = _serialize_policy(item)
        if not overlaps_orgs(policy.get("organizations"), visible_orgs):
            return None
        return policy

    def save(self, policy: dict) -> dict:
        from apps.rum.models import RumAlertPolicy

        with transaction.atomic():
            if policy.get("id"):
                try:
                    item = RumAlertPolicy.objects.select_for_update().get(pk=policy["id"])
                except RumAlertPolicy.DoesNotExist as exc:
                    raise ControlError("not_found", "monitor not found") from exc
            else:
                item = RumAlertPolicy()
            _apply_policy(item, policy)
            item.save()
            _replace_policy_children(item, policy)
            item = self._queryset().get(pk=item.pk)
            return _serialize_policy(item)

    def delete(self, policy_id: str) -> None:
        from apps.rum.models import RumAlertPolicy

        deleted, _ = RumAlertPolicy.objects.filter(pk=policy_id).delete()
        if not deleted:
            raise ControlError("not_found", "monitor not found")

    @contextmanager
    def locked(self, policy_id: str) -> Iterator[dict | None]:
        from apps.rum.models import RumAlertPolicy

        with transaction.atomic():
            try:
                item = (
                    RumAlertPolicy.objects.select_for_update()
                    .prefetch_related("organization_links", "notification_targets")
                    .get(pk=policy_id)
                )
            except RumAlertPolicy.DoesNotExist:
                yield None
                return
            policy = _serialize_policy(item)
            yield policy
            _apply_policy(item, policy)
            item.save()


class DjangoEventStore:
    def list_alerts(
        self,
        page: int,
        limit: int,
        *,
        visible_orgs: set[int] | None = None,
        status_group: str = "",
        application: str = "",
        keyword: str = "",
        handler: str = "",
    ) -> tuple[list[dict], int]:
        from apps.rum.models import RumAlert

        qs = RumAlert.objects.all()
        if visible_orgs is not None:
            if not visible_orgs:
                return [], 0
            qs = build_json_membership_query(qs, "organizations", list(visible_orgs))
        if status_group == "active":
            qs = qs.filter(status="active")
        elif status_group == "history":
            qs = qs.filter(status__in=["recovered", "closed"])
        if application:
            qs = qs.filter(application=application)
        if keyword:
            qs = qs.filter(Q(policy_name__icontains=keyword) | Q(application__icontains=keyword) | Q(metric__icontains=keyword))
        if handler:
            qs = build_json_membership_query(qs, "handlers", [handler])
        qs = qs.order_by("-last_event_at", "-id")
        total = qs.count()
        start = (page - 1) * limit
        return [_serialize_alert(item) for item in qs[start : start + limit]], total

    def list_page(self, page: int, limit: int) -> tuple[list[dict], int]:
        return self.list_alerts(page, limit)

    def get_alert(self, alert_id: str, visible_orgs: set[int] | None = None) -> dict | None:
        from apps.rum.models import RumAlert

        try:
            item = RumAlert.objects.get(pk=alert_id)
        except RumAlert.DoesNotExist:
            return None
        alert = _serialize_alert(item)
        if not overlaps_orgs(alert.get("organizations"), visible_orgs):
            return None
        return alert

    def get(self, alert_id: str) -> dict | None:
        return self.get_alert(alert_id)

    def active_for_policy(self, policy_id: str) -> dict | None:
        from apps.rum.models import RumAlert

        item = (
            RumAlert.objects.select_for_update()
            .filter(policy_id_snapshot=policy_id, status="active")
            .order_by("-started_at")
            .first()
        )
        return _serialize_alert(item) if item else None

    def latest_open(self, policy_id: str) -> dict | None:
        return self.active_for_policy(policy_id)

    def active_policy_ids(self) -> set[str]:
        from apps.rum.models import RumAlert

        return set(RumAlert.objects.filter(status="active").values_list("policy_id_snapshot", flat=True))

    def create_alert(self, alert: dict) -> dict:
        from apps.rum.models import RumAlert, RumAlertPolicy

        policy = RumAlertPolicy.objects.filter(pk=alert.get("policyId") or "").first()
        item = RumAlert(
            policy=policy,
            policy_id_snapshot=alert.get("policyId") or "",
            policy_name=alert.get("policyName") or "",
            application=alert.get("application") or "",
            metric=alert.get("metric") or "",
            comparator=alert.get("comparator") or "",
            warn_threshold=alert.get("warnThreshold") or 0,
            critical_threshold=alert.get("criticalThreshold") or 0,
            severity=alert.get("severity") or "",
            status=alert.get("status") or "active",
            current_value=alert.get("currentValue"),
            organizations=list(alert.get("organizations") or []),
            handlers=list(alert.get("handlers") or []),
            operator=alert.get("operator") or "",
            renotify_count=int(alert.get("renotifyCount") or 0),
            started_at=parse_dt(alert.get("startedAt")),
            ended_at=parse_dt(alert.get("endedAt")),
            last_event_at=parse_dt(alert.get("lastEventAt")),
            last_notified_at=parse_dt(alert.get("lastNotifiedAt")),
        )
        if alert.get("id"):
            item.id = alert["id"]
        item.save()
        return _serialize_alert(item)

    def create(self, alert: dict) -> dict:
        return self.create_alert(alert)

    def save_alert(self, alert: dict) -> dict:
        from apps.rum.models import RumAlert

        try:
            item = RumAlert.objects.select_for_update().get(pk=alert["id"])
        except RumAlert.DoesNotExist:
            return self.create_alert(alert)
        item.status = alert.get("status") or item.status
        item.severity = alert.get("severity") or item.severity
        item.current_value = alert.get("currentValue")
        item.handlers = list(alert.get("handlers") or [])
        item.operator = alert.get("operator") or ""
        item.renotify_count = int(alert.get("renotifyCount") or 0)
        item.ended_at = parse_dt(alert.get("endedAt"))
        item.last_event_at = parse_dt(alert.get("lastEventAt"))
        item.last_notified_at = parse_dt(alert.get("lastNotifiedAt"))
        item.save()
        return _serialize_alert(item)

    def save(self, alert: dict) -> dict:
        return self.save_alert(alert)

    def add_event(self, event: dict) -> dict:
        from apps.rum.models import RumAlert, RumAlertEvent

        existing = RumAlertEvent.objects.filter(event_key=event.get("eventKey") or "").first()
        if existing is not None:
            return _serialize_event(existing)
        alert = RumAlert.objects.get(pk=event["alertId"])
        item = RumAlertEvent(
            event_key=event["eventKey"],
            alert=alert,
            action=event.get("action") or "",
            occurred_at=parse_dt(event.get("occurredAt")),
            severity=event.get("severity") or "",
            value=event.get("value"),
            content=dict(event.get("content") or {}),
            organizations=list(event.get("organizations") or []),
        )
        item.save()
        return _serialize_event(item)

    def list_events(self, alert_id: str) -> list[dict]:
        from apps.rum.models import RumAlertEvent

        return [_serialize_event(item) for item in RumAlertEvent.objects.filter(alert_id=alert_id).order_by("occurred_at", "id")]

    def add_delivery(self, delivery: dict) -> dict:
        from apps.rum.models import RumAlert, RumAlertDelivery, RumAlertEvent

        existing = RumAlertDelivery.objects.filter(delivery_key=delivery.get("deliveryKey") or "").first()
        if existing is not None:
            return _serialize_delivery(existing)
        alert = RumAlert.objects.get(pk=delivery["alertId"])
        event = RumAlertEvent.objects.filter(pk=delivery.get("eventId") or "").first()
        item = RumAlertDelivery(
            delivery_key=delivery["deliveryKey"],
            event=event,
            alert=alert,
            channel_id=delivery.get("channelId"),
            channel_name=delivery.get("channelName") or "",
            channel_type=delivery.get("channelType") or "",
            delivery_mode=delivery.get("deliveryMode") or "message",
            recipients=list(delivery.get("recipients") or []),
            title=delivery.get("title") or "",
            body=delivery.get("body") or "",
            payload=dict(delivery.get("payload") or {}),
        )
        item.save()
        return _serialize_delivery(item)

    def list_deliveries(self, alert_id: str) -> list[dict]:
        from apps.rum.models import RumAlertDelivery

        return [_serialize_delivery(item) for item in RumAlertDelivery.objects.filter(alert_id=alert_id).order_by("created_at", "id")]

    def due_delivery_ids(self, now: datetime, limit: int = 100) -> list[str]:
        from apps.rum.models import RumAlertDelivery

        claim_before = now.timestamp() - CLAIM_TTL_SECONDS
        claim_cutoff = datetime.fromtimestamp(claim_before, tz=timezone.utc)
        qs = RumAlertDelivery.objects.filter(status="pending").filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))
        qs = qs.filter(Q(claimed_at__isnull=True) | Q(claimed_at__lte=claim_cutoff))
        return list(qs.order_by("created_at", "id").values_list("id", flat=True)[:limit])

    def claim_delivery(self, delivery_id: str, now: datetime) -> dict | None:
        from apps.rum.models import RumAlertDelivery

        with transaction.atomic():
            try:
                item = RumAlertDelivery.objects.select_for_update().get(pk=delivery_id)
            except RumAlertDelivery.DoesNotExist:
                return None
            if item.status != "pending":
                return None
            if item.next_retry_at is not None and item.next_retry_at > now:
                return None
            if item.claimed_at is not None and (now - item.claimed_at).total_seconds() < CLAIM_TTL_SECONDS:
                return None
            item.claimed_at = now
            item.save(update_fields=("claimed_at",))
            return _serialize_delivery(item)

    def save_delivery(self, delivery: dict) -> dict:
        from apps.rum.models import RumAlertDelivery

        item = RumAlertDelivery.objects.select_for_update().get(pk=delivery["id"])
        item.status = delivery.get("status") or item.status
        item.attempts = int(delivery.get("attempts") or 0)
        item.next_retry_at = parse_dt(delivery.get("nextRetryAt"))
        item.claimed_at = parse_dt(delivery.get("claimedAt"))
        item.last_error_code = (delivery.get("lastErrorCode") or "")[:128]
        item.last_error_message = (delivery.get("lastErrorMessage") or "")[:512]
        item.delivered_at = parse_dt(delivery.get("deliveredAt"))
        item.failed_at = parse_dt(delivery.get("failedAt"))
        item.save()
        return _serialize_delivery(item)


_policy_store: Any = None
_event_store: Any = None


def get_policy_store():
    global _policy_store
    if _policy_store is None:
        _policy_store = DjangoPolicyStore()
    return _policy_store


def get_event_store():
    global _event_store
    if _event_store is None:
        _event_store = DjangoEventStore()
    return _event_store


def set_policy_store(store) -> None:
    global _policy_store
    _policy_store = store


def set_event_store(store) -> None:
    global _event_store
    _event_store = store
