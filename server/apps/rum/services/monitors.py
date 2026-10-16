from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from apps.core.utils.user_display import build_user_display_map, format_user_identifiers
from apps.rum.services.alert_runtime import RumAlertRuntime
from apps.rum.services.alert_store import (  # noqa: F401
    MemoryEventStore,
    MemoryPolicyStore,
    get_event_store,
    get_policy_store,
    org_ids,
    parse_dt,
)
from apps.rum.services.analytics import Analytics, get_analytics
from apps.rum.services.control import ControlError, ControlPlane, get_control_plane
from apps.rum.services.settings import load_rum_settings
from apps.rum.services.validation import ValidationError, valid_application

_ALLOWED_METRICS = {
    "error_rate",
    "lcp_p75",
    "inp_p75",
    "fcp_p75",
    "ttfb_p75",
    "cls_p75",
    "session_count",
}
_ALLOWED_COMPARATORS = {">", ">=", "<", "<="}
_ALLOWED_SEVERITIES = {"info", "warning", "critical"}
_ALLOWED_WINDOWS = {5, 15, 60}
_DELIVERY_MODES = {"message", "alert_event_copy"}
_RECIPIENT_MODES = {"none", "system_user", "free_text"}


def normalize_targets(raw: Any, handlers: list) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("notificationTargets must be an array")
    out: list[dict] = []
    seen: set[int] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValidationError("notificationTargets must be objects")
        try:
            channel_id = int(item.get("channelId"))
        except (TypeError, ValueError) as exc:
            raise ValidationError("invalid channelId") from exc
        if channel_id <= 0 or channel_id in seen:
            raise ValidationError("invalid channelId")
        seen.add(channel_id)
        delivery_mode = str(item.get("deliveryMode") or "message")
        recipient_mode = str(item.get("recipientMode") or "none")
        if delivery_mode not in _DELIVERY_MODES or recipient_mode not in _RECIPIENT_MODES:
            raise ValidationError("invalid notification target")
        if delivery_mode == "alert_event_copy" or recipient_mode == "none":
            recipients: list[str] = []
        elif "recipients" in item:
            recipients = [str(value).strip() for value in item.get("recipients") or [] if str(value).strip()]
        else:
            recipients = [str(value) for value in handlers]
        out.append(
            {
                "channelId": channel_id,
                "channelName": str(item.get("channelName") or "")[:100],
                "channelType": str(item.get("channelType") or "")[:30],
                "deliveryMode": delivery_mode,
                "recipientMode": recipient_mode,
                "recipients": recipients,
            }
        )
    return out


def normalize_alert_policy(body: dict, *, partial: bool = False) -> dict:
    name = (body.get("name") or "").strip()
    application = (body.get("application") or "").strip()
    metric = (body.get("metric") or "").strip()
    severity = (body.get("severity") or "").strip() or "warning"
    comparator = (body.get("comparator") or "").strip() or ">="
    warn = float(body.get("warnThreshold") if body.get("warnThreshold") is not None else 0)
    critical = float(body.get("criticalThreshold") if body.get("criticalThreshold") is not None else 0)
    for_duration = int(body.get("forDurationSec") if body.get("forDurationSec") is not None else 300)
    window = int(body.get("evaluationWindowMinutes") if body.get("evaluationWindowMinutes") is not None else 15)
    no_data_after = int(body.get("noDataAfter") if body.get("noDataAfter") is not None else 3)
    enabled = bool(body.get("enabled") if body.get("enabled") is not None else True)
    renotify = body.get("renotifyMinutes")
    if renotify is not None and renotify != "":
        renotify = int(renotify)
    else:
        renotify = None
    organizations = org_ids(body.get("organizations"))
    handlers = body.get("handlers") or []
    if not isinstance(handlers, list):
        raise ValidationError("handlers must be an array")

    if not name or len(name) > 120 or not application:
        raise ValidationError("name and application are required")
    if not organizations:
        raise ValidationError("organizations are required")
    if not valid_application(application):
        raise ValidationError("invalid application")
    if metric not in _ALLOWED_METRICS:
        raise ValidationError("invalid metric")
    if severity not in _ALLOWED_SEVERITIES:
        raise ValidationError("invalid severity")
    if comparator not in _ALLOWED_COMPARATORS:
        raise ValidationError("invalid comparator")
    if window not in _ALLOWED_WINDOWS:
        raise ValidationError("invalid evaluationWindowMinutes")
    if for_duration < 0 or for_duration > 86400:
        raise ValidationError("invalid forDurationSec")
    if no_data_after < 0 or no_data_after > 1440:
        raise ValidationError("invalid noDataAfter")
    if renotify is not None and renotify < 0:
        raise ValidationError("invalid renotifyMinutes")
    if metric == "error_rate":
        if warn < 0 or critical <= 0 or warn > 1 or critical > 1:
            raise ValidationError("invalid error_rate thresholds")
    elif metric == "cls_p75":
        if warn < 0 or critical <= 0 or warn > 10 or critical > 10:
            raise ValidationError("invalid cls_p75 thresholds")
    else:
        if warn < 0 or critical <= 0:
            raise ValidationError("invalid thresholds")
    if comparator in {">", ">="}:
        if warn > 0 and warn > critical:
            raise ValidationError("warnThreshold must not exceed criticalThreshold")
    else:
        if warn > 0 and warn < critical:
            raise ValidationError("warnThreshold must not be below criticalThreshold")

    result = {
        "name": name,
        "application": application,
        "organizations": organizations,
        "metric": metric,
        "severity": severity,
        "comparator": comparator,
        "warnThreshold": warn,
        "criticalThreshold": critical,
        "evaluationWindowMinutes": window,
        "forDurationSec": for_duration,
        "noDataAfter": no_data_after,
        "renotifyMinutes": renotify,
        "handlers": handlers,
        "enabled": enabled,
    }
    if "notificationTargets" in body or not partial:
        result["notificationTargets"] = normalize_targets(body.get("notificationTargets"), handlers)
    return result


