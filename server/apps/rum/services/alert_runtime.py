from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

from apps.core.logger import rum_logger as logger
from apps.rum.services.alerteval import breached, should_renotify
from apps.rum.services.alert_store import fmt_dt, parse_dt
from apps.rum.services.notify import render_message

LEVEL_TO_ALERT_CENTER = {
    "critical": "0",
    "warning": "2",
    "info": "3",
}
TERMINAL_DELIVERY_CODES = {"channel_not_found", "invalid_recipients", "channel_forbidden"}
MAX_DELIVERY_ATTEMPTS = 8
SYSTEM_OPERATOR = "system"


def minute_cursor(when: datetime) -> str:
    return when.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()


def hits_required(policy: dict) -> int:
    seconds = int(policy.get("forDurationSec") or 0)
    if seconds <= 0:
        return 1
    return max(1, seconds // 60)


def _is_manual_channel(target: dict) -> bool:
    return target.get("deliveryMode") != "alert_event_copy" and target.get("recipientMode") != "none"


def _is_alert_center_copy(target: dict) -> bool:
    return target.get("deliveryMode") == "alert_event_copy"


def _unix_seconds(value) -> str:
    moment = value if isinstance(value, datetime) else parse_dt(value)
    if moment is None:
        moment = datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return str(int(moment.astimezone(timezone.utc).timestamp()))


_COPY_ACTION = {"triggered": "created", "recovered": "recovery", "closed": "closed"}


class RumAlertRuntime:
    def __init__(self, *, policies, alerts, analytics=None, dispatcher=None, now: Callable[[], datetime] | None = None, tenant_id: str = "core"):
        self.policies = policies
        self.alerts = alerts
        self.analytics = analytics
        self.dispatcher = dispatcher
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.tenant_id = tenant_id

    def evaluate_all(self) -> dict:
        if self.analytics is None or not self.analytics.available():
            return {"skipped": True, "reason": "analytics", "evaluated": 0, "fired": 0, "resolved": 0, "renotified": 0, "skippedCount": 0}
        policies = self.policies.list_enabled()
        fired = resolved = renotified = failed = skipped = 0
        for policy in policies:
            action = self.evaluate_policy(policy["id"], self.now())
            if action == "fired":
                fired += 1
            elif action == "recovered":
                resolved += 1
            elif action == "renotified":
                renotified += 1
            elif action == "failed":
                failed += 1
            elif action in {"skipped", "duplicate"}:
                skipped += 1
        return {
            "skipped": False,
            "evaluated": len(policies),
            "fired": fired,
            "resolved": resolved,
            "renotified": renotified,
            "skippedCount": failed + skipped,
            "failed": failed,
        }

    def evaluate_policy(self, policy_id: str, evaluated_at: datetime) -> str:
        evaluated_at = evaluated_at.astimezone(timezone.utc)
        cursor = minute_cursor(evaluated_at)
        with self.policies.locked(policy_id) as policy:
            if policy is None or not policy.get("enabled"):
                return "skipped"
            if policy.get("evaluationCursor") == cursor:
                return "duplicate"
            try:
                value = self._read_metric(policy, evaluated_at)
            except Exception as exc:
                policy["lastFailedAt"] = fmt_dt(evaluated_at)
                policy["lastEvaluationResult"] = "failed"
                logger.warning(
                    "rum alert metric read skipped policy_id=%s failed_stage=%s error_type=%s",
                    policy_id,
                    "monitor_metric",
                    type(exc).__name__,
                )
                return "failed"
            action = self._advance(policy, value, evaluated_at)
            policy["evaluationCursor"] = cursor
            policy["lastSucceededAt"] = fmt_dt(evaluated_at)
            policy["lastFailedAt"] = None
            policy["lastEvaluationResult"] = "ok"
            return action

    def close_active(self, policy: dict, *, operator: str = SYSTEM_OPERATOR, at: datetime | None = None) -> dict | None:
        with self.policies.locked(policy["id"]):
            alert = self.alerts.active_for_policy(policy["id"])
            if alert is None:
                return None
            now = (at or self.now()).astimezone(timezone.utc)
            stamp = fmt_dt(now)
            alert["status"] = "closed"
            alert["operator"] = operator
            alert["endedAt"] = stamp
            alert["lastEventAt"] = stamp
            saved = self.alerts.save_alert(alert)
            event = self.alerts.add_event(
                {
                    "eventKey": f"{saved['id']}:closed:{uuid4().hex}",
                    "alertId": saved["id"],
                    "action": "closed",
                    "occurredAt": stamp,
                    "severity": saved.get("severity") or "",
                    "value": saved.get("currentValue"),
                    "organizations": list(saved.get("organizations") or []),
                    "content": {"actor": operator, "action": "closed", "handlers": list(saved.get("handlers") or [])},
                }
            )
            self._enqueue(policy, saved, event, "closed", now, copy_only=True)
            return saved

    def deliver_due(self, now: datetime | None = None, limit: int = 100) -> dict:
        moment = (now or self.now()).astimezone(timezone.utc)
        sent = failed = 0
        for delivery_id in self.alerts.due_delivery_ids(moment, limit):
            claimed = self.alerts.claim_delivery(delivery_id, moment)
            if claimed is None:
                continue
            try:
                result = self.dispatcher.dispatch(claimed)
            except Exception as exc:
                _log_delivery_exception(claimed.get("id") or delivery_id, exc)
                result = {
                    "delivered": False,
                    "retryable": True,
                    "code": "dispatcher_exception",
                    "message": "通知投递失败。",
                }
            if result.get("delivered"):
                claimed["status"] = "delivered"
                claimed["attempts"] = int(claimed.get("attempts") or 0) + 1
                claimed["nextRetryAt"] = None
                claimed["claimedAt"] = None
                claimed["lastErrorCode"] = ""
                claimed["lastErrorMessage"] = ""
                claimed["deliveredAt"] = fmt_dt(moment)
                claimed["failedAt"] = None
                sent += 1
            else:
                _mark_delivery_failed(claimed, result, moment)
                if claimed.get("lastErrorCode") != "dispatcher_exception":
                    logger.warning(
                        "rum alert delivery failed delivery_id=%s failed_stage=%s error_type=%s",
                        claimed.get("id") or delivery_id,
                        "dispatch",
                        claimed.get("lastErrorCode") or "delivery_failed",
                    )
                failed += 1
            self.alerts.save_delivery(claimed)
        return {"sent": sent, "failed": failed}

    def _read_metric(self, policy: dict, evaluated_at: datetime):
        window = int(policy.get("evaluationWindowMinutes") or 15)
        return self.analytics.monitor_metric(
            self.tenant_id,
            {
                "application": policy["application"],
                "metric": policy["metric"],
                "from": evaluated_at - timedelta(minutes=window),
                "to": evaluated_at,
            },
        )

    def _advance(self, policy: dict, value, evaluated_at: datetime) -> str:
        required = hits_required(policy)
        active = self.alerts.active_for_policy(policy["id"])
        if value is None:
            policy["consecutiveHits"] = 0
            policy["consecutiveRecoveries"] = 0
            policy["consecutiveNoData"] = int(policy.get("consecutiveNoData") or 0) + 1
            no_data_after = int(policy.get("noDataAfter") or 0)
            if active is None and no_data_after > 0 and policy["consecutiveNoData"] >= no_data_after:
                self._open_alert(policy, None, policy.get("severity") or "warning", evaluated_at, no_data=True)
                return "fired"
            if active is not None and _opened_for_no_data(active):
                return self._maybe_renotify(policy, active, evaluated_at)
            return "none"

        policy["consecutiveNoData"] = 0
        level = breached(
            policy.get("comparator") or ">=",
            float(value),
            float(policy.get("warnThreshold") or 0),
            float(policy.get("criticalThreshold") or 0),
        )
        if level:
            policy["consecutiveRecoveries"] = 0
            if active is not None:
                active["currentValue"] = float(value)
                active["severity"] = level
                active["lastEventAt"] = fmt_dt(evaluated_at)
                saved = self.alerts.save_alert(active)
                return self._maybe_renotify(policy, saved, evaluated_at)
            policy["consecutiveHits"] = int(policy.get("consecutiveHits") or 0) + 1
            if policy["consecutiveHits"] >= required:
                policy["consecutiveHits"] = 0
                self._open_alert(policy, float(value), level, evaluated_at, no_data=False)
                return "fired"
            return "none"

        policy["consecutiveHits"] = 0
        if active is None:
            policy["consecutiveRecoveries"] = 0
            return "none"
        policy["consecutiveRecoveries"] = int(policy.get("consecutiveRecoveries") or 0) + 1
        if policy["consecutiveRecoveries"] < required:
            active["currentValue"] = float(value)
            active["lastEventAt"] = fmt_dt(evaluated_at)
            self.alerts.save_alert(active)
            return "none"
        policy["consecutiveRecoveries"] = 0
        self._recover_alert(policy, active, float(value), evaluated_at)
        return "recovered"

    def _open_alert(self, policy: dict, value, severity: str, evaluated_at: datetime, *, no_data: bool) -> dict:
        stamp = fmt_dt(evaluated_at)
        alert = self.alerts.create_alert(
            {
                "policyId": policy["id"],
                "policyName": policy.get("name") or "",
                "application": policy.get("application") or "",
                "metric": policy.get("metric") or "",
                "comparator": policy.get("comparator") or "",
                "warnThreshold": policy.get("warnThreshold") or 0,
                "criticalThreshold": policy.get("criticalThreshold") or 0,
                "severity": severity,
                "status": "active",
                "currentValue": value,
                "organizations": list(policy.get("organizations") or []),
                "handlers": list(policy.get("handlers") or []),
                "operator": "",
                "renotifyCount": 0,
                "startedAt": stamp,
                "lastEventAt": stamp,
                "lastNotifiedAt": stamp,
                "noData": no_data,
            }
        )
        event = self.alerts.add_event(
            {
                "eventKey": f"{alert['id']}:triggered:{uuid4().hex}",
                "alertId": alert["id"],
                "action": "triggered",
                "occurredAt": stamp,
                "severity": severity,
                "value": value,
                "organizations": list(alert.get("organizations") or []),
                "content": {
                    "actor": SYSTEM_OPERATOR,
                    "action": "triggered",
                    "handlers": list(alert.get("handlers") or []),
                    "noData": no_data,
                },
            }
        )
        self._enqueue(policy, alert, event, "triggered", evaluated_at, manual_only=False)
        return alert

    def _recover_alert(self, policy: dict, alert: dict, value: float, evaluated_at: datetime) -> dict:
        stamp = fmt_dt(evaluated_at)
        alert["status"] = "recovered"
        alert["currentValue"] = value
        alert["operator"] = SYSTEM_OPERATOR
        alert["endedAt"] = stamp
        alert["lastEventAt"] = stamp
        alert["lastNotifiedAt"] = stamp
        saved = self.alerts.save_alert(alert)
        event = self.alerts.add_event(
            {
                "eventKey": f"{saved['id']}:recovered:{uuid4().hex}",
                "alertId": saved["id"],
                "action": "recovered",
                "occurredAt": stamp,
                "severity": saved.get("severity") or "",
                "value": value,
                "organizations": list(saved.get("organizations") or []),
                "content": {"actor": SYSTEM_OPERATOR, "action": "recovered", "handlers": list(saved.get("handlers") or [])},
            }
        )
        self._enqueue(policy, saved, event, "recovered", evaluated_at, manual_only=False)
        return saved

    def _maybe_renotify(self, policy: dict, alert: dict, evaluated_at: datetime) -> str:
        last = parse_dt(alert.get("lastNotifiedAt"))
        if not should_renotify(last, policy.get("renotifyMinutes"), evaluated_at):
            return "none"
        if not any(_is_manual_channel(target) for target in policy.get("notificationTargets") or []):
            return "none"
        alert["renotifyCount"] = int(alert.get("renotifyCount") or 0) + 1
        alert["lastNotifiedAt"] = fmt_dt(evaluated_at)
        saved = self.alerts.save_alert(alert)
        self._enqueue(policy, saved, None, "renotify", evaluated_at, manual_only=True)
        return "renotified"

    def _enqueue(self, policy: dict, alert: dict, event: dict | None, action: str, evaluated_at: datetime, *, manual_only: bool = False, copy_only: bool = False) -> None:
        targets = list(policy.get("notificationTargets") or [])
        if not targets:
            return
        view = {**alert, "metricValue": alert.get("currentValue")}
        title, body = render_message(policy, view, action, evaluated_at)
        severity = alert.get("severity") or policy.get("severity") or "warning"
        for target in targets:
            if manual_only and not _is_manual_channel(target):
                continue
            if copy_only and not _is_alert_center_copy(target):
                continue
            channel_id = target.get("channelId")
            if manual_only:
                key = f"{alert['id']}:renotify:{alert.get('renotifyCount')}:channel:{channel_id}"
                event_id = None
                event_key = key
            else:
                event_key = event["eventKey"]
                key = f"{event_key}:channel:{channel_id}"
                event_id = event["id"]
            recipients = [] if not _is_manual_channel(target) else [str(item) for item in target.get("recipients") or []]
            payload = {
                "event_key": event_key,
                "external_id": str(alert["id"]),
                "action": _COPY_ACTION.get(action, action),
                "severity": severity,
                "level": LEVEL_TO_ALERT_CENTER.get(severity, "3"),
                "title": title,
                "description": body,
                "value": alert.get("currentValue"),
                "start_time": _unix_seconds(alert.get("startedAt")),
                "resource_id": alert.get("application") or "",
                "resource_type": "rum_application",
                "resource_name": alert.get("application") or "",
                "organizations": list(alert.get("organizations") or []),
                "pusher": "lite-rum",
                "rule_id": policy.get("id") or "",
                "item": policy.get("metric") or "",
                "alert_link": f"/rum/alert-events?event={alert['id']}",
            }
            if action in {"recovered", "closed"}:
                payload["end_time"] = _unix_seconds(evaluated_at)
            self.alerts.add_delivery(
                {
                    "deliveryKey": key,
                    "eventId": event_id,
                    "alertId": alert["id"],
                    "channelId": int(channel_id),
                    "channelName": target.get("channelName") or "",
                    "channelType": target.get("channelType") or "",
                    "deliveryMode": target.get("deliveryMode") or "message",
                    "recipients": recipients,
                    "title": title,
                    "body": body,
                    "payload": payload,
                    "createdAt": fmt_dt(evaluated_at),
                }
            )


def _opened_for_no_data(alert: dict) -> bool:
    return bool(alert.get("noData")) or alert.get("currentValue") is None


def _mark_delivery_failed(delivery: dict, result: dict, now: datetime) -> None:
    code = str(result.get("code") or "delivery_failed")
    delivery["attempts"] = int(delivery.get("attempts") or 0) + 1
    delivery["claimedAt"] = None
    delivery["lastErrorCode"] = code[:128]
    delivery["lastErrorMessage"] = str(result.get("message") or "")[:512]
    terminal = (not result.get("retryable", True)) or code in TERMINAL_DELIVERY_CODES or delivery["attempts"] >= MAX_DELIVERY_ATTEMPTS
    if terminal:
        delivery["status"] = "failed"
        delivery["nextRetryAt"] = None
        delivery["failedAt"] = fmt_dt(now)
        return
    delay = min(300, 2 ** min(delivery["attempts"], MAX_DELIVERY_ATTEMPTS))
    delivery["nextRetryAt"] = fmt_dt(now + timedelta(seconds=delay))
    delivery["status"] = "pending"


def _log_delivery_exception(delivery_id: str, exc: BaseException) -> None:
    proxy = RuntimeError("notification dispatch failed")
    proxy.__traceback__ = exc.__traceback__
    logger.error(
        "rum alert delivery traceback delivery_id=%s failed_stage=%s error_type=%s",
        delivery_id,
        "dispatch",
        type(exc).__name__,
        exc_info=(RuntimeError, proxy, exc.__traceback__),
    )
