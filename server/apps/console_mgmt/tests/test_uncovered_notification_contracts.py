"""补齐通知创建的数据层失败契约。"""

import pytest

from apps.console_mgmt import nats_api


pytestmark = pytest.mark.unit


def test_create_notification_returns_diagnostic_when_repository_fails(
    monkeypatch,
):
    def fail_lookup(**_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(nats_api.App.objects, "filter", fail_lookup)

    result = nats_api.create_notification("custom-app", "deployment done")

    assert result == {
        "result": False,
        "message": "database unavailable",
    }
