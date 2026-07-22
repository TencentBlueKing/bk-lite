"""通知收口出口(Q1)单元测试:build_channel_params + enqueue_notifications。"""

from unittest import mock

import pytest

from apps.alerts.common.notify.dispatcher import build_channel_params, enqueue_notifications
from apps.alerts.constants.constants import NotifyResultStatus
from apps.alerts.models.alert_operator import NotifyResult
from apps.alerts.tasks.tasks import sync_notify


@pytest.mark.django_db
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_content", return_value="c")
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_title", return_value="t")
def test_build_channel_params_one_per_channel(_mt, _mc):
    channels = [
        {"id": 7, "channel_type": "wechat", "name": "企微"},
        {"id": 9, "channel_type": "sms", "name": "短信"},
    ]
    params = build_channel_params(["u1", "u2"], channels, alerts=[], object_id="ALERT-1")
    assert isinstance(params, list) and len(params) == 2
    assert params[0] == {
        "username_list": ["u1", "u2"], "channel_type": "wechat", "channel_id": 7,
        "title": "t", "content": "c", "object_id": "ALERT-1", "notify_action_object": "alert",
    }
    assert params[1]["channel_type"] == "sms" and params[1]["channel_id"] == 9


def test_build_channel_params_empty_when_no_recipients_or_channels():
    assert build_channel_params([], [{"id": 1, "channel_type": "email"}], [], "x") == []
    assert build_channel_params(["u1"], [], [], "x") == []


@pytest.mark.django_db
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_content", return_value="正文")
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_title", return_value="标题")
def test_build_channel_params_nats_builds_dict_content(_mt, _mc):
    """opspilot 托管 NATS 通道：content 构造为 dict{message,team,user_ids}，team 取单一告警组织。"""
    from apps.alerts.models.models import Alert

    alert = Alert(alert_id="ALERT-1", level="0", title="t", content="c", fingerprint="fp", team=[2])
    channels = [
        {"id": 9, "channel_type": "nats", "name": "BotA"},
        {"id": 3, "channel_type": "email", "name": "邮件"},
    ]
    params = build_channel_params(["alice", "bob"], channels, alerts=[alert], object_id="ALERT-1")

    nats = next(p for p in params if p["channel_type"] == "nats")
    assert nats["title"] == ""
    assert nats["content"] == {"message": "正文", "team": 2, "user_ids": ["alice", "bob"]}
    assert nats["object_id"] == "ALERT-1"
    email = next(p for p in params if p["channel_type"] == "email")
    assert email["content"] == "正文"


@pytest.mark.django_db
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_content", return_value="正文")
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_title", return_value="标题")
def test_build_channel_params_nats_skipped_when_no_single_team(_mt, _mc):
    """无单一组织上下文(空 team / 非单条告警)时跳过 NATS 通道，其他通道不受影响。"""
    from apps.alerts.models.models import Alert

    alert = Alert(alert_id="ALERT-1", level="0", title="t", content="c", fingerprint="fp", team=[])
    channels = [
        {"id": 9, "channel_type": "nats", "name": "BotA"},
        {"id": 3, "channel_type": "email", "name": "邮件"},
    ]
    params = build_channel_params(["alice"], channels, alerts=[alert], object_id="ALERT-1")

    assert all(p["channel_type"] != "nats" for p in params)
    assert any(p["channel_type"] == "email" for p in params)


@mock.patch("apps.alerts.tasks.deliver_alert_outbox.delay")
def test_enqueue_notifications_empty_is_noop(mock_delay):
    assert enqueue_notifications([]) is False
    mock_delay.assert_not_called()


@pytest.mark.django_db
@mock.patch("apps.alerts.tasks.deliver_alert_outbox.delay")
def test_enqueue_notifications_persists_outbox_in_atomic_block(mock_delay, django_capture_on_commit_callbacks):
    from apps.alerts.models import AlertOutbox

    params = [{"username_list": ["u1"], "channel_type": "email", "channel_id": 1,
               "title": "t", "content": "c", "object_id": "A", "notify_action_object": "alert"}]
    with django_capture_on_commit_callbacks(execute=True):
        assert enqueue_notifications(params) is True
    record = AlertOutbox.objects.get()
    assert record.kind == "notification"
    assert record.payload == {"params": params}
    mock_delay.assert_called_once_with(record.pk)


@pytest.mark.django_db
@mock.patch("apps.alerts.tasks.tasks.Notify")
def test_sync_notify_records_exception_and_continues_with_next_notification(mock_notify):
    mock_notify.return_value.notify.side_effect = [
        RuntimeError("provider unavailable"),
        {"result": True},
    ]
    params = [
        {
            "username_list": ["alice"],
            "channel_type": "wechat",
            "channel_id": 1,
            "title": "first",
            "content": "first content",
            "object_id": "ALERT-FAILED",
        },
        {
            "username_list": ["bob"],
            "channel_type": "email",
            "channel_id": 2,
            "title": "second",
            "content": "second content",
            "object_id": "ALERT-SUCCESS",
        },
    ]

    results = sync_notify(params)

    assert results == [
        {"result": False, "message": "通知服务调用异常"},
        {"result": True},
    ]
    assert mock_notify.return_value.notify.call_count == 2
    failed_row = NotifyResult.objects.get(notify_object="ALERT-FAILED")
    success_row = NotifyResult.objects.get(notify_object="ALERT-SUCCESS")
    assert failed_row.notify_result == NotifyResultStatus.FAILED
    assert failed_row.failure_reason == "通知服务调用异常"
    assert "provider unavailable" not in failed_row.failure_reason
    assert success_row.notify_result == NotifyResultStatus.SUCCESS
