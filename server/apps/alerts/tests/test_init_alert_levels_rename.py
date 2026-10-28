"""已改名的内置等级按 level_id 与 level_type 识别，初始化不得另插一行。"""
from io import StringIO

import pytest
from django.core.management import call_command

from apps.alerts.constants.constants import LevelType
from apps.alerts.models.models import Level

pytestmark = pytest.mark.django_db


def test_renamed_builtin_level_survives_reinit_and_missing_level_is_recreated():
    Level.objects.all().delete()
    call_command("init_alert_levels", stdout=StringIO())

    level = Level.objects.get(level_type=LevelType.EVENT, level_id=0)
    level.level_name = "Critical-custom"
    level.color = "#112233"
    level.save(update_fields=["level_name", "color"])

    out = StringIO()
    call_command("init_alert_levels", stdout=out)
    assert "成功初始化 0 个告警级别" in out.getvalue()

    rows = Level.objects.filter(level_type=LevelType.EVENT, level_id=0)
    assert rows.count() == 1
    kept = rows.get()
    assert kept.level_name == "Critical-custom"
    assert kept.color == "#112233"

    kept.delete()
    call_command("init_alert_levels", stdout=StringIO())
    recreated = Level.objects.filter(level_type=LevelType.EVENT, level_id=0)
    assert recreated.count() == 1
    restored = recreated.get()
    assert restored.level_name == "Critical"
    assert restored.color == "#F43B2C"
    assert restored.built_in is True