def _require_assignable(organizations: list[int], assignable_orgs: set[int]) -> None:
    if not set(organizations).issubset(set(assignable_orgs)):
        raise ControlError("forbidden", "organization is not assignable")


class MonitorsService:
    def __init__(
        self,
        control: ControlPlane | None = None,
        analytics: Analytics | None = None,
        policies=None,
        events=None,
        runtime: RumAlertRuntime | None = None,
        users=None,
    ):
        self.users = users
        self.control = control or get_control_plane()
        self.analytics = analytics or get_analytics()
        self.policies = policies or get_policy_store()
        self.events = events or get_event_store()
        settings = load_rum_settings()
        self.runtime = runtime or RumAlertRuntime(
            policies=self.policies,
            alerts=self.events,
            analytics=self.analytics,
            tenant_id=settings.tenant_id,
        )

    def _require_application(self, application: str) -> None:
        from apps.rum.models import RumApplication

        if not RumApplication.objects.filter(name=application, enabled=True).exists():
            raise ControlError("not_found", "application not found")

    def list_monitors(self, *, visible_orgs: set[int]) -> list[dict]:
        firing = self.events.active_policy_ids()
        policies = self.policies.list(visible_orgs)
        user_map = build_user_display_map([handler for item in policies for handler in (item.get("handlers") or [])])
        views = []
        for item in policies:
            view = _as_monitor_view(item, item["id"] in firing)
            view["handlersDisplay"] = format_user_identifiers(item.get("handlers") or [], user_map)
            views.append(view)
        return views

    def create_monitor(self, actor: str, body: dict, *, assignable_orgs: set[int]) -> dict:
        normalized = normalize_alert_policy(body)
        _require_assignable(normalized["organizations"], assignable_orgs)
        self._require_application(normalized["application"])
        normalized["enabled"] = True
        normalized.setdefault("notificationTargets", [])
        normalized.setdefault("handlers", [])
        saved = self.policies.save(normalized)
        return _as_monitor_view(saved, False)

    def update_monitor(self, actor: str, policy_id: str, body: dict, *, assignable_orgs: set[int], visible_orgs: set[int]) -> dict:
        existing = self.policies.get(policy_id, visible_orgs)
        if existing is None:
            raise ControlError("not_found", "monitor not found")
        merged_body = {**existing, **body}
        if "notificationTargets" not in body:
            merged_body["notificationTargets"] = existing.get("notificationTargets") or []
        normalized = normalize_alert_policy(merged_body)
        _require_assignable(normalized["organizations"], assignable_orgs)
        self._require_application(normalized["application"])
        if set(normalized["organizations"]) != set(org_ids(existing.get("organizations"))):
            _drop_out_of_scope(normalized)
        merged = {**existing, **normalized, "id": policy_id}
        was_enabled = bool(existing.get("enabled"))
        saved = self.policies.save(merged)
        if was_enabled and not saved.get("enabled"):
            self.runtime.close_active(saved)
        firing = self.events.active_for_policy(policy_id) is not None
        return _as_monitor_view(self.policies.get(policy_id) or saved, firing)

    def delete_monitor(self, policy_id: str, *, visible_orgs: set[int]) -> None:
        existing = self.policies.get(policy_id, visible_orgs)
        if existing is None:
            raise ControlError("not_found", "monitor not found")
        self.runtime.close_active(existing)
        self.policies.delete(policy_id)

    def list_alert_events(self, params: dict[str, Any], *, visible_orgs: set[int]) -> dict:
        page = int(params.get("page") or 1)
        limit = int(params.get("limit") or 15)
        if page < 1:
            page = 1
        if limit <= 0:
            limit = 15
        if limit > 200:
            limit = 200
        status_group = str(params.get("status") or params.get("status_group") or "")
        application = str(params.get("application") or "").strip()
        keyword = str(params.get("keyword") or params.get("q") or "").strip()
        handler = str(params.get("handler") or "").strip()
        items, total = self.events.list_alerts(
            page,
            limit,
            visible_orgs=visible_orgs,
            status_group=status_group,
            application=application,
            keyword=keyword,
            handler=handler,
        )
        user_map = build_user_display_map([handler for item in items for handler in (item.get("handlers") or [])])
        for item in items:
            item["handlersDisplay"] = format_user_identifiers(item.get("handlers") or [], user_map)
            deliveries = self.events.list_deliveries(item["id"])
            item["notification"] = {
                "pending": sum(1 for row in deliveries if row.get("status") == "pending"),
                "delivered": sum(1 for row in deliveries if row.get("status") == "delivered"),
                "failed": sum(1 for row in deliveries if row.get("status") == "failed"),
            }
        return {"items": items, "total": total, "page": page, "limit": limit}

    def claim_alert(self, alert_id: str, actor, *, visible_orgs: set[int]) -> dict:
        return self._disposition().claim(alert_id, actor, visible_orgs=visible_orgs)

    def assign_alert(self, alert_id: str, actor, handlers, *, visible_orgs: set[int]) -> dict:
        return self._disposition().assign(alert_id, actor, handlers, visible_orgs=visible_orgs)

    def reassign_alert(self, alert_id: str, actor, handlers, *, visible_orgs: set[int]) -> dict:
        return self._disposition().reassign(alert_id, actor, handlers, visible_orgs=visible_orgs)

    def close_alert(self, alert_id: str, actor, *, visible_orgs: set[int]) -> dict:
        return self._disposition().close(alert_id, actor, visible_orgs=visible_orgs)

    def retry_alert_delivery(self, alert_id: str, delivery_id: str, actor, *, visible_orgs: set[int]) -> dict:
        return self._disposition().retry_delivery(alert_id, delivery_id, actor, visible_orgs=visible_orgs)

    def _disposition(self):
        from apps.rum.services.disposition import AlertDisposition

        return AlertDisposition(policies=self.policies, alerts=self.events, users=self.users)

    def get_alert_event(self, alert_id: str, *, visible_orgs: set[int]) -> dict:
        alert = self.events.get_alert(alert_id, visible_orgs)
        if alert is None:
            raise ControlError("not_found", "alert event not found")
        alert["handlersDisplay"] = format_user_identifiers(alert.get("handlers") or [])
        return {
            "alert": alert,
            "events": self.events.list_events(alert_id),
            "deliveries": self.events.list_deliveries(alert_id),
            "trend": self._trend(alert),
        }

    def _trend(self, alert: dict) -> list[dict]:
        if not self.analytics.available() or not alert.get("application") or not alert.get("metric"):
            return []
        now = datetime.now(timezone.utc)
        end = now
        start = now - timedelta(hours=6)
        fired = parse_dt(alert.get("startedAt"))
        if fired is not None:
            start = min(start, fired - timedelta(hours=1))
            ended = parse_dt(alert.get("endedAt"))
            if ended is not None:
                end = max(end, ended + timedelta(minutes=15))
        week_ago = now - timedelta(days=7)
        if start < week_ago:
            start = week_ago
        if end <= start:
            end = start + timedelta(hours=1)
        return self.analytics.metric_series(
            load_rum_settings().tenant_id,
            {
                "application": alert["application"],
                "metric": alert["metric"],
                "from": start,
                "to": end,
                "points": 24,
            },
        )


def _drop_out_of_scope(policy: dict) -> None:
    from apps.core.utils.user_lookup import find_user

    allowed = set(org_ids(policy.get("organizations")))
    kept = []
    for handler in policy.get("handlers") or []:
        user = find_user(handler)
        if user is None or getattr(user, "disabled", False):
            continue
        if _user_in_orgs(user, allowed):
            kept.append(user.id)
    policy["handlers"] = kept
    for target in policy.get("notificationTargets") or []:
        if target.get("recipientMode") != "system_user":
            continue
        recipients = []
        for recipient in target.get("recipients") or []:
            user = find_user(recipient)
            if user is None or getattr(user, "disabled", False):
                continue
            if _user_in_orgs(user, allowed):
                recipients.append(str(user.id))
        target["recipients"] = recipients


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


def _as_monitor_view(policy: dict, firing: bool) -> dict:
    return {
        **policy,
        "firing": firing,
        "organizations": list(policy.get("organizations") or []),
        "notificationTargets": list(policy.get("notificationTargets") or []),
        "handlers": list(policy.get("handlers") or []),
    }
