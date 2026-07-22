"""未分派通知拼装 + 提醒服务深层分支 补充覆盖。

对照 specs/capabilities/legacy-prd-告警中心-告警.md：未分派告警按系统配置渠道生成通知参数；提醒服务推进/停用逻辑。
"""

import pydantic.root_model  # noqa

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.alert_operator import AlertAssignment, AlertReminderTask
from apps.alerts.models.models import Alert
from apps.alerts.models.sys_setting import SystemSetting
from apps.alerts.service.reminder_service import ReminderService as RS
from apps.alerts.service.un_dispatch import UnDispatchService


def _make_alert(alert_id="A1", level="0", status=AlertStatus.UNASSIGNED):
    return Alert.objects.create(
        alert_id=alert_id, level=level, title="t", content="c", fingerprint="fp" + alert_id, status=status
    )


def _make_assignment(name="分派", frequency=None):
    return AlertAssignment.objects.create(name=name, match_type="all", notification_frequency=frequency or {})


def _fake_build_channel_params(
    username_list, channels, alerts, object_id, notify_action_object="alert", title=None, content=None
):
    return [
        {
            "username_list": username_list,
            "channel_type": channel["channel_type"],
            "channel_id": channel["id"],
            "title": title or "提醒标题",
            "content": content or "提醒内容",
            "object_id": object_id,
            "notify_action_object": notify_action_object,
        }
        for channel in channels
    ]


# --------------------------------------------------------------------------
# UnDispatchService.notify_un_dispatched_alert_params_format 完整拼装路径
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_un_dispatch_full_param_format(monkeypatch):
    SystemSetting.objects.create(
        key="no_dispatch_alert_notice",
        value={
            "notify_people": ["op1", "op2"],
            "notify_channel": [
                {"id": 1, "channel_type": "email"},
                {"id": 2, "channel_type": "wechat"},
            ],
        },
    )

    class FakeFormat:
        def __init__(self, username_list, alerts):
            self.username_list = username_list
            self.alerts = alerts

        def format_title(self):
            return "未分派告警"

        def format_content(self):
            return "内容"

    monkeypatch.setattr("apps.alerts.service.un_dispatch.NotifyParamsFormat", FakeFormat)

    alert = _make_alert()
    result = UnDispatchService.notify_un_dispatched_alert_params_format(alerts=[alert])

    assert len(result) == 2
    assert result[0]["channel_type"] == "email"
    assert result[0]["channel_id"] == 1
    assert result[0]["title"] == "未分派告警"
    assert result[0]["content"] == "内容"
    assert result[0]["username_list"] == ["op1", "op2"]
    assert result[1]["channel_type"] == "wechat"


@pytest.mark.django_db
def test_un_dispatch_no_alerts_returns_empty(monkeypatch):
    SystemSetting.objects.create(
        key="no_dispatch_alert_notice",
        value={"notify_people": ["op1"], "notify_channel": [{"id": 1, "channel_type": "email"}]},
    )
    # 配置齐全但无告警 -> 空（同时覆盖 alerts is None 时走 DB 查询路径，无未分派告警）
    assert UnDispatchService.notify_un_dispatched_alert_params_format(alerts=None) == []


@pytest.mark.django_db
def test_un_dispatch_fetches_alerts_from_db_when_none(monkeypatch):
    SystemSetting.objects.create(
        key="no_dispatch_alert_notice",
        value={"notify_people": ["op1"], "notify_channel": [{"id": 1, "channel_type": "email"}]},
    )
    _make_alert(alert_id="UN1", status=AlertStatus.UNASSIGNED)

    class FakeFormat:
        def __init__(self, username_list, alerts):
            self.alerts = alerts

        def format_title(self):
            return "T"

        def format_content(self):
            return "C"

    monkeypatch.setattr("apps.alerts.service.un_dispatch.NotifyParamsFormat", FakeFormat)
    # alerts=None -> search_no_operator_alerts 找到 UN1
    result = UnDispatchService.notify_un_dispatched_alert_params_format(alerts=None)
    assert len(result) == 1
    assert result[0]["channel_id"] == 1


@pytest.mark.django_db
def test_search_no_operator_alerts_filters_unassigned():
    _make_alert(alert_id="U1", status=AlertStatus.UNASSIGNED)
    _make_alert(alert_id="P1", status=AlertStatus.PENDING)
    result = UnDispatchService.search_no_operator_alerts()
    ids = {a.alert_id for a in result}
    assert "U1" in ids
    assert "P1" not in ids


