"""告警监控源集合：保留来源字符串身份，统一生成稳定快照。"""

from collections.abc import Iterable

from django.db import transaction

from apps.alerts.models.models import Alert


def normalize_push_source_ids(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value.strip()})


def collect_push_source_ids(events) -> list[str]:
    return normalize_push_source_ids(getattr(event, "push_source_id", None) for event in events)


def associate_event_with_monitor_sources(alert_pk, event) -> bool:
    """在同一行锁下关联事件并刷新来源，返回是否新增关联。"""
    with transaction.atomic():
        alert = Alert.objects.select_for_update().get(pk=alert_pk)
        added = not alert.events.filter(pk=event.pk).exists()
        if added:
            alert.events.add(event)
        sources = normalize_push_source_ids(alert.events.order_by().values_list("push_source_id", flat=True).distinct())
        if sources != alert.push_source_ids:
            Alert.objects.filter(pk=alert.pk).update(push_source_ids=sources)
        return added
