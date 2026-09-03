"""普通与即时 Alert 持久化监控对象集合的契约。"""

from datetime import timedelta
from unittest import mock

import pytest
from django.db import transaction
from django.utils import timezone

from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
from apps.alerts.aggregation.processor.instant_dispatcher import InstantAlertDispatcher, InstantStrategyCache
from apps.alerts.aggregation.recovery.recovery_handler import RecoveryHandler
from apps.alerts.constants.constants import AlarmStrategyType, EventAction, LevelType
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event, Level

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _event(
    source,
    event_id,
    monitor_id,
    cmdb_id,
    resource_type,
    resource_name,
    **overrides,
):
    values = {
        "source": source,
        "raw_data": {},
        "title": "CPU high",
        "description": "CPU high",
        "level": "1",
        "start_time": timezone.now(),
        "event_id": event_id,
        "item": "cpu_usage",
        "monitor_id": monitor_id,
        "cmdb_id": cmdb_id,
        "resource_id": monitor_id,
        "resource_type": resource_type,
        "resource_name": resource_name,
        "push_source_id": "lite-monitor",
        "labels": {"sample": event_id},
    }
    values.update(overrides)
    return Event.objects.create(**values)


def _aggregation_context(name):
    AlertBuilder.clear_event_cache()
    AlertBuilder._valid_alert_levels = None
    Level.objects.create(
        level_id=1,
        level_name="error",
        level_display_name="错误",
        level_type=LevelType.ALERT,
    )
    source = AlertSource.objects.create(
        name="NATS",
        source_id=f"nats-{name}",
        source_type="nats",
        secret="x",
    )
    strategy = AlarmStrategy.objects.create(
        name=f"对象集合策略-{name}",
        strategy_type="smart_denoise",
        team=[1],
        dispatch_team=[1],
        params={"window_size": 10},
    )
    return source, strategy


def _aggregation_result(fingerprint, event_ids):
    now = timezone.now()
    return {
        "fingerprint": fingerprint,
        "event_ids": event_ids,
        "alert_level": "1",
        "alert_title": "聚合监控告警",
        "alert_description": "desc",
        "first_event_time": now,
        "last_event_time": now,
    }


def test_create_alert_persists_all_monitor_objects():
    AlertBuilder.clear_event_cache()
    AlertBuilder._valid_alert_levels = None
    Level.objects.create(
        level_id=1,
        level_name="error",
        level_display_name="错误",
        level_type=LevelType.ALERT,
    )
    source = AlertSource.objects.create(
        name="NATS",
        source_id="nats-aggregation-snapshot",
        source_type="nats",
        secret="x",
    )
    strategy = AlarmStrategy.objects.create(
        name="对象集合策略",
        strategy_type="smart_denoise",
        team=[1],
        dispatch_team=[1],
        params={"window_size": 10},
    )
    events = [
        _event(source, "EVENT-1", "0001", "xxxx1", "Host", "ip1"),
        _event(source, "EVENT-2", "0001", "xxxx1", "Host", "ip1"),
        _event(source, "EVENT-3", "0001", "xxxx1", "Host", "ip1"),
        _event(source, "EVENT-4", "0002", "xxxx2", "Switch", "ip2"),
    ]
    now = timezone.now()
    aggregation_result = {
        "fingerprint": "monitor-objects-create",
        "event_ids": [event.event_id for event in events],
        "alert_level": "1",
        "alert_title": "聚合监控告警",
        "alert_description": "desc",
        "first_event_time": now,
        "last_event_time": now,
    }

    with transaction.atomic():
        alert = AlertBuilder.create_or_update_alert(aggregation_result, strategy)

    assert alert.monitor_objects == [
        {
            "monitor_id": "0001",
            "cmdb_id": "xxxx1",
            "resource_type": "Host",
            "resource_name": "ip1",
        },
        {
            "monitor_id": "0002",
            "cmdb_id": "xxxx2",
            "resource_type": "Switch",
            "resource_name": "ip2",
        },
    ]
    assert alert.events.count() == 4
    assert (
        alert.resource_id,
        alert.resource_type,
        alert.resource_name,
        alert.labels,
    ) == (None, None, None, {})


