"""会话窗口超时检查覆盖测试。

对照 spec/prd/告警中心·告警：会话窗口告警超时未恢复后转为已确认；策略变更/删除批量处理观察中告警。
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.alerts.aggregation.recovery.timeout_checker import TimeoutChecker
from apps.alerts.constants.constants import AlertStatus, SessionStatus
from apps.alerts.models.models import Alert


def _session_alert(alert_id="A1", session_status=SessionStatus.OBSERVING, end_minutes=-5, rule_id="1"):
    return Alert.objects.create(
        alert_id=alert_id, level="0", title="t", content="c", fingerprint="fp" + alert_id,
        status=AlertStatus.UNASSIGNED, is_session_alert=True, session_status=session_status,
        session_end_time=timezone.now() + timedelta(minutes=end_minutes), rule_id=rule_id,
    )


@pytest.mark.django_db
def test_check_session_timeouts_confirms_expired():
    _session_alert("A1", end_minutes=-5)  # 已过期
    confirmed = TimeoutChecker.check_session_timeouts()
    assert confirmed == 1
    assert Alert.objects.get(alert_id="A1").session_status == SessionStatus.CONFIRMED


@pytest.mark.django_db
def test_check_session_timeouts_skips_not_expired():
    _session_alert("A1", end_minutes=30)  # 未过期
    confirmed = TimeoutChecker.check_session_timeouts()
    assert confirmed == 0
    assert Alert.objects.get(alert_id="A1").session_status == SessionStatus.OBSERVING


@pytest.mark.django_db
def test_confirm_observing_alerts_by_strategy():
    _session_alert("A1", rule_id="42")
    _session_alert("A2", rule_id="42")
    _session_alert("A3", rule_id="99")  # 不同策略
    count = TimeoutChecker.confirm_observing_alerts_by_strategy(42)
    assert count == 2
    assert Alert.objects.get(alert_id="A1").session_status == SessionStatus.CONFIRMED
    assert Alert.objects.get(alert_id="A3").session_status == SessionStatus.OBSERVING


@pytest.mark.django_db
def test_close_observing_session_alerts_by_strategy():
    _session_alert("A1", rule_id="42")
    count = TimeoutChecker.close_observing_session_alerts_by_strategy(42)
    assert count == 1
    alert = Alert.objects.get(alert_id="A1")
    assert alert.status == AlertStatus.CLOSED
    assert alert.session_status == SessionStatus.RECOVERED


@pytest.mark.django_db
def test_trigger_auto_assignment_for_empty_ids_noop():
    # 空列表直接返回，不报错
    assert TimeoutChecker._trigger_auto_assignment_for_alert_ids([]) is None
