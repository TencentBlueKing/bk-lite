from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from apps.rum.services.alert_store import fmt_dt
from apps.rum.services.control import ControlError
from apps.rum.services.notify import render_message


def _actor_id(actor) -> str:
    value = getattr(actor, "id", None)
    if value in (None, ""):
        value = getattr(actor, "pk", None)
    return "" if value in (None, "") else str(value)


def _actor_matches(handlers, actor) -> bool:
    candidates = {_actor_id(actor), str(getattr(actor, "username", "") or "")}
    candidates.discard("")
    return any(str(item) in candidates for item in handlers or [])


def _person_channel(target: dict) -> bool:
    return target.get("deliveryMode") == "message" and target.get("recipientMode") in {"system_user", "free_text"}


class AlertDisposition:
    def __init__(self, *, policies, alerts, users=None, now=None):
        self.policies = policies
        self.alerts = alerts
        self.users = users or _default_users
        self.now = now or (lambda: datetime.now(timezone.utc))

    def claim(self, alert_id: str, actor, *, visible_orgs: set[int] | None = None) -> dict:
        return self._mutate(alert_id, actor, visible_orgs=visible_orgs, action="claimed", handlers=[_actor_id(actor)])

    def assign(self, alert_id: str, actor, handlers, *, visible_orgs: set[int] | None = None) -> dict:
        return self._mutate(alert_id, actor, visible_orgs=visible_orgs, action="assigned", handlers=handlers)

    def reassign(self, alert_id: str, actor, handlers, *, visible_orgs: set[int] | None = None) -> dict:
        return self._mutate(alert_id, actor, visible_orgs=visible_orgs, action="reassigned", handlers=handlers)

    def close(self, alert_id: str, actor, *, visible_orgs: set[int] | None = None) -> dict:
        return self._mutate(alert_id, actor, visible_orgs=visible_orgs, action="closed", handlers=None)

    def retry_delivery(self, alert_id: str, delivery_id: str, actor, *, visible_orgs: set[int] | None = None) -> dict:
        with self.alerts.locked_alert(alert_id, visible_orgs) as alert:
            if alert is None:
                raise ControlError("not_found", "alert event not found")
            delivery = self.alerts.get_delivery(delivery_id)
            if delivery is None or delivery.get("alertId") != alert_id:
                raise ControlError("not_found", "delivery not found")
            if delivery.get("status") != "failed":
                raise ControlError("conflict", "只有终止失败的投递可以重投")
            self.alerts.add_retry(
                {
                    "deliveryId": delivery_id,
                    "requestedBy": getattr(actor, "username", None) or _actor_id(actor),
                    "previousAttempts": int(delivery.get("attempts") or 0),
                    "previousErrorCode": delivery.get("lastErrorCode") or "",
                    "previousErrorMessage": delivery.get("lastErrorMessage") or "",
                }
            )
            delivery["status"] = "pending"
            delivery["attempts"] = 0
            delivery["nextRetryAt"] = None
            delivery["claimedAt"] = None
            delivery["failedAt"] = None
            return self.alerts.save_delivery(delivery)

    def _mutate(self, alert_id: str, actor, *, visible_orgs, action: str, handlers) -> dict:
        with self.alerts.locked_alert(alert_id, visible_orgs) as alert:
            return self._mutate_locked(alert, actor, action=action, handlers=handlers)

    def _mutate_locked(self, alert: dict | None, actor, *, action: str, handlers) -> dict:
        if alert is None:
            raise ControlError("not_found", "alert event not found")
        if alert.get("status") != "active":
            raise ControlError("conflict", "只有进行中的告警可以处置")
        current = list(alert.get("handlers") or [])
        if action in {"claimed", "assigned"}:
            if current:
                raise ControlError("conflict", "告警已有处理人")
            actor_id = getattr(actor, "id", None)
            next_handlers = [actor_id if actor_id not in (None, "") else _actor_id(actor)] if action == "claimed" else self._normalize(handlers, alert.get("organizations") or [])
        elif action == "reassigned":
            if not current:
                raise ControlError("conflict", "告警没有处理人")
            if not _actor_matches(current, actor):
                raise ControlError("conflict", "只有当前处理人可以转派")
            next_handlers = self._normalize(handlers, alert.get("organizations") or [])
        else:
            if current and not _actor_matches(current, actor):
                raise ControlError("conflict", "只有当前处理人可以关闭")
            next_handlers = current
        now = self.now().astimezone(timezone.utc)
        stamp = fmt_dt(now)
        if action == "closed":
            alert["status"] = "closed"
            alert["endedAt"] = stamp
            alert["operator"] = getattr(actor, "username", None) or _actor_id(actor)
        else:
            alert["handlers"] = next_handlers
            alert["operator"] = getattr(actor, "username", None) or _actor_id(actor)
        alert["lastEventAt"] = stamp
        saved = self.alerts.save_alert(alert)
        self.alerts.add_event(
            {
                "eventKey": f"{saved['id']}:{action}:{uuid4().hex}",
                "alertId": saved["id"],
                "action": action,
                "occurredAt": stamp,
                "severity": saved.get("severity") or "",
                "value": saved.get("currentValue"),
                "organizations": list(saved.get("organizations") or []),
                "content": {"actor": alert["operator"], "action": action, "handlers": list(saved.get("handlers") or [])},
            }
        )
        if action in {"assigned", "reassigned"}:
            self._notify(saved, action, now)
        return saved

    def _normalize(self, handlers, organizations) -> list:
        if not handlers:
            raise ControlError("invalid_argument", "至少指定一名处理人")
        allowed = {int(item) for item in organizations or []}
        resolved = []
        seen = set()
        for raw in handlers:
            user = self.users(raw)
            if user is None:
                raise ControlError("invalid_argument", "处理人不存在")
            if getattr(user, "disabled", False):
                raise ControlError("invalid_argument", "处理人已禁用")
            if not _user_in_orgs(user, allowed):
                raise ControlError("invalid_argument", "处理人不属于告警组织")
            if user.id in seen:
                continue
            seen.add(user.id)
            resolved.append(user.id)
        if not resolved:
            raise ControlError("invalid_argument", "至少指定一名处理人")
        return resolved

    def _notify(self, alert: dict, action: str, now: datetime) -> None:
        policy = self.policies.get(alert.get("policyId") or "")
        if policy is None:
            return
        targets = [target for target in policy.get("notificationTargets") or [] if _person_channel(target)]
        if not targets:
            return
        view = {**alert, "metricValue": alert.get("currentValue")}
        title, body = render_message(policy, view, action, now)
        handlers = [str(item) for item in alert.get("handlers") or []]
        for target in targets:
            recipients = handlers if target.get("recipientMode") == "system_user" else [str(item) for item in target.get("recipients") or []]
            if not recipients:
                continue
            channel_id = target.get("channelId")
            self.alerts.add_delivery(
                {
                    "deliveryKey": f"{alert['id']}:{action}:{uuid4().hex}:channel:{channel_id}",
                    "eventId": None,
                    "alertId": alert["id"],
                    "channelId": int(channel_id),
                    "channelName": target.get("channelName") or "",
                    "channelType": target.get("channelType") or "",
                    "deliveryMode": "message",
                    "recipients": recipients,
                    "title": title,
                    "body": body,
                    "payload": {"action": action, "pusher": "lite-rum", "organizations": list(alert.get("organizations") or [])},
                    "createdAt": fmt_dt(now),
                }
            )


def _default_users(identifier):
    from apps.core.utils.user_lookup import find_user

    return find_user(identifier)


def _user_in_orgs(user, allowed: set[int]) -> bool:
    if not allowed:
        return False
    for item in getattr(user, "group_list", None) or []:
        group_id = item.get("id") if isinstance(item, dict) else item
        try:
            if int(group_id) in allowed:
                return True
        except (TypeError, ValueError):
            continue
    return False


def actor_from_user(user) -> SimpleNamespace:
    return SimpleNamespace(
        id=getattr(user, "id", None) or getattr(user, "pk", None),
        username=getattr(user, "username", "") or "",
        disabled=bool(getattr(user, "disabled", False)),
        group_list=getattr(user, "group_list", None) or [],
    )
