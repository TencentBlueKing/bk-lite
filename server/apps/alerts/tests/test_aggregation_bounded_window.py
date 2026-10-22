import logging
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
from apps.alerts.aggregation.query.builder import SQLBuilder
from apps.alerts.aggregation.window.factory import WindowConfig, WindowType
from apps.alerts.constants.constants import AlertStatus, EventAction, LevelType
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.models import Alert, AlertSource, Event, Level
from apps.alerts.models.outbox import AlertOutbox
from apps.core.logger import alert_logger


@pytest.fixture
def source(db):
    return AlertSource.objects.create(name="源1", source_id="s1", source_type="restful", secret="x")


@pytest.fixture
def alert_levels(db):
    for level_id in (0, 1, 2):
        Level.objects.create(
            level_id=level_id,
            level_name=f"L{level_id}",
            level_display_name=f"等级{level_id}",
            level_type=LevelType.ALERT,
        )


def _event(source, event_id, **overrides):
    received_at = overrides.pop("received_at", None)
    event = Event.objects.create(
        source=source,
        raw_data={},
        title=overrides.pop("title", "CPU高"),
        description=overrides.pop("description", "cpu high"),
        level=overrides.pop("level", "1"),
        start_time=overrides.pop("start_time", timezone.now()),
        event_id=event_id,
        action=overrides.pop("action", EventAction.CREATED),
        service=overrides.pop("service", "svc-a"),
        resource_name=overrides.pop("resource_name", "host-a"),
        item=overrides.pop("item", "cpu"),
        external_id=overrides.pop("external_id", event_id),
        **overrides,
    )
    if received_at is not None:
        Event.objects.filter(pk=event.pk).update(received_at=received_at)
        event.refresh_from_db()
    return event


def _strategy(**params):
    defaults = {"window_size": 60, "group_by": ["service"]}
    defaults.update(params)
    return AlarmStrategy.objects.create(
        name="降噪",
        strategy_type="smart_denoise",
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "title", "operator": "eq", "value": "CPU高"}]],
        params=defaults,
    )


def test_aggregation_sql_omits_event_id_list_and_sorts_resource_names():
    sql = SQLBuilder().build_aggregation_sql(
        dimensions=["service"],
        window_config=WindowConfig(
            WindowType.SLIDING,
            window_size_minutes=10,
            window_end=timezone.now(),
        ),
        strategy_id=1,
    )
    assert "LIST(event_id)" not in sql
    assert "ORDER BY CAST(resource_name AS VARCHAR)" in sql
    assert "arg_max(title, (received_at, pk))" in sql


@pytest.mark.django_db
def test_window_end_excludes_event_at_right_edge(source):
    window_end = timezone.now()
    inside = _event(source, "E-inside", received_at=window_end - timedelta(minutes=1))
    edge = _event(source, "E-edge", received_at=window_end)
    strategy = _strategy()

    event_ids = set(AggregationProcessor.get_events_for_strategy(strategy, window_end).values_list("event_id", flat=True))

    assert inside.event_id in event_ids
    assert edge.event_id not in event_ids


@pytest.mark.django_db
def test_multi_event_content_uses_sorted_resource_names(source, alert_levels, caplog):
    _event(source, "E-b", resource_name="host-b", description="later", external_id="ext-b")
    _event(source, "E-a", resource_name="host-a", description="earlier", external_id="ext-a")
    _strategy()

    with caplog.at_level(logging.INFO, logger=alert_logger.name):
        AggregationProcessor().process_aggregation()

    alert = Alert.objects.get()
    assert alert.content == "影响范围：host-a,host-b"
    assert {event.event_id for event in alert.events.all()} == {"E-a", "E-b"}
    strategy = AlarmStrategy.objects.get()
    summary = next(record for record in caplog.records if "window_summary" in record.getMessage())
    assert summary.msg == "[AlertAggregation] window_summary strategy_id=%s loaded_batches=%s groups=%s"
    assert summary.args == (strategy.id, 1, 1)
    rendered = summary.getMessage()
    assert rendered == f"[AlertAggregation] window_summary strategy_id={strategy.id} loaded_batches=1 groups=1"
    assert "host-a" not in rendered
    assert "cpu high" not in rendered


@pytest.mark.django_db
def test_pk_batches_keep_every_member(source, alert_levels):
    received_at = timezone.now() - timedelta(minutes=1)
    events = [
        Event(
            source=source,
            raw_data={},
            title="CPU高",
            description="cpu high",
            level="1",
            start_time=received_at,
            received_at=received_at,
            event_id=f"E{index}",
            action=EventAction.CREATED,
            service="svc-a",
            resource_name="host-b" if index % 2 else "host-a",
            item="cpu",
            external_id=f"ext-{index}",
        )
        for index in range(1001)
    ]
    Event.objects.bulk_create(events, batch_size=500)
    _strategy()

    AggregationProcessor().process_aggregation()

    alert = Alert.objects.get()
    assert alert.events.count() == 1001