def test_update_alert_recomputes_monitor_objects_from_all_related_created_events():
    source, strategy = _aggregation_context("update")
    first_event = _event(
        source,
        "EVENT-UPDATE-1",
        "monitor-1",
        "cmdb-1",
        "Host",
        "host-1",
    )
    second_event = _event(
        source,
        "EVENT-UPDATE-2",
        "monitor-2",
        "cmdb-2",
        "Switch",
        "switch-1",
    )

    with transaction.atomic():
        alert = AlertBuilder.create_or_update_alert(
            _aggregation_result("monitor-objects-update", [first_event.event_id]),
            strategy,
        )
    with transaction.atomic():
        alert = AlertBuilder.create_or_update_alert(
            _aggregation_result("monitor-objects-update", [second_event.event_id]),
            strategy,
        )

    assert alert.monitor_objects == [
        {
            "monitor_id": "monitor-1",
            "cmdb_id": "cmdb-1",
            "resource_type": "Host",
            "resource_name": "host-1",
        },
        {
            "monitor_id": "monitor-2",
            "cmdb_id": "cmdb-2",
            "resource_type": "Switch",
            "resource_name": "switch-1",
        },
    ]


def test_update_alert_fills_empty_monitor_object_slots_without_overwrite():
    source, strategy = _aggregation_context("fill")
    first_event = _event(
        source,
        "EVENT-FILL-1",
        "monitor-fill",
        None,
        None,
        None,
    )
    second_event = _event(
        source,
        "EVENT-FILL-2",
        "monitor-fill",
        "cmdb-fill",
        "Switch",
        "switch-fill",
    )

    with transaction.atomic():
        AlertBuilder.create_or_update_alert(
            _aggregation_result("monitor-objects-fill", [first_event.event_id]),
            strategy,
        )
    with transaction.atomic():
        alert = AlertBuilder.create_or_update_alert(
            _aggregation_result("monitor-objects-fill", [second_event.event_id]),
            strategy,
        )

    assert alert.monitor_objects == [
        {
            "monitor_id": "monitor-fill",
            "cmdb_id": "cmdb-fill",
            "resource_type": "Switch",
            "resource_name": "switch-fill",
        }
    ]


def test_recovery_event_does_not_extend_monitor_object_snapshot():
    source, strategy = _aggregation_context("recovery")
    created_event = _event(
        source,
        "EVENT-RECOVERY-CREATED",
        "monitor-created",
        "cmdb-created",
        "Host",
        "host-created",
        external_id="external-recovery-snapshot",
        action=EventAction.CREATED,
        team=[1],
    )
    with transaction.atomic():
        alert = AlertBuilder.create_or_update_alert(
            _aggregation_result(
                "monitor-objects-recovery",
                [created_event.event_id],
            ),
            strategy,
        )
    recovery_event = _event(
        source,
        "EVENT-RECOVERY-CLOSED",
        "monitor-recovery-only",
        "cmdb-recovery-only",
        "Switch",
        "switch-recovery-only",
        external_id="external-recovery-snapshot",
        action=EventAction.RECOVERY,
        team=[1],
        start_time=created_event.start_time + timedelta(minutes=1),
    )

    RecoveryHandler.handle_recovery_events([recovery_event])
    alert.refresh_from_db()

    assert alert.events.filter(pk=recovery_event.pk).exists()
    assert alert.monitor_objects == [
        {
            "monitor_id": "monitor-created",
            "cmdb_id": "cmdb-created",
            "resource_type": "Host",
            "resource_name": "host-created",
        }
    ]

    later_created_event = _event(
        source,
        "EVENT-RECOVERY-LATER-CREATED",
        "monitor-later-created",
        "cmdb-later-created",
        "Database",
        "db-later-created",
        external_id="external-later-created",
        action=EventAction.CREATED,
        team=[1],
    )
    with transaction.atomic():
        alert = AlertBuilder.create_or_update_alert(
            _aggregation_result(
                "monitor-objects-recovery",
                [later_created_event.event_id],
            ),
            strategy,
        )

    assert [item["monitor_id"] for item in alert.monitor_objects] == [
        "monitor-created",
        "monitor-later-created",
    ]


