"""通知收口出口(Q1)单元测试:build_channel_params + enqueue_notifications。"""

from unittest import mock

import pytest

from apps.alerts.common.notify.dispatcher import build_channel_params, enqueue_notifications


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


@mock.patch("apps.alerts.tasks.sync_notify.delay")
def test_enqueue_notifications_empty_is_noop(mock_delay):
    assert enqueue_notifications([]) is False
    mock_delay.assert_not_called()


@pytest.mark.django_db
@mock.patch("apps.alerts.tasks.sync_notify.delay")
def test_enqueue_notifications_defers_in_atomic_block(mock_delay, django_capture_on_commit_callbacks):
    params = [{"username_list": ["u1"], "channel_type": "email", "channel_id": 1,
               "title": "t", "content": "c", "object_id": "A", "notify_action_object": "alert"}]
    with django_capture_on_commit_callbacks(execute=True):
        assert enqueue_notifications(params) is True
    mock_delay.assert_called_once_with(params)
