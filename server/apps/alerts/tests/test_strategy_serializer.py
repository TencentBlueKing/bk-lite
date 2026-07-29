"""告警策略序列化器校验覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-配置.md：相关性规则（智能降噪/缺失检查）参数校验。
"""

from types import SimpleNamespace

import pytest

from apps.alerts.serializers.strategy import AlarmStrategySerializer


def _ctx(superuser=True):
    request = SimpleNamespace(
        user=SimpleNamespace(is_superuser=superuser, group_list=[{"id": 1}]),
        COOKIES={"current_team": "1"},
    )
    return {"request": request}


# --------------------------------------------------------------------------
# validate_team / dispatch_team
# --------------------------------------------------------------------------


def test_validate_team_superuser_passes():
    ser = AlarmStrategySerializer(context=_ctx(superuser=True))
    assert ser.validate_team([1, 2]) == [1, 2]


def test_validate_team_invalid_value_raises():
    from rest_framework import serializers

    ser = AlarmStrategySerializer(context=_ctx())
    with pytest.raises(serializers.ValidationError):
        ser.validate_team("notalist")


# --------------------------------------------------------------------------
# validate (smart_denoise)
# --------------------------------------------------------------------------


def test_validate_smart_denoise_normalizes_window():
    ser = AlarmStrategySerializer(context=_ctx())
    attrs = {"strategy_type": "smart_denoise", "params": {"window_size": 10}}
    result = ser.validate(attrs)
    assert result["params"]["window_size"] == 10
    assert result["last_execute_time"] is None


def test_validate_smart_denoise_invalid_window_raises():
    from rest_framework import serializers

    ser = AlarmStrategySerializer(context=_ctx())
    attrs = {"strategy_type": "smart_denoise", "params": {"window_size": -5}}
    with pytest.raises(serializers.ValidationError):
        ser.validate(attrs)


# --------------------------------------------------------------------------
# validate (missing_detection)
# --------------------------------------------------------------------------


def _missing_attrs(**param_over):
    params = {
        "check_mode": "cron",
        "cron_expr": "*/5 * * * *",
        "grace_period": 5,
        "activation_mode": "first_heartbeat",
        "auto_recovery": True,
        "alert_template": {"title": "标题", "level": "1", "description": "详情"},
    }
    params.update(param_over)
    return {
        "strategy_type": "missing_detection",
        "match_rules": [[{"key": "item", "operator": "eq", "value": "hb"}]],
        "params": params,
    }


def test_validate_missing_detection_ok():
    ser = AlarmStrategySerializer(context=_ctx())
    result = ser.validate(_missing_attrs())
    assert result["params"]["check_mode"] == "cron"
    assert result["params"]["cron_expr"] == "*/5 * * * *"


def test_validate_missing_detection_no_match_rules():
    from rest_framework import serializers

    ser = AlarmStrategySerializer(context=_ctx())
    attrs = _missing_attrs()
    attrs["match_rules"] = []
    with pytest.raises(serializers.ValidationError):
        ser.validate(attrs)


def test_validate_missing_detection_invalid_cron():
    from rest_framework import serializers

    ser = AlarmStrategySerializer(context=_ctx())
    with pytest.raises(serializers.ValidationError):
        ser.validate(_missing_attrs(cron_expr="not a cron"))


def test_validate_missing_detection_invalid_grace_period():
    from rest_framework import serializers

    ser = AlarmStrategySerializer(context=_ctx())
    with pytest.raises(serializers.ValidationError):
        ser.validate(_missing_attrs(grace_period=0))


def test_validate_missing_detection_missing_template_title():
    from rest_framework import serializers

    ser = AlarmStrategySerializer(context=_ctx())
    with pytest.raises(serializers.ValidationError):
        ser.validate(_missing_attrs(alert_template={"title": "", "level": "1", "description": "x"}))
