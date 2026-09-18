"""告警初始化命令：级别幂等写入、系统设置、内置聚合规则。"""
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.alerts.constants.init_data import DEFAULT_LEVEL, SYSTEM_SETTINGS
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Level
from apps.alerts.models.sys_setting import SystemSetting
from apps.alerts.utils.rule_catalog import rules_are_valid

pytestmark = pytest.mark.django_db


def test_init_alert_levels_creates_then_is_idempotent():
    Level.objects.all().delete()
    out = StringIO()
    call_command("init_alert_levels", stdout=out)
    assert f"成功初始化 {len(DEFAULT_LEVEL)} 个告警级别" in out.getvalue()
    assert Level.objects.filter(built_in=True).count() == len(DEFAULT_LEVEL)

    out = StringIO()
    call_command("init_alert_levels", stdout=out)
    assert "成功初始化 0 个告警级别" in out.getvalue()
    assert Level.objects.filter(built_in=True).count() == len(DEFAULT_LEVEL)


def test_init_alert_levels_reraises_after_logging():
    with (
        patch("apps.alerts.models.models.Level.objects.get_or_create", side_effect=RuntimeError("db down")),
        pytest.raises(RuntimeError, match="db down"),
    ):
        call_command("init_alert_levels")


def test_init_system_settings_creates_and_runs_enrichment():
    SystemSetting.objects.all().delete()
    with patch("apps.alerts.constants.init_data.init_enrichment_rules") as enrich:
        out = StringIO()
        call_command("init_system_settings", stdout=out)
    enrich.assert_called_once()
    assert f"成功初始化 {len(SYSTEM_SETTINGS)} 个系统设置" in out.getvalue()
    assert SystemSetting.objects.count() == len(SYSTEM_SETTINGS)


def test_init_alert_rules_creates_when_empty_and_skips_when_present():
    AlertSource.objects.filter(source_id="nats").delete()
    AlarmStrategy.objects.all().delete()
    nats = AlertSource.objects.create(name="NATS", source_id="nats", source_type="nats", secret="x")
    call_command("init_alert_rules")
    strategy = AlarmStrategy.objects.get(name="内置检测规则")
    assert strategy.strategy_type == "smart_denoise"
    assert strategy.params["window_size"] == 2
    assert strategy.auto_close is True
    assert strategy.close_minutes == 120
    assert strategy.match_rules == [[{"key": "source_name", "operator": "any_of", "value": [nats.name]}]]
    assert rules_are_valid(strategy.match_rules, "correlation")

    call_command("init_alert_rules")
    assert AlarmStrategy.objects.filter(name="内置检测规则").count() == 1
    assert AlarmStrategy.objects.get(name="内置检测规则").match_rules == strategy.match_rules


def test_init_alert_rules_rewrites_legacy_source_id_filter():
    AlertSource.objects.filter(source_id="nats").delete()
    AlarmStrategy.objects.all().delete()
    nats = AlertSource.objects.create(name="NATS", source_id="nats", source_type="nats", secret="x")
    AlarmStrategy.objects.create(
        name="内置检测规则",
        strategy_type="smart_denoise",
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "source_id", "operator": "eq", "value": nats.id}]],
        params={"window_size": 2},
    )
    call_command("init_alert_rules")
    strategy = AlarmStrategy.objects.get(name="内置检测规则")
    assert strategy.match_rules == [[{"key": "source_name", "operator": "any_of", "value": [nats.name]}]]
    assert rules_are_valid(strategy.match_rules, "correlation")


def test_init_alert_rules_keeps_custom_match_rules():
    AlertSource.objects.filter(source_id="nats").delete()
    AlarmStrategy.objects.all().delete()
    AlertSource.objects.create(name="NATS", source_id="nats", source_type="nats", secret="x")
    custom = [[{"key": "title", "operator": "contains", "value": "cpu"}]]
    AlarmStrategy.objects.create(
        name="内置检测规则",
        strategy_type="smart_denoise",
        team=[1],
        dispatch_team=[1],
        match_rules=custom,
        params={"window_size": 2},
    )
    call_command("init_alert_rules")
    assert AlarmStrategy.objects.get(name="内置检测规则").match_rules == custom