@pytest.mark.django_db
def test_failed_group_still_assigns_committed_group(source, alert_levels, mocker):
    from apps.alerts.aggregation.builder.alert_builder import AlertBuilder

    _event(source, "E-a", service="svc-a", external_id="ext-a")
    _event(source, "E-b", service="svc-b", external_id="ext-b")
    strategy = _strategy()
    real = AlertBuilder.create_or_update_alert
    calls = {"count": 0}

    def wrapped(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("group failed")
        return real(*args, **kwargs)

    mocker.patch(
        "apps.alerts.aggregation.processor.aggregation_processor.AlertBuilder.create_or_update_alert",
        side_effect=wrapped,
    )
    dispatched = mocker.patch("apps.alerts.service.alert_lifecycle.dispatch_alert_lifecycle")

    with pytest.raises(RuntimeError, match="聚合轮次部分失败"):
        AggregationProcessor().process_aggregation()

    strategy.refresh_from_db()
    assert strategy.last_execute_time is None
    assert Alert.objects.count() == 1
    assert dispatched.called


@pytest.mark.django_db
def test_session_end_is_anchored_to_window_end(source, alert_levels, monkeypatch):
    frozen = timezone.now()
    monkeypatch.setattr("django.utils.timezone.now", lambda: frozen)
    _event(source, "E-session", received_at=frozen - timedelta(minutes=1), external_id="ext-session")
    _strategy(time_out=True, time_minutes=15)

    AggregationProcessor().process_aggregation()

    alert = Alert.objects.get()
    assert alert.session_end_time == frozen + timedelta(minutes=15)
    assert alert.session_status == "observing"


@pytest.mark.django_db
def test_recovery_outbox_reattaches_once_per_window(source, alert_levels):
    created = _event(source, "E-created", external_id="ext-same")
    _strategy()
    AggregationProcessor().process_aggregation()
    AggregationProcessor().process_aggregation()

    assert AlertOutbox.objects.filter(kind="recovery_reattach").count() == 1
    alert = Alert.objects.get()
    recovery = _event(
        source,
        "E-recovery",
        action=EventAction.RECOVERY,
        external_id="ext-same",
        start_time=created.start_time,
        end_time=created.start_time + timedelta(minutes=5),
        received_at=timezone.now(),
    )
    from apps.alerts.service.outbox import deliver_outbox_record

    record = AlertOutbox.objects.get(kind="recovery_reattach")
    assert deliver_outbox_record(record.pk) is True
    alert.refresh_from_db()
    assert recovery.pk in set(alert.events.values_list("pk", flat=True))
    assert alert.status == AlertStatus.AUTO_RECOVERY


@pytest.mark.django_db
def test_unique_fallback_requires_one_candidate_alert(source):
    from apps.alerts.aggregation.recovery.recovery_checker import attach_visible_recoveries

    created = _event(
        source,
        "E-created",
        external_id="created-ext",
        item="cpu",
        resource_name="host-a",
        resource_id="",
        resource_type="",
    )
    alert = Alert.objects.create(
        alert_id="ALERT-FALLBACK",
        fingerprint="fp-fallback",
        level="1",
        title="t",
        content="c",
        status=AlertStatus.UNASSIGNED,
    )
    alert.events.add(created)
    other = Alert.objects.create(
        alert_id="ALERT-OTHER",
        fingerprint="fp-other",
        level="1",
        title="t",
        content="c",
        status=AlertStatus.UNASSIGNED,
    )
    other.events.add(
        _event(
            source,
            "E-other",
            external_id="other-ext",
            item="cpu",
            resource_name="host-a",
            resource_id="",
            resource_type="",
        )
    )
    recovery = _event(
        source,
        "E-recovery",
        action=EventAction.RECOVERY,
        external_id="recovery-ext",
        item="cpu",
        resource_name="host-a",
        resource_id="",
        resource_type="",
        end_time=created.start_time + timedelta(minutes=5),
    )

    assert attach_visible_recoveries(alert) == 0
    assert recovery.pk not in set(alert.events.values_list("pk", flat=True))

    other.delete()
    assert attach_visible_recoveries(alert) == 1
    assert recovery.pk in set(alert.events.values_list("pk", flat=True))


@pytest.mark.django_db
def test_constructed_events_exercise_bounded_window(source, alert_levels, monkeypatch, caplog):
    """用构造事件核对窗口、分批装载、代表事件顺序和恢复补挂。"""
    from apps.alerts.aggregation.engine.connection import DuckDBConnection

    frozen = timezone.now()
    monkeypatch.setattr("django.utils.timezone.now", lambda: frozen)
    monkeypatch.setattr("apps.alerts.aggregation.engine.connection.AGGREGATION_BATCH_SIZE", 2)
    monkeypatch.setattr("apps.alerts.aggregation.builder.alert_builder.AGGREGATION_BATCH_SIZE", 2)
    original_pages = DuckDBConnection.iter_member_pk_batches

    def page_by_two(self, expression, value, batch_size=2):
        return original_pages(self, expression, value, batch_size)

    monkeypatch.setattr(DuckDBConnection, "iter_member_pk_batches", page_by_two)

    later = frozen - timedelta(minutes=1)
    older = frozen - timedelta(minutes=3)
    svc_a = [
        _event(source, "A-old", service="svc-a", received_at=older, description="旧描述", resource_name="host-z", external_id="ext-old"),
        _event(source, "A-new", service="svc-a", received_at=later, description="新描述", resource_name="host-a", external_id="ext-new"),
        _event(source, "A-tie", service="svc-a", received_at=later, description="同刻描述", resource_name="host-m", external_id="ext-tie"),
    ]
    svc_b = [
        _event(source, "B-c", service="svc-b", received_at=later, resource_name="host-c", external_id="ext-b-c"),
        _event(source, "B-a", service="svc-b", received_at=later, resource_name="host-a", external_id="ext-b-a"),
        _event(source, "B-b", service="svc-b", received_at=later, resource_name="host-b", external_id="ext-b-b"),
    ]
    single = _event(source, "C-one", service="svc-one", received_at=later, description="仅此一条", resource_name="host-c", external_id="ext-one")
    too_old = _event(source, "OUT-old", service="svc-a", received_at=frozen - timedelta(minutes=61), external_id="ext-out-old")
    at_edge = _event(source, "OUT-edge", service="svc-a", received_at=frozen, external_id="ext-out-edge")
    other_title = _event(source, "OUT-title", service="svc-a", received_at=later, title="磁盘满", external_id="ext-out-title")
    recovery = _event(
        source,
        "A-recovery",
        action=EventAction.RECOVERY,
        service="svc-a",
        received_at=later,
        external_id="ext-old",
        end_time=svc_a[0].start_time + timedelta(minutes=5),
        resource_name="host-z",
    )
    _strategy(time_out=True, time_minutes=15)

    included_ids = [event.event_id for event in svc_a + svc_b + [single, too_old, at_edge]]
    connection = DuckDBConnection()
    loaded = connection.load_events_to_memory(Event.objects.filter(event_id__in=included_ids), dimensions=["service"])
    sql = SQLBuilder().build_aggregation_sql(
        dimensions=["service"],
        window_config=WindowConfig(WindowType.SLIDING, window_size_minutes=60, window_end=frozen),
        strategy_id=1,
    )
    rows = {row["effective_group_dimension"]: row for row in connection.execute_query(sql)}
    svc_a_row = rows["service=svc-a"]
    member_batches = list(original_pages(connection, SQLBuilder().grouping_expression(["service"]), "service=svc-a", 2))
    connection.close()

    assert loaded is True
    assert connection.loaded_batches == 5
    assert "LIST(event_id)" not in sql
    assert set(rows) == {"service=svc-a", "service=svc-b", "service=svc-one"}
    assert svc_a_row["event_count"] == 3
    assert svc_a_row["alert_title"] == "CPU高"
    assert svc_a_row["first_event_description"] == "同刻描述"
    assert svc_a_row["alert_description"] == "host-a,host-m,host-z"
    assert [len(batch) for batch in member_batches] == [2, 2, 1]
    assert {pk for batch in member_batches for pk in batch} == {event.pk for event in svc_a + [too_old, at_edge]}

    with caplog.at_level(logging.INFO, logger=alert_logger.name):
        AggregationProcessor().process_aggregation()

    alerts = {alert.title: alert for alert in Alert.objects.all()}
    assert set(alerts) == {"svc-a 检测到异常", "svc-b 检测到异常", "svc-one 检测到异常"}
    alert_a = alerts["svc-a 检测到异常"]
    alert_b = alerts["svc-b 检测到异常"]
    alert_c = alerts["svc-one 检测到异常"]
    assert alert_a.content == "影响范围：host-a,host-m,host-z"
    assert alert_b.content == "影响范围：host-a,host-b,host-c"
    assert alert_c.content == "仅此一条"
    assert {event.event_id for event in alert_a.events.all()} == {"A-old", "A-new", "A-tie", "A-recovery"}
    assert recovery.pk in set(alert_a.events.values_list("pk", flat=True))
    assert alert_a.status != AlertStatus.AUTO_RECOVERY
    assert alert_a.session_status == "observing"
    assert alert_a.session_end_time == frozen + timedelta(minutes=15)
    assert timezone.is_aware(alert_a.first_event_time)
    assert timezone.is_aware(alert_a.last_event_time)
    assert alert_a.first_event_time == older
    assert alert_a.last_event_time == later
    excluded = {too_old.event_id, at_edge.event_id, other_title.event_id}
    linked = set(Event.objects.filter(alert__isnull=False).values_list("event_id", flat=True))
    assert excluded.isdisjoint(linked)
    summary = next(record for record in caplog.records if record.msg.startswith("[AlertAggregation] window_summary"))
    assert summary.args == (AlarmStrategy.objects.get().id, 4, 3)
    assert "同刻描述" not in summary.getMessage()
    assert AlertOutbox.objects.filter(kind="recovery_reattach").count() == 3
