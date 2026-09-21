from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from apps.rum.constants import SUBJECT_APPLICATION_LIST
from apps.rum.services.analytics import Analytics, get_analytics
from apps.rum.services.control import ControlError, ControlPlane, control_unavailable, get_control_plane
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


def normalize_channels(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, list):
        raise ValidationError("notifyChannels must be an array")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def normalize_alert_policy(body: dict, *, partial: bool = False) -> dict:
    name = (body.get("name") or "").strip()
    application = (body.get("application") or "").strip()
    metric = (body.get("metric") or "").strip()
    severity = (body.get("severity") or "").strip() or "warning"
    comparator = (body.get("comparator") or "").strip() or ">="
    warn = float(body.get("warnThreshold") if body.get("warnThreshold") is not None else 0)
    critical = float(body.get("criticalThreshold") if body.get("criticalThreshold") is not None else 0)
    for_duration = int(body.get("forDurationSec") if body.get("forDurationSec") is not None else 0)
    no_data = bool(body.get("noData") or False)
    enabled = bool(body.get("enabled") if body.get("enabled") is not None else True)
    renotify = body.get("renotifyMinutes")
    if renotify is not None and renotify != "":
        renotify = int(renotify)
    else:
        renotify = None

    if not name or len(name) > 120 or not application:
        raise ValidationError("name and application are required")
    if not valid_application(application):
        raise ValidationError("invalid application")
    if metric not in _ALLOWED_METRICS:
        raise ValidationError("invalid metric")
    if severity not in _ALLOWED_SEVERITIES:
        raise ValidationError("invalid severity")
    if comparator not in _ALLOWED_COMPARATORS:
        raise ValidationError("invalid comparator")
    if for_duration < 0 or for_duration > 86400:
        raise ValidationError("invalid forDurationSec")
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

    channels = normalize_channels(body.get("notifyChannels")) if "notifyChannels" in body or not partial else None
    result = {
        "name": name,
        "application": application,
        "metric": metric,
        "severity": severity,
        "comparator": comparator,
        "warnThreshold": warn,
        "criticalThreshold": critical,
        "forDurationSec": for_duration,
        "noData": no_data,
        "renotifyMinutes": renotify,
        "enabled": enabled,
        "signal": (body.get("signal") or "").strip(),
    }
    if channels is not None:
        result["notifyChannels"] = channels
    return result


class PolicyStore(Protocol):
    def list(self) -> list[dict]:
        ...

    def list_enabled(self) -> list[dict]:
        ...

    def get(self, policy_id: str) -> dict | None:
        ...

    def save(self, policy: dict) -> dict:
        ...

    def delete(self, policy_id: str) -> None:
        ...


class EventStore(Protocol):
    def list_page(self, page: int, limit: int) -> tuple[list[dict], int]:
        ...

    def list_recent(self, limit: int = 500) -> list[dict]:
        ...

    def get(self, event_id: str) -> dict | None:
        ...

    def latest_open(self, policy_id: str) -> dict | None:
        ...

    def create(self, event: dict) -> dict:
        ...

    def save(self, event: dict) -> dict:
        ...


class MemoryPolicyStore:
    def __init__(self):
        self._items: dict[str, dict] = {}
        self._seq = 0

    def list(self) -> list[dict]:
        return [dict(item) for item in self._items.values()]

    def list_enabled(self) -> list[dict]:
        return [dict(item) for item in self._items.values() if item.get("enabled")]

    def get(self, policy_id: str) -> dict | None:
        item = self._items.get(policy_id)
        return dict(item) if item else None

    def save(self, policy: dict) -> dict:
        item = dict(policy)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if not item.get("id"):
            self._seq += 1
            item["id"] = f"policy-{self._seq}"
            item["createdAt"] = now
        item["updatedAt"] = now
        item.setdefault("notifyChannels", [])
        self._items[item["id"]] = item
        return dict(item)

    def delete(self, policy_id: str) -> None:
        if policy_id not in self._items:
            raise ControlError("not_found", "monitor not found")
        del self._items[policy_id]


