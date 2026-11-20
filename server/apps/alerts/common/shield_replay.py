"""监控源屏蔽事件在窗口结束后的补准入。

只处理 lite-monitor 的 created 事件。恢复与否只看告警中心里已有的
recovery/closed，不回查监控。原事件保持 SHIELD，补一条新的 created 走现有入库。
"""

from django.utils import timezone

from apps.alerts.aggregation.recovery.match_key import build_recovery_match_key
from apps.alerts.constants.constants import AlertShieldMatchType, AlertStatus, EventAction, EventStatus
from apps.alerts.models.alert_operator import AlertShield
from apps.alerts.models.models import Alert, Event
from apps.alerts.notification_templates.timefmt import resolve_display_timezone
from apps.alerts.utils.monitor_source_rules import MonitorSourceRuleMatcher
from apps.alerts.utils.rule_catalog import model_fields
from apps.alerts.utils.time_range_checker import TimeRangeChecker
from apps.core.logger import alert_logger as logger

MONITOR_PUSH_SOURCE_ID = "lite-monitor"
BATCH_SIZE = 200
_REPLAY_PREFIX = "shield-replay:"


def replay_settled_monitor_shields():
    """了结或重放一批仍处于屏蔽状态的监控源事件。"""
    events = list(
        Event.objects.filter(
            push_source_id=MONITOR_PUSH_SOURCE_ID,
            status=EventStatus.SHIELD,
            action=EventAction.CREATED,
            shield_settled_at__isnull=True,
        )
        .select_related("source")
        .order_by("id")[:BATCH_SIZE]
    )
    shields = list(AlertShield.objects.filter(is_active=True))
    settled = 0
    replayed = 0
    for event in events:
        try:
            outcome = _replay_one(event, shields)
        except Exception as exc:
            logger.exception(
                "event=monitor_shield_replay_failed event_id=%s failed_stage=replay error_type=%s",
                event.event_id,
                type(exc).__name__,
            )
            continue
        if outcome == "settled":
            settled += 1
        elif outcome == "replayed":
            replayed += 1
    logger.info(
        "event=monitor_shield_replay_finished scanned=%s settled=%s replayed=%s",
        len(events),
        settled,
        replayed,
    )
    return {"scanned": len(events), "settled": settled, "replayed": replayed}


def _replay_one(event, shields):
    if not str(event.external_id or "").strip():
        _settle(event)
        return "settled"
    if _has_later_recovery(event) or _has_active_alert(event) or _already_replayed(event):
        _settle(event)
        return "settled"
    if _still_shielded(event, shields):
        return "waiting"
    if not _replay(event):
        return "failed"
    _settle(event)
    return "replayed"


def _settle(event):
    Event.objects.filter(pk=event.pk, shield_settled_at__isnull=True).update(shield_settled_at=timezone.now())


def _has_later_recovery(event):
    created_key = build_recovery_match_key(event)
    if created_key is None:
        return False
    created_time = event.start_time or event.received_at
    recoveries = Event.objects.filter(
        source_id=event.source_id,
        push_source_id=event.push_source_id,
        external_id=event.external_id,
        action__in=[EventAction.RECOVERY, EventAction.CLOSED],
    ).only("source_id", "push_source_id", "external_id", "team", "end_time", "start_time", "received_at")
    for recovery in recoveries:
        if build_recovery_match_key(recovery) != created_key:
            continue
        recovery_time = recovery.end_time or recovery.start_time or recovery.received_at
        if created_time and recovery_time and recovery_time > created_time:
            return True
    return False


def _has_active_alert(event):
    return Alert.objects.filter(
        status__in=AlertStatus.ACTIVATE_STATUS,
        events__source_id=event.source_id,
        events__push_source_id=event.push_source_id,
        events__external_id=event.external_id,
        events__action=EventAction.CREATED,
    ).exists()


def _already_replayed(event):
    generation = f"{_REPLAY_PREFIX}{event.event_id}"
    rows = (
        Event.objects.filter(
            source_id=event.source_id,
            push_source_id=event.push_source_id,
            external_id=event.external_id,
            action=EventAction.CREATED,
        )
        .exclude(pk=event.pk)
        .only("raw_data")
    )
    for row in rows:
        raw = row.raw_data if isinstance(row.raw_data, dict) else {}
        if raw.get("lifecycle_generation") == generation:
            return True
    return False


def _still_shielded(event, shields):
    now = timezone.now()
    matcher = None
    for shield in shields:
        checker = TimeRangeChecker(
            shield.suppression_time,
            now,
            resolve_display_timezone([getattr(shield, "created_by", None)]),
        )
        if not checker.is_in_range():
            continue
        if shield.match_type == AlertShieldMatchType.ALL:
            return True
        if shield.match_type != AlertShieldMatchType.FILTER:
            continue
        if matcher is None:
            matcher = MonitorSourceRuleMatcher(model_fields("shield"), source_field="push_source_id")
        if event.pk in matcher.filter_queryset(Event.objects.filter(pk=event.pk), shield.match_rules or []):
            return True
    return False


def _replay(event):
    raw = event.raw_data if isinstance(event.raw_data, dict) else {}
    payload = dict(raw)
    payload["title"] = payload.get("title") or event.title
    payload["level"] = payload.get("level") or event.level
    payload["external_id"] = event.external_id
    payload["action"] = EventAction.CREATED
    payload["push_source_id"] = event.push_source_id
    payload["organizations"] = list(event.team or [])
    payload["lifecycle_action"] = "created"
    payload["lifecycle_generation"] = f"{_REPLAY_PREFIX}{event.event_id}"
    if event.start_time and not payload.get("start_time"):
        payload["start_time"] = str(int(event.start_time.timestamp()))

    from apps.alerts.common.source_adapter.nats import NatsAdapter

    adapter = NatsAdapter(alert_source=event.source, events=[payload], trusted_internal=True)
    adapter.main()
    result = getattr(adapter, "last_ingestion_result", None) or {}
    return result.get("accepted", 0) > 0 or result.get("duplicates", 0) > 0