# --------------------------------------------------------------------------
# ReminderService._send_reminder_notification: 成功投递并 on_commit 推进（mock celery）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_send_reminder_notification_enqueues_celery(monkeypatch):
    alert = _make_alert(level="0", status=AlertStatus.PENDING)
    assignment = _make_assignment()
    assignment.personnel = ["op1"]
    assignment.notify_channels = [{"id": 1, "channel_type": "email"}]
    assignment.save()

    # mock 升级服务返回无加层名册 -> 回退到 assignment.personnel / notify_channels
    monkeypatch.setattr(
        "apps.alerts.service.escalation_service.EscalationService.active_roster_for_reminder",
        staticmethod(lambda a: (None, None)),
    )
    monkeypatch.setattr(
        "apps.alerts.common.notify.dispatcher.build_channel_params",
        _fake_build_channel_params,
    )

    calls = {"delay": []}
    import apps.alerts.tasks as tasks_mod
    monkeypatch.setattr(
        tasks_mod.deliver_alert_outbox,
        "delay",
        lambda record_id: calls["delay"].append(record_id),
    )

    # django_db 测试处于事务中，_send_reminder_notification 走 on_commit 路径，
    # 用 captureOnCommitCallbacks 触发回调以验证 celery 投递契约。
    from django.test import TestCase

    with TestCase.captureOnCommitCallbacks(execute=True) as callbacks:
        result = RS._send_reminder_notification(assignment=assignment, alert=alert)
    assert result is True
    assert len(callbacks) == 1
    assert len(calls["delay"]) == 1
    from apps.alerts.models import AlertOutbox
    params = AlertOutbox.objects.get().payload["params"]
    assert params[0]["channel_type"] == "email"
    assert params[0]["object_id"] == alert.alert_id
    assert params[0]["notify_action_object"] == "alert"


@pytest.mark.django_db
def test_send_reminder_notification_channel_str_json_parsed(monkeypatch):
    alert = _make_alert(level="0", status=AlertStatus.PENDING)
    assignment = _make_assignment()
    assignment.personnel = ["op1"]
    # 渠道是 JSON 字符串 -> 内部 json.loads 解析
    assignment.notify_channels = '[{"id": 9, "channel_type": "sms"}]'
    assignment.save()

    monkeypatch.setattr(
        "apps.alerts.service.escalation_service.EscalationService.active_roster_for_reminder",
        staticmethod(lambda a: (None, None)),
    )
    monkeypatch.setattr(
        "apps.alerts.common.notify.dispatcher.build_channel_params",
        _fake_build_channel_params,
    )

    calls = {"delay": []}
    import apps.alerts.tasks as tasks_mod
    monkeypatch.setattr(
        tasks_mod.deliver_alert_outbox,
        "delay",
        lambda record_id: calls["delay"].append(record_id),
    )

    from django.test import TestCase

    with TestCase.captureOnCommitCallbacks(execute=True):
        result = RS._send_reminder_notification(assignment=assignment, alert=alert)
    assert result is True
    from apps.alerts.models import AlertOutbox
    assert AlertOutbox.objects.get().payload["params"][0]["channel_type"] == "sms"


@pytest.mark.django_db
def test_send_reminder_notification_invalid_channel_json_returns_false(monkeypatch):
    alert = _make_alert(level="0", status=AlertStatus.PENDING)
    assignment = _make_assignment()
    assignment.personnel = ["op1"]
    assignment.notify_channels = "not-json"
    assignment.save()

    monkeypatch.setattr(
        "apps.alerts.service.escalation_service.EscalationService.active_roster_for_reminder",
        staticmethod(lambda a: (None, None)),
    )
    # JSON 解析失败 -> channel_list=[] -> 返回 False
    assert RS._send_reminder_notification(assignment=assignment, alert=alert) is False


# --------------------------------------------------------------------------
# _update_reminder_task: 频率变化时重算 next_reminder_time
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_update_reminder_task_recomputes_next_time_on_freq_change():
    alert = _make_alert()
    assignment = _make_assignment()
    now = timezone.now()
    reminder = AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=True,
        current_frequency_minutes=10, current_max_reminders=5,
        last_reminder_time=now - timedelta(minutes=2),
        next_reminder_time=now + timedelta(minutes=8),
    )
    assert RS._update_reminder_task(reminder, 30, 5) is True
    reminder.refresh_from_db()
    assert reminder.current_frequency_minutes == 30
    # 频率变化且 next 未到，应被重算到未来
    assert reminder.next_reminder_time >= now


@pytest.mark.django_db
def test_update_reminder_task_negative_max_uses_default():
    alert = _make_alert()
    assignment = _make_assignment()
    reminder = AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=True,
        current_frequency_minutes=10, current_max_reminders=5,
        next_reminder_time=timezone.now(),
    )
    assert RS._update_reminder_task(reminder, 10, -1) is True
    reminder.refresh_from_db()
    assert reminder.current_max_reminders == RS.DEFAULT_MAX_REMINDERS


# --------------------------------------------------------------------------
# _get_effective_max_reminders: 各分支
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_effective_max_reminders_uses_current_when_no_level_config():
    alert = _make_alert(level="0")
    assignment = _make_assignment(frequency={})  # 无 level 配置
    reminder = AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=True,
        current_frequency_minutes=30, current_max_reminders=7,
        next_reminder_time=timezone.now(),
    )
    assert RS._get_effective_max_reminders(reminder) == 7


@pytest.mark.django_db
def test_get_effective_max_reminders_negative_current_uses_default():
    alert = _make_alert(level="0")
    assignment = _make_assignment(frequency={})
    reminder = AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=True,
        current_frequency_minutes=30, current_max_reminders=-1,
        next_reminder_time=timezone.now(),
    )
    assert RS._get_effective_max_reminders(reminder) == RS.DEFAULT_MAX_REMINDERS