class MemoryEventStore:
    def __init__(self):
        self._items: dict[str, dict] = {}
        self._seq = 0

    def list_page(self, page: int, limit: int) -> tuple[list[dict], int]:
        rows = sorted(self._items.values(), key=lambda row: row.get("createdAt") or "", reverse=True)
        total = len(rows)
        start = (page - 1) * limit
        return [dict(row) for row in rows[start : start + limit]], total

    def list_recent(self, limit: int = 500) -> list[dict]:
        rows = sorted(self._items.values(), key=lambda row: row.get("createdAt") or "", reverse=True)
        return [dict(row) for row in rows[:limit]]

    def get(self, event_id: str) -> dict | None:
        item = self._items.get(event_id)
        return dict(item) if item else None

    def latest_open(self, policy_id: str) -> dict | None:
        open_events = [item for item in self._items.values() if item.get("policyId") == policy_id and item.get("status") == "firing"]
        if not open_events:
            return None
        open_events.sort(key=lambda row: row.get("createdAt") or "", reverse=True)
        return dict(open_events[0])

    def create(self, event: dict) -> dict:
        self._seq += 1
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        item = {
            **event,
            "id": event.get("id") or f"event-{self._seq}",
            "createdAt": event.get("createdAt") or now,
        }
        self._items[item["id"]] = item
        return dict(item)

    def save(self, event: dict) -> dict:
        item = dict(event)
        if not item.get("id") or item["id"] not in self._items:
            return self.create(item)
        self._items[item["id"]] = item
        return dict(item)


_policy_store: PolicyStore | None = None
_event_store: EventStore | None = None


def get_policy_store() -> PolicyStore:
    global _policy_store
    if _policy_store is None:
        _policy_store = DjangoPolicyStore()
    return _policy_store


def get_event_store() -> EventStore:
    global _event_store
    if _event_store is None:
        _event_store = DjangoEventStore()
    return _event_store


def set_policy_store(store: PolicyStore | None) -> None:
    """Test seam."""
    global _policy_store
    _policy_store = store


def set_event_store(store: EventStore | None) -> None:
    """Test seam."""
    global _event_store
    _event_store = store


class DjangoPolicyStore:
    def list(self) -> list[dict]:
        from apps.rum.models import RumAlertPolicy

        return [_serialize_policy(item) for item in RumAlertPolicy.objects.all().order_by("-updated_at")]

    def list_enabled(self) -> list[dict]:
        from apps.rum.models import RumAlertPolicy

        return [_serialize_policy(item) for item in RumAlertPolicy.objects.filter(enabled=True).order_by("-updated_at")]

    def get(self, policy_id: str) -> dict | None:
        from apps.rum.models import RumAlertPolicy

        try:
            return _serialize_policy(RumAlertPolicy.objects.get(pk=policy_id))
        except RumAlertPolicy.DoesNotExist:
            return None

    def save(self, policy: dict) -> dict:
        from apps.rum.models import RumAlertPolicy

        if policy.get("id"):
            try:
                item = RumAlertPolicy.objects.get(pk=policy["id"])
            except RumAlertPolicy.DoesNotExist as exc:
                raise ControlError("not_found", "monitor not found") from exc
        else:
            item = RumAlertPolicy()
        item.name = policy["name"]
        item.application = policy["application"]
        item.metric = policy["metric"]
        item.severity = policy["severity"]
        item.comparator = policy["comparator"]
        item.warn_threshold = policy["warnThreshold"]
        item.critical_threshold = policy["criticalThreshold"]
        item.for_duration_sec = policy["forDurationSec"]
        item.no_data = policy["noData"]
        item.renotify_minutes = policy.get("renotifyMinutes")
        item.enabled = policy["enabled"]
        item.signal = policy.get("signal") or ""
        if "notifyChannels" in policy:
            item.notify_channels = list(policy["notifyChannels"] or [])
        item.pending_since = _parse_dt(policy.get("pendingSince"))
        item.recovering_since = _parse_dt(policy.get("recoveringSince"))
        item.save()
        return _serialize_policy(item)

    def delete(self, policy_id: str) -> None:
        from apps.rum.models import RumAlertPolicy

        deleted, _ = RumAlertPolicy.objects.filter(pk=policy_id).delete()
        if not deleted:
            raise ControlError("not_found", "monitor not found")


