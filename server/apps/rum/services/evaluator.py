from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from apps.core.logger import rum_logger as logger
from apps.rum.services.alerteval import EVAL_FIRE, EVAL_RESOLVE, EvalState, advance, breached, should_renotify
from apps.rum.services.analytics import Analytics, get_analytics
from apps.rum.services.monitors import EventStore, MemoryEventStore, MemoryPolicyStore, PolicyStore
from apps.rum.services.notify import NOTIFY_FIRE, NOTIFY_RECOVER, NOTIFY_RENOTIFY, MemoryNotifier, Notifier, deliver_notify
from apps.rum.services.settings import load_rum_settings

DEFAULT_EVAL_WINDOW = timedelta(minutes=15)


class AlertEvaluator:
    def __init__(
        self,
        *,
        policies: PolicyStore | None = None,
        events: EventStore | None = None,
        analytics: Analytics | None = None,
        notifier: Notifier | None = None,
        now: Callable[[], datetime] | None = None,
        window: timedelta = DEFAULT_EVAL_WINDOW,
    ):
        self.policies = policies or MemoryPolicyStore()
        self.events = events or MemoryEventStore()
        self.analytics = analytics or get_analytics()
        self.notifier = notifier or MemoryNotifier()
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.window = window
        self.settings = load_rum_settings()

    def evaluate_all(self) -> dict:
        if not self.analytics.available():
            return {"skipped": True, "reason": "analytics", "evaluated": 0}
        policies = self.policies.list_enabled()
        end = self.now().astimezone(timezone.utc)
        start = end - self.window
        fired = resolved = renotified = 0
        for policy in policies:
            action = self.evaluate_policy(policy, start, end)
            if action == EVAL_FIRE:
                fired += 1
            elif action == EVAL_RESOLVE:
                resolved += 1
            elif action == "renotify":
                renotified += 1
        return {
            "skipped": False,
            "evaluated": len(policies),
            "fired": fired,
            "resolved": resolved,
            "renotified": renotified,
        }

    def evaluate_policy(self, policy: dict, start: datetime, end: datetime) -> str:
        try:
            value = self.analytics.monitor_metric(
                self.settings.tenant_id,
                {
                    "application": policy["application"],
                    "metric": policy["metric"],
                    "from": start,
                    "to": end,
                },
            )
        except Exception as exc:
            logger.warning(
                "rum alert metric read policy=%s metric=%s err=%s",
                policy.get("id"),
                policy.get("metric"),
                exc,
            )
            value = 0.0

        comparator = policy.get("comparator") or ">="
        level = breached(
            comparator,
            float(value),
            float(policy.get("warnThreshold") or 0),
            float(policy.get("criticalThreshold") or 0),
        )
        is_breached = level != ""
        if policy.get("noData") and float(value) <= 0:
            is_breached = True
            if not level:
                level = "critical"

        now = self.now().astimezone(timezone.utc)
        open_event = self.events.latest_open(policy["id"])
        state = EvalState(
            breaching_since=_parse_optional(policy.get("pendingSince")),
            recovering_since=_parse_optional(policy.get("recoveringSince")),
        )
        for_duration = timedelta(seconds=int(policy.get("forDurationSec") or 0))
        action = advance(state, is_breached, open_event is not None, for_duration, now)

        if action == EVAL_FIRE:
            severity = level or policy.get("severity") or "critical"
            message = f"{policy['application']} {policy['metric']}={value} breached threshold " f"{policy.get('criticalThreshold')}"
            if policy.get("noData") and float(value) <= 0:
                message = f"{policy['application']} {policy['metric']} reported no data " f"in the last {self.window}"
            now_iso = _fmt(now)
            event = self.events.create(
                {
                    "policyId": policy["id"],
                    "status": "firing",
                    "severity": severity,
                    "metricValue": float(value),
                    "message": message,
                    "firedAt": now_iso,
                    "lastNotifiedAt": now_iso,
                }
            )
            self._persist_state(policy, state)
            deliver_notify(self.notifier, policy, event, NOTIFY_FIRE, now)
            return EVAL_FIRE

        if action == EVAL_RESOLVE and open_event is not None:
            open_event["status"] = "resolved"
            open_event["resolvedAt"] = _fmt(now)
            open_event["metricValue"] = float(value)
            saved = self.events.save(open_event)
            self._persist_state(policy, state)
            deliver_notify(self.notifier, policy, saved, NOTIFY_RECOVER, now)
            return EVAL_RESOLVE

        self._persist_state(policy, state)
        if is_breached and open_event is not None and open_event.get("status") == "firing":
            if self._maybe_renotify(policy, open_event, float(value), now):
                return "renotify"
        return "none"

    def _maybe_renotify(self, policy: dict, open_event: dict, value: float, now: datetime) -> bool:
        last = _parse_optional(open_event.get("lastNotifiedAt"))
        if not should_renotify(last, policy.get("renotifyMinutes"), now):
            return False
        open_event["lastNotifiedAt"] = _fmt(now)
        open_event["metricValue"] = value
        saved = self.events.save(open_event)
        deliver_notify(self.notifier, policy, saved, NOTIFY_RENOTIFY, now)
        return True

    def _persist_state(self, policy: dict, state: EvalState) -> None:
        policy["pendingSince"] = _fmt(state.breaching_since) if state.breaching_since else None
        policy["recoveringSince"] = _fmt(state.recovering_since) if state.recovering_since else None
        self.policies.save(policy)


def _parse_optional(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _fmt(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
