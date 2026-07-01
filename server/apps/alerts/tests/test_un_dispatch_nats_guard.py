# -- coding: utf-8 --
"""未分派兜底通知：聚合多告警无单一组织，opspilot nats 通道需跳过。"""

import pytest

from apps.alerts.constants.constants import LevelType
from apps.alerts.models.models import Alert, Level
from apps.alerts.models.sys_setting import SystemSetting
from apps.alerts.service.un_dispatch import UnDispatchService


@pytest.mark.django_db
def test_un_dispatch_skips_nats_channel():
    Level.objects.get_or_create(
        level_id=0, level_type=LevelType.ALERT,
        defaults={"level_name": "critical", "level_display_name": "严重"},
    )
    SystemSetting.objects.create(
        key="no_dispatch_alert_notice",
        value={
            "notify_people": ["alice"],
            "notify_channel": [{"id": 9, "channel_type": "nats"}, {"id": 3, "channel_type": "email"}],
        },
        is_activate=True,
        description="d",
    )
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")

    params = UnDispatchService.notify_un_dispatched_alert_params_format(alerts=[alert])

    types = {p["channel_type"] for p in params}
    assert "nats" not in types
    assert "email" in types
