"""告警自动关闭覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-告警.md：超过策略 close_minutes 未更新的活跃告警自动关闭。
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.alerts.common.auto_close import REOPEN_OBJECT, AlertAutoClose, WindowCalculator
from apps.alerts.constants.constants import AlertStatus, EventAction, EventStatus
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event
from apps.alerts.models.operator_log import OperatorLog

# --------------------------------------------------------------------------
# WindowCalculator.parse_time_str
# --------------------------------------------------------------------------


def test_parse_time_str_variants():
    assert WindowCalculator.parse_time_str("5min") == timedelta(minutes=5)
    assert WindowCalculator.parse_time_str("2h") == timedelta(hours=2)
    assert WindowCalculator.parse_time_str("3d") == timedelta(days=3)
    assert WindowCalculator.parse_time_str("30s") == timedelta(seconds=30)
    assert WindowCalculator.parse_time_str("10") == timedelta(minutes=10)


# --------------------------------------------------------------------------
# AlertAutoClose
# --------------------------------------------------------------------------


def _make_strategy(close_minutes=60, auto_close=True, is_active=True):
    return AlarmStrategy.objects.create(
        name="策略",
        strategy_type="smart_denoise",
        is_active=is_active,
        auto_close=auto_close,
        close_minutes=close_minutes,
    )


def _make_alert(strategy, last_event_minutes_ago=120, status=AlertStatus.PROCESSING, alert_id="A1", fingerprint="fp"):
    now = timezone.now()
    return Alert.objects.create(
        alert_id=alert_id,
        level="0",
        title="t",
        content="c",
        fingerprint=fingerprint,
        status=status,
        rule_id=str(strategy.id),
        first_event_time=now - timedelta(minutes=last_event_minutes_ago),
        last_event_time=now - timedelta(minutes=last_event_minutes_ago),
    )


@pytest.mark.django_db
def test_build_rule_mapping_includes_auto_close_strategy():
    strategy = _make_strategy()
    _make_alert(strategy)
    closer = AlertAutoClose()
    assert str(strategy.id) in closer.rule_id_to_strategy


@pytest.mark.django_db
def test_should_auto_close_true_when_overdue():
    strategy = _make_strategy(close_minutes=60)
    alert = _make_alert(strategy, last_event_minutes_ago=120)
    closer = AlertAutoClose()
    assert closer.should_auto_close(alert, strategy) is True


@pytest.mark.django_db
def test_should_auto_close_false_when_recent():
    strategy = _make_strategy(close_minutes=60)
    alert = _make_alert(strategy, last_event_minutes_ago=10)
    closer = AlertAutoClose()
    assert closer.should_auto_close(alert, strategy) is False


@pytest.mark.django_db
def test_should_auto_close_false_when_disabled():
    strategy = _make_strategy(close_minutes=0, auto_close=False)
    alert = _make_alert(strategy, last_event_minutes_ago=120)
    closer = AlertAutoClose()
    assert closer.should_auto_close(alert, strategy) is False


@pytest.mark.django_db
def test_should_auto_close_false_when_no_last_event():
    strategy = _make_strategy(close_minutes=60)
    alert = _make_alert(strategy)
    alert.last_event_time = None
    alert.save()
    closer = AlertAutoClose()
    assert closer.should_auto_close(alert, strategy) is False


@pytest.mark.django_db
def test_auto_close_alert_sets_status():
    strategy = _make_strategy(close_minutes=60)
    alert = _make_alert(strategy, last_event_minutes_ago=120)
    closer = AlertAutoClose()
    assert closer.auto_close_alert(alert, strategy) is True
    alert.refresh_from_db()
    assert alert.status == AlertStatus.AUTO_CLOSE
    assert alert.closed_at is not None


@pytest.mark.django_db
def test_auto_close_alert_skips_inactive_alert():
    strategy = _make_strategy(close_minutes=60)
    alert = _make_alert(strategy, status=AlertStatus.CLOSED)
    closer = AlertAutoClose()
    assert closer.auto_close_alert(alert, strategy) is False


@pytest.mark.django_db
def test_auto_close_main_closes_overdue():
    strategy = _make_strategy(close_minutes=60)
    _make_alert(strategy, last_event_minutes_ago=120)
    AlertAutoClose().main()
    assert Alert.objects.get(alert_id="A1").status == AlertStatus.AUTO_CLOSE


def _monitor_event(source, event_id, external_id, when, action=EventAction.CREATED):
    return Event.objects.create(
        source=source,
        push_source_id="lite-monitor",
        raw_data={"title": "t"},
        title="t",
        level="1",
        start_time=when,
        end_time=when if action == EventAction.RECOVERY else None,
        event_id=event_id,
        external_id=external_id,
        action=action,
        status=EventStatus.RECEIVED,
        team=[1],
    )


@pytest.mark.django_db
def test_lite_monitor_without_recovery_stays_open_and_records_both_logs():
    strategy = _make_strategy(close_minutes=60)
    alert = _make_alert(strategy, last_event_minutes_ago=120, status=AlertStatus.PROCESSING)
    source = AlertSource.objects.create(name="NATS", source_id="nats", source_type="nats", secret="x")
    created_at = timezone.now() - timedelta(hours=3)
    event = _monitor_event(source, "E-created", "monitor-9", created_at)
    alert.events.add(event)

    AlertAutoClose().main()

    alert.refresh_from_db()
    overviews = list(OperatorLog.objects.filter(target_id=alert.alert_id).order_by("id").values_list("overview", flat=True))
    assert alert.status == AlertStatus.PROCESSING
    assert alert.closed_at is None
    assert len(overviews) == 2
    assert overviews[0].startswith("告警自动关闭")
    assert "Lite Monitor（lite-monitor）" in overviews[1]
    assert "E-created" in overviews[1]
    assert OperatorLog.objects.filter(target_id=alert.alert_id, operator_object=REOPEN_OBJECT).count() == 1

    AlertAutoClose().main()
    assert OperatorLog.objects.filter(target_id=alert.alert_id).count() == 2


@pytest.mark.django_db
def test_lite_monitor_with_later_recovery_still_auto_closes():
    strategy = _make_strategy(close_minutes=60)
    alert = _make_alert(strategy, last_event_minutes_ago=120)
    source = AlertSource.objects.create(name="NATS", source_id="nats", source_type="nats", secret="x")
    created_at = timezone.now() - timedelta(hours=3)
    alert.events.add(_monitor_event(source, "E-created", "monitor-9", created_at))
    alert.events.add(_monitor_event(source, "E-recovery", "monitor-9", timezone.now() - timedelta(hours=1), EventAction.RECOVERY))

    AlertAutoClose().main()

    alert.refresh_from_db()
    assert alert.status == AlertStatus.AUTO_CLOSE
    assert OperatorLog.objects.filter(target_id=alert.alert_id, operator_object=REOPEN_OBJECT).exists() is False


@pytest.mark.django_db
def test_already_auto_closed_lite_monitor_alert_reopens():
    strategy = _make_strategy(close_minutes=60)
    alert = _make_alert(strategy, last_event_minutes_ago=120, status=AlertStatus.AUTO_CLOSE)
    alert.operator = ["alice"]
    alert.closed_at = timezone.now() - timedelta(hours=1)
    alert.save(update_fields=["operator", "closed_at"])
    OperatorLog.objects.create(
        action="modify",
        target_type="alert",
        operator="system",
        operator_object="告警处理-自动关闭",
        target_id=alert.alert_id,
        overview="告警自动关闭, 告警标题[t], 触发策略[策略], 超时关闭时间[60]分钟",
    )
    source = AlertSource.objects.create(name="NATS", source_id="nats", source_type="nats", secret="x")
    alert.events.add(_monitor_event(source, "E-created", "monitor-9", timezone.now() - timedelta(hours=3)))

    AlertAutoClose().main()

    alert.refresh_from_db()
    reopen = OperatorLog.objects.get(target_id=alert.alert_id, operator_object=REOPEN_OBJECT)
    assert alert.status == AlertStatus.PENDING
    assert alert.closed_at is None
    assert "E-created" in reopen.overview
    assert "Lite Monitor（lite-monitor）" in reopen.overview
    assert OperatorLog.objects.filter(target_id=alert.alert_id, operator_object="告警处理-自动关闭").count() == 1


@pytest.mark.django_db
def test_auto_closed_lite_monitor_alert_older_than_a_day_stays_closed():
    strategy = _make_strategy(close_minutes=60)
    alert = _make_alert(strategy, last_event_minutes_ago=120, status=AlertStatus.AUTO_CLOSE)
    alert.closed_at = timezone.now() - timedelta(hours=48)
    alert.save(update_fields=["closed_at"])
    source = AlertSource.objects.create(name="NATS", source_id="nats-old", source_type="nats", secret="x")
    alert.events.add(_monitor_event(source, "E-old", "monitor-old", timezone.now() - timedelta(hours=50)))

    AlertAutoClose().main()

    alert.refresh_from_db()
    assert alert.status == AlertStatus.AUTO_CLOSE
    assert OperatorLog.objects.filter(target_id=alert.alert_id, operator_object=REOPEN_OBJECT).exists() is False


@pytest.mark.django_db
def test_recovered_auto_close_does_not_block_newer_reopen(monkeypatch, settings):
    from django.core.cache import cache

    from apps.alerts.common import auto_close

    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "auto-close-reopen-cursor",
        }
    }
    cache.close()
    cache.delete(auto_close.REOPEN_CURSOR_KEY)
    monkeypatch.setattr(auto_close, "REOPEN_BATCH_SIZE", 1)
    strategy = _make_strategy(close_minutes=60)
    source = AlertSource.objects.create(name="NATS", source_id="nats-cursor", source_type="nats", secret="x")
    recovered = _make_alert(strategy, last_event_minutes_ago=120, status=AlertStatus.AUTO_CLOSE, alert_id="A-old", fingerprint="fp-old")
    newer = _make_alert(strategy, last_event_minutes_ago=120, status=AlertStatus.AUTO_CLOSE, alert_id="A-new", fingerprint="fp-new")
    closed_at = timezone.now() - timedelta(hours=1)
    recovered.closed_at = closed_at
    newer.closed_at = closed_at
    recovered.save()
    newer.save()
    created_at = timezone.now() - timedelta(hours=3)
    recovered.events.add(_monitor_event(source, "E-old", "monitor-old", created_at))
    recovered.events.add(_monitor_event(source, "E-old-recovery", "monitor-old", timezone.now() - timedelta(hours=1), EventAction.RECOVERY))
    newer.events.add(_monitor_event(source, "E-new", "monitor-new", created_at))

    AlertAutoClose().main()
    newer.refresh_from_db()
    assert newer.status == AlertStatus.AUTO_CLOSE

    AlertAutoClose().main()
    newer.refresh_from_db()
    assert newer.status == AlertStatus.UNASSIGNED
    assert newer.closed_at is None


@pytest.mark.django_db
def test_reopen_stops_when_recovery_arrives_before_lock(monkeypatch):
    from apps.alerts.common import auto_close

    strategy = _make_strategy(close_minutes=60)
    alert = _make_alert(strategy, last_event_minutes_ago=120, status=AlertStatus.AUTO_CLOSE)
    alert.closed_at = timezone.now() - timedelta(hours=1)
    alert.save(update_fields=["closed_at"])
    source = AlertSource.objects.create(name="NATS", source_id="nats-race", source_type="nats", secret="x")
    alert.events.add(_monitor_event(source, "E-race", "monitor-race", timezone.now() - timedelta(hours=3)))
    answers = iter([["E-race"], []])
    monkeypatch.setattr(auto_close, "monitor_unrecovered_event_ids", lambda alert: next(answers))

    AlertAutoClose().main()

    alert.refresh_from_db()
    assert alert.status == AlertStatus.AUTO_CLOSE
    assert OperatorLog.objects.filter(target_id=alert.alert_id, operator_object=REOPEN_OBJECT).exists() is False


@pytest.mark.django_db
def test_auto_close_main_no_alerts_noop():
    # 无活跃告警 → 直接返回
    AlertAutoClose().main()


@pytest.mark.django_db
def test_auto_close_main_no_valid_strategy():
    # 有告警但无 auto_close 策略 → 跳过
    strategy = _make_strategy(close_minutes=0, auto_close=False)
    _make_alert(strategy, last_event_minutes_ago=120)
    AlertAutoClose().main()
    # 告警保持活跃
    assert Alert.objects.get(alert_id="A1").status == AlertStatus.PROCESSING


@pytest.mark.django_db
def test_auto_close_main_skips_when_last_event_updates_while_waiting_for_lock(monkeypatch):
    """锁外已超时；等待行锁期间 last_event_time 更新到现在时不得关闭。"""
    strategy = _make_strategy(close_minutes=60)
    alert = _make_alert(strategy, last_event_minutes_ago=120)
    closer = AlertAutoClose()
    original = closer.auto_close_alert
    stopped = []

    def interleaved(alert_arg, strategy_arg):
        Alert.objects.filter(pk=alert.pk).update(last_event_time=timezone.now())
        return original(alert_arg, strategy_arg)

    monkeypatch.setattr(closer, "auto_close_alert", interleaved)

    from apps.alerts.service.reminder_service import ReminderService

    def record_stop(cls, locked_alert):
        stopped.append(locked_alert.alert_id)
        return True

    monkeypatch.setattr(ReminderService, "stop_reminder_task", classmethod(record_stop))

    closer.main()

    alert.refresh_from_db()
    assert alert.status == AlertStatus.PROCESSING
    assert alert.closed_at is None
    assert stopped == []
