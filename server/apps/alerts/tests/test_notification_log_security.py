from unittest import mock

import logging

from apps.alerts.tasks.tasks import sync_notify


def test_sync_notify_logs_metadata_without_sensitive_content(caplog):
    params = [{
        "username_list": ["u1"],
        "channel_id": 1,
        "channel_type": "email",
        "title": "title",
        "content": "SECRET-BODY-123",
    }]
    with mock.patch("apps.alerts.tasks.tasks.Notify") as notify:
        notify.return_value.notify.return_value = {"result": True}
        with caplog.at_level(logging.INFO, logger="alert"):
            sync_notify(params)

    assert "SECRET-BODY-123" not in caplog.text
    assert "channel_id=1" in caplog.text
