import logging
from unittest import mock

from apps.alerts.common.notify.notify import Notify
from apps.alerts.tasks.tasks import sync_notify


def test_sync_notify_logs_metadata_without_sensitive_content(caplog):
    params = [
        {
            "username_list": ["u1"],
            "channel_id": 1,
            "channel_type": "email",
            "title": "title",
            "content": "SECRET-BODY-123",
        }
    ]
    with mock.patch("apps.alerts.tasks.tasks.Notify") as notify:
        notify.return_value.notify.return_value = {"result": True}
        with caplog.at_level(logging.INFO, logger="alert"):
            sync_notify(params)

    assert "SECRET-BODY-123" not in caplog.text
    assert "channel_id=1" in caplog.text


def test_notify_logs_channel_without_content_or_downstream(caplog):
    secret = "must-not-log-notify-body"
    downstream = {"token": "must-not-log-notify-result"}
    users = [{"username": "u1", "id": 42, "email": "a@b.c"}]
    with (
        mock.patch(
            "apps.alerts.common.notify.notify.SystemMgmtUtils.get_user_all",
            return_value=users,
        ),
        mock.patch(
            "apps.alerts.common.notify.notify.SystemMgmtUtils.send_msg_with_channel",
            return_value=downstream,
        ) as send,
    ):
        notify = Notify(username_list=["u1"], channel_id=7, title="t", content=secret)
        with caplog.at_level(logging.INFO, logger="alert"):
            result = notify.notify()

    assert result is downstream
    send.assert_called_once_with(
        channel_id=7,
        title="t",
        content=secret,
        receivers=[42],
    )
    records = [record for record in caplog.records if record.name == "alert" and record.msg.startswith("[AlertNotify] 通知已发送:")]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "[AlertNotify] 通知已发送: channel_id=%s, receiver_count=%s"
    assert record.args == (7, 1)
    rendered = record.getMessage()
    assert rendered == "[AlertNotify] 通知已发送: channel_id=7, receiver_count=1"
    assert secret not in caplog.text
    assert secret not in rendered
    assert "must-not-log-notify-result" not in caplog.text
    assert "must-not-log-notify-result" not in rendered
