"""告警自动关闭覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-告警.md：超过策略 close_minutes 未更新的活跃告警自动关闭。
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.alerts.common.auto_close import AlertAutoClose, WindowCalculator
from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.models import Alert


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
        name="策略", strategy_type="smart_denoise", is_active=is_active,
        auto_close=auto_close, close_minutes=close_minutes,
    )


def _make_alert(strategy, last_event_minutes_ago=120, status=AlertStatus.PROCESSING):
    now = timezone.now()
    return Alert.objects.create(
        alert_id="A1", level="0", title="t", content="c", fingerprint="fp",
        status=status, rule_id=str(strategy.id),
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