def test_alert_without_monitor_id_keeps_existing_resource_fields():
    source, strategy = _aggregation_context("legacy")
    event = _event(
        source,
        "EVENT-LEGACY-1",
        None,
        None,
        "legacy-type",
        "legacy-name",
        resource_id="legacy-resource",
        labels={"legacy": "value"},
    )

    with transaction.atomic():
        alert = AlertBuilder.create_or_update_alert(
            _aggregation_result("monitor-objects-legacy", [event.event_id]),
            strategy,
        )

    assert alert.monitor_objects == []
    assert {
        "resource_id": alert.resource_id,
        "resource_type": alert.resource_type,
        "resource_name": alert.resource_name,
        "labels": alert.labels,
    } == {
        "resource_id": "legacy-resource",
        "resource_type": "legacy-type",
        "resource_name": "legacy-name",
        "labels": {"legacy": "value"},
    }


def test_mixed_source_resource_id_does_not_create_fake_monitor_object():
    source, strategy = _aggregation_context("mixed")
    monitor_event = _event(
        source,
        "EVENT-MIXED-1",
        "monitor-real",
        "cmdb-real",
        "Host",
        "real-host",
    )
    third_party_event = _event(
        source,
        "EVENT-MIXED-2",
        None,
        None,
        "vendor-type",
        "vendor-host",
        resource_id="vendor-resource",
        push_source_id="third-party",
    )

    with transaction.atomic():
        alert = AlertBuilder.create_or_update_alert(
            _aggregation_result(
                "monitor-objects-mixed",
                [monitor_event.event_id, third_party_event.event_id],
            ),
            strategy,
        )

    assert [item["monitor_id"] for item in alert.monitor_objects] == ["monitor-real"]


def test_instant_alert_contains_single_monitor_object_snapshot(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "monitor-object-snapshot-test",
        }
    }
    from django.core.cache import cache

    cache.close()
    InstantStrategyCache.cache_clear()
    source = AlertSource.objects.create(
        name="NATS",
        source_id="nats-instant-snapshot",
        source_type="nats",
        secret="x",
    )
    AlarmStrategy.objects.create(
        name="即时对象集合策略",
        strategy_type=AlarmStrategyType.INSTANT,
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "title", "operator": "contains", "value": "CPU"}]],
        params={},
    )
    event = _event(
        source,
        "EVENT-INSTANT-1",
        "instant-monitor",
        "instant-cmdb",
        "Host",
        "instant-host",
    )

    with mock.patch("apps.alerts.tasks.deliver_alert_outbox.delay"):
        InstantAlertDispatcher.dispatch([[event]])

    alert = Alert.objects.get()
    assert alert.monitor_objects == [
        {
            "monitor_id": "instant-monitor",
            "cmdb_id": "instant-cmdb",
            "resource_type": "Host",
            "resource_name": "instant-host",
        }
    ]


def test_instant_alert_without_monitor_id_keeps_legacy_fields(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "monitor-object-legacy-instant-test",
        }
    }
    from django.core.cache import cache

    cache.close()
    InstantStrategyCache.cache_clear()
    source = AlertSource.objects.create(
        name="Vendor",
        source_id="vendor-instant-snapshot",
        source_type="nats",
        secret="x",
    )
    AlarmStrategy.objects.create(
        name="即时旧事件策略",
        strategy_type=AlarmStrategyType.INSTANT,
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "title", "operator": "contains", "value": "CPU"}]],
        params={},
    )
    event = _event(
        source,
        "EVENT-INSTANT-LEGACY",
        None,
        None,
        "legacy-type",
        "legacy-host",
        resource_id="legacy-resource",
        labels={"legacy": "value"},
        push_source_id="third-party",
    )

    with mock.patch("apps.alerts.tasks.deliver_alert_outbox.delay"):
        InstantAlertDispatcher.dispatch([[event]])

    alert = Alert.objects.get()
    assert alert.monitor_objects == []
    assert (
        alert.resource_id,
        alert.resource_type,
        alert.resource_name,
        alert.labels,
    ) == (
        "legacy-resource",
        "legacy-type",
        "legacy-host",
        {"legacy": "value"},
    )
