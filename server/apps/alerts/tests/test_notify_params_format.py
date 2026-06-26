# -- coding: utf-8 --
"""NotifyParamsFormat.format_title 对缺失 Level 行的兜底——不抛 Level.DoesNotExist
（分派/提醒/升级通知都在事务内构造，抛异常会回滚整个操作）。"""

import pytest

from apps.alerts.common.notify.base import NotifyParamsFormat
from apps.alerts.constants.constants import LevelType
from apps.alerts.models.models import Alert, Level


def _alert(level="0", title="标题"):
    # 不落库；format_title 只读 alert.level / alert.title
    return Alert(alert_id="A1", level=level, title=title, content="c", fingerprint="fp", team=[1])


@pytest.mark.django_db
def test_format_title_falls_back_when_level_missing():
    # 无对应 Level 行：用原始级别兜底，绝不抛异常
    fmt = NotifyParamsFormat(username_list=[], alerts=[_alert(level="0", title="X")])
    assert fmt.format_title() == "【0】X"


@pytest.mark.django_db
def test_format_title_uses_level_display_name_when_present():
    Level.objects.get_or_create(
        level_id=0, level_type=LevelType.ALERT,
        defaults={"level_name": "critical", "level_display_name": "严重"},
    )
    fmt = NotifyParamsFormat(username_list=[], alerts=[_alert(level="0", title="X")])
    assert fmt.format_title() == "【严重】X"
