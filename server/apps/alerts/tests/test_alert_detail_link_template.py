import pytest

from apps.alerts.notification_templates.operation import ALERT_DETAIL_GUIDE, _default_content, resolve_alert_detail_prefix
from apps.alerts.notification_templates.renderer import validate_source


class _Request:
    def __init__(self, host, secure=False):
        self.host = host
        self.secure = secure

    def get_host(self):
        return self.host

    def is_secure(self):
        return self.secure


def test_detail_prefix_uses_request_host_without_port():
    assert resolve_alert_detail_prefix(_Request("10.11.27.147:8000")) == "http://10.11.27.147"
    assert resolve_alert_detail_prefix(_Request("bklite.example.com", secure=True)) == "https://bklite.example.com"


def test_loopback_request_uses_detected_server_ip(monkeypatch):
    monkeypatch.setattr(
        "apps.alerts.notification_templates.operation._detect_server_ip",
        lambda: "10.11.27.147",
    )
    assert resolve_alert_detail_prefix(_Request("127.0.0.1:8000", secure=True)) == "http://10.11.27.147"


@pytest.mark.parametrize("channel_type", ["email", "enterprise_wechat_bot", "custom_webhook"])
def test_builtin_operation_template_explains_prefix_plus_alert_id(channel_type):
    _subject, body = _default_content(channel_type, "http://10.11.27.147")
    assert "http://10.11.27.147/alarm/alarms?alert_id={{ alert.alert_id }}" in body
    assert ALERT_DETAIL_GUIDE in body
    assert "alert.detail_url" not in body
    if channel_type == "email":
        validate_source(body, channel_type="email", scope="alert_operation")