class DjangoEventStore:
    def list_page(self, page: int, limit: int) -> tuple[list[dict], int]:
        from apps.rum.models import RumAlertEvent

        qs = RumAlertEvent.objects.all().order_by("-created_at")
        total = qs.count()
        start = (page - 1) * limit
        return [_serialize_event(item) for item in qs[start : start + limit]], total

    def list_recent(self, limit: int = 500) -> list[dict]:
        from apps.rum.models import RumAlertEvent

        return [_serialize_event(item) for item in RumAlertEvent.objects.all().order_by("-created_at")[:limit]]

    def get(self, event_id: str) -> dict | None:
        from apps.rum.models import RumAlertEvent

        try:
            return _serialize_event(RumAlertEvent.objects.get(pk=event_id))
        except RumAlertEvent.DoesNotExist:
            return None

    def latest_open(self, policy_id: str) -> dict | None:
        from apps.rum.models import RumAlertEvent

        item = RumAlertEvent.objects.filter(policy_id=policy_id, status="firing").order_by("-created_at").first()
        return _serialize_event(item) if item else None

    def create(self, event: dict) -> dict:
        from apps.rum.models import RumAlertEvent

        item = RumAlertEvent(
            policy_id=event["policyId"],
            status=event.get("status") or "firing",
            severity=event.get("severity") or "",
            metric_value=float(event.get("metricValue") or 0),
            message=event.get("message") or "",
            fired_at=_parse_dt(event.get("firedAt")),
            resolved_at=_parse_dt(event.get("resolvedAt")),
            last_notified_at=_parse_dt(event.get("lastNotifiedAt")),
        )
        if event.get("id"):
            item.id = event["id"]
        item.save()
        return _serialize_event(item)

    def save(self, event: dict) -> dict:
        from apps.rum.models import RumAlertEvent

        try:
            item = RumAlertEvent.objects.get(pk=event["id"])
        except RumAlertEvent.DoesNotExist:
            return self.create(event)
        item.status = event.get("status") or item.status
        item.severity = event.get("severity") or item.severity
        if event.get("metricValue") is not None:
            item.metric_value = float(event["metricValue"])
        if "message" in event:
            item.message = event["message"] or ""
        item.fired_at = _parse_dt(event.get("firedAt")) if "firedAt" in event else item.fired_at
        item.resolved_at = _parse_dt(event.get("resolvedAt")) if "resolvedAt" in event else item.resolved_at
        item.last_notified_at = _parse_dt(event.get("lastNotifiedAt")) if "lastNotifiedAt" in event else item.last_notified_at
        item.save()
        return _serialize_event(item)


