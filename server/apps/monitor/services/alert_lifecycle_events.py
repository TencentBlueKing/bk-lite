import uuid

from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import MonitorEvent


def record_lifecycle_events(alerts, action, *, event_time, operator="", reason=""):
    """为告警状态转换写入幂等生命周期 Event，已存在的动作不会再写。"""
    if not alerts:
        return []

    alert_ids = [alert.id for alert in alerts]
    existing_alert_ids = set(
        MonitorEvent.objects.filter(alert_id__in=alert_ids, action=action).values_list("alert_id", flat=True)
    )
    create_events = []
    for alert in alerts:
        if alert.id in existing_alert_ids:
            continue
        create_events.append(
            MonitorEvent(
                id=uuid.uuid4().hex,
                alert_id=alert.id,
                policy_id=alert.policy_id,
                monitor_instance_id=alert.monitor_instance_id,
                metric_instance_id=alert.metric_instance_id or "",
                dimensions=alert.dimensions or {},
                value=alert.value,
                level=alert.level or "info",
                action=action,
                content=_lifecycle_content(alert, action, operator=operator, reason=reason),
                notice_result=[],
                event_time=event_time,
            )
        )
    if not create_events:
        return []
    MonitorEvent.objects.bulk_create(
        create_events,
        batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE,
        ignore_conflicts=True,
    )
    return list(
        MonitorEvent.objects.filter(
            alert_id__in=[event.alert_id for event in create_events],
            action=action,
        )
    )


def _lifecycle_content(alert, action, *, operator, reason):
    base = alert.content or ""
    if action == MonitorEvent.Action.CLOSED:
        parts = [part for part in (base, reason, operator) if part]
        return " ".join(parts)
    return base