def _parse_dt(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _fmt_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _serialize_policy(item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "application": item.application,
        "metric": item.metric,
        "severity": item.severity,
        "comparator": item.comparator,
        "warnThreshold": item.warn_threshold,
        "criticalThreshold": item.critical_threshold,
        "forDurationSec": item.for_duration_sec,
        "noData": item.no_data,
        "renotifyMinutes": item.renotify_minutes,
        "enabled": item.enabled,
        "signal": item.signal,
        "notifyChannels": list(item.notify_channels or []),
        "pendingSince": _fmt_dt(item.pending_since),
        "recoveringSince": _fmt_dt(item.recovering_since),
        "createdAt": _fmt_dt(item.created_at),
        "updatedAt": _fmt_dt(item.updated_at),
    }


def _serialize_event(item) -> dict:
    return {
        "id": item.id,
        "policyId": item.policy_id,
        "status": item.status,
        "severity": item.severity,
        "metricValue": item.metric_value,
        "message": item.message,
        "firedAt": _fmt_dt(item.fired_at),
        "resolvedAt": _fmt_dt(item.resolved_at),
        "lastNotifiedAt": _fmt_dt(item.last_notified_at),
        "createdAt": _fmt_dt(item.created_at),
    }


def _as_monitor_view(policy: dict, firing: bool) -> dict:
    return {**policy, "firing": firing, "notifyChannels": list(policy.get("notifyChannels") or [])}


class MonitorsService:
    def __init__(
        self,
        control: ControlPlane | None = None,
        analytics: Analytics | None = None,
        policies: PolicyStore | None = None,
        events: EventStore | None = None,
    ):
        self.control = control or get_control_plane()
        self.analytics = analytics or get_analytics()
        self.policies = policies or get_policy_store()
        self.events = events or get_event_store()

    def _list_enabled_apps(self, actor: str) -> tuple[list[str], str | None]:
        try:
            _, data = self.control.request(SUBJECT_APPLICATION_LIST, actor, {})
        except ControlError as exc:
            if control_unavailable(exc):
                return [], "control"
            raise
        registry = data if isinstance(data, list) else []
        return [item.get("application") for item in registry if item.get("application") and item.get("enabled", True)], None

    def _require_application(self, actor: str, application: str) -> None:
        enabled, reason = self._list_enabled_apps(actor)
        if reason == "control":
            raise ControlError("unavailable", "RUM controller is unavailable")
        if application not in enabled:
            raise ControlError("not_found", "application not found")

    def list_monitors(self) -> list[dict]:
        firing: set[str] = set()
        for event in self.events.list_recent(500):
            if event.get("status") == "firing" and event.get("policyId"):
                firing.add(event["policyId"])
        return [_as_monitor_view(item, item["id"] in firing) for item in self.policies.list()]

    def create_monitor(self, actor: str, body: dict) -> dict:
        normalized = normalize_alert_policy(body)
        self._require_application(actor, normalized["application"])
        normalized["enabled"] = True
        if "notifyChannels" not in normalized:
            normalized["notifyChannels"] = []
        saved = self.policies.save(normalized)
        return _as_monitor_view(saved, False)

    def update_monitor(self, actor: str, policy_id: str, body: dict) -> dict:
        existing = self.policies.get(policy_id)
        if existing is None:
            raise ControlError("not_found", "monitor not found")
        normalized = normalize_alert_policy({**existing, **body})
        self._require_application(actor, normalized["application"])
        if "notifyChannels" not in body:
            normalized["notifyChannels"] = list(existing.get("notifyChannels") or [])
        merged = {**existing, **normalized, "id": policy_id}
        if not merged.get("enabled"):
            merged["pendingSince"] = None
            merged["recoveringSince"] = None
        saved = self.policies.save(merged)
        if not saved.get("enabled"):
            open_event = self.events.latest_open(policy_id)
            if open_event is not None:
                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                open_event["status"] = "resolved"
                open_event["resolvedAt"] = now
                self.events.save(open_event)
        open_event = self.events.latest_open(policy_id)
        firing = open_event is not None and open_event.get("status") == "firing"
        return _as_monitor_view(saved, firing)

    def delete_monitor(self, policy_id: str) -> None:
        open_event = self.events.latest_open(policy_id)
        if open_event is not None:
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            open_event["status"] = "resolved"
            open_event["resolvedAt"] = now
            self.events.save(open_event)
        self.policies.delete(policy_id)

    def list_alert_events(self, params: dict[str, Any]) -> dict:
        page = int(params.get("page") or 1)
        limit = int(params.get("limit") or 15)
        if page < 1:
            page = 1
        if limit <= 0:
            limit = 15
        if limit > 200:
            limit = 200
        items, total = self.events.list_page(page, limit)
        return {"items": items, "total": total, "page": page, "limit": limit}

    def get_alert_event(self, event_id: str) -> dict:
        event = self.events.get(event_id)
        if event is None:
            raise ControlError("not_found", "alert event not found")
        policy = self.policies.get(event.get("policyId") or "") or {}
        timeline = []
        if event.get("firedAt"):
            timeline.append({"kind": "fired", "at": event["firedAt"], "note": "threshold breached"})
        if event.get("resolvedAt"):
            timeline.append({"kind": "resolved", "at": event["resolvedAt"], "note": "metric recovered"})
        trend: list[dict] = []
        if self.analytics.available() and policy.get("application") and policy.get("metric"):
            from apps.rum.services.settings import load_rum_settings

            now = datetime.now(timezone.utc)
            end = now
            # Sparse RUM traffic needs a wide window; a 15m pre-fire slice often paints
            # an all-zero flat sparkline that looks identical across alerts.
            start = now - timedelta(hours=6)
            if event.get("firedAt"):
                fired = _parse_dt(event["firedAt"])
                if fired is not None:
                    start = min(start, fired - timedelta(hours=1))
                    if event.get("resolvedAt"):
                        resolved = _parse_dt(event["resolvedAt"])
                        if resolved is not None:
                            end = max(end, resolved + timedelta(minutes=15))
            week_ago = now - timedelta(days=7)
            if start < week_ago:
                start = week_ago
            if end <= start:
                end = start + timedelta(hours=1)
            trend = self.analytics.metric_series(
                load_rum_settings().tenant_id,
                {
                    "application": policy["application"],
                    "metric": policy["metric"],
                    "from": start,
                    "to": end,
                    "points": 24,
                },
            )
        return {"event": event, "policy": policy, "trend": trend, "timeline": timeline}
