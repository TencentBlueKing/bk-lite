"""告警策略序列化器：即时告警 / 聚合维度 / 缺失检查 补充分支覆盖。

对照 spec/prd/告警中心·配置：即时告警必须配置筛选条件且模板标题/描述必填；
聚合维度白名单防注入；缺失检查激活方式/级别/描述校验；非超管授权校验；保存后清缓存。
"""

import pydantic.root_model  # noqa

from types import SimpleNamespace

import pytest
from rest_framework import serializers

from apps.alerts.serializers.strategy import AlarmStrategySerializer


def _ctx(superuser=True, group_ids=None):
    request = SimpleNamespace(
        user=SimpleNamespace(is_superuser=superuser, group_list=[{"id": gid} for gid in (group_ids or [])]),
        COOKIES={"current_team": "1"},
    )
    return {"request": request}


# --------------------------------------------------------------------------
# _validate_instant
# --------------------------------------------------------------------------


def _instant_attrs(**over):
    attrs = {
        "strategy_type": "instant",
        "match_rules": [[{"key": "level", "operator": "eq", "value": "0"}]],
        "params": {"alert_template": {"title": "标题", "description": "详情"}},
    }
    attrs.update(over)
    return attrs


def test_validate_instant_ok_strips_aggregation_and_sets_auto_close_false():
    ser = AlarmStrategySerializer(context=_ctx())
    attrs = _instant_attrs(
        params={
            "alert_template": {"title": " 标题 ", "description": " 详情 "},
            "window_size": 30,
            "group_by": ["level"],
            "aggregation_strategy": "x",
        }
    )
    result = ser.validate(attrs)
    # 聚合相关字段被清理，只保留 alert_template
    assert result["params"] == {"alert_template": {"title": "标题", "description": "详情"}}
    assert result["auto_close"] is False


def test_validate_instant_empty_match_rules_raises():
    ser = AlarmStrategySerializer(context=_ctx())
    with pytest.raises(serializers.ValidationError):
        ser.validate(_instant_attrs(match_rules=[]))


def test_validate_instant_all_empty_groups_raises():
    # match_rules 存在但每个 group 都是空 → 等价 ALL，不允许
    ser = AlarmStrategySerializer(context=_ctx())
    with pytest.raises(serializers.ValidationError):
        ser.validate(_instant_attrs(match_rules=[[], []]))


def test_validate_instant_missing_template_title_raises():
    ser = AlarmStrategySerializer(context=_ctx())
    attrs = _instant_attrs(params={"alert_template": {"title": "", "description": "详情"}})
    with pytest.raises(serializers.ValidationError):
        ser.validate(attrs)


def test_validate_instant_missing_template_description_raises():
    ser = AlarmStrategySerializer(context=_ctx())
    attrs = _instant_attrs(params={"alert_template": {"title": "标题", "description": ""}})
    with pytest.raises(serializers.ValidationError):
        ser.validate(attrs)


# --------------------------------------------------------------------------
# _validate_aggregation_strategy: group_by 白名单校验
# --------------------------------------------------------------------------


def test_validate_aggregation_group_by_not_list_raises():
    ser = AlarmStrategySerializer(context=_ctx())
    attrs = {"strategy_type": "smart_denoise", "params": {"window_size": 10, "group_by": "level"}}
    with pytest.raises(serializers.ValidationError):
        ser.validate(attrs)


def test_validate_aggregation_group_by_non_string_dim_raises():
    ser = AlarmStrategySerializer(context=_ctx())
    attrs = {"strategy_type": "smart_denoise", "params": {"window_size": 10, "group_by": [123]}}
    with pytest.raises(serializers.ValidationError):
        ser.validate(attrs)


def test_validate_aggregation_group_by_illegal_format_raises():
    ser = AlarmStrategySerializer(context=_ctx())
    # 含非法字符（如分号）-> 格式校验失败（防注入）
    attrs = {"strategy_type": "smart_denoise", "params": {"window_size": 10, "group_by": ["level;drop"]}}
    with pytest.raises(serializers.ValidationError):
        ser.validate(attrs)


def test_validate_aggregation_group_by_not_in_whitelist_raises():
    ser = AlarmStrategySerializer(context=_ctx())
    attrs = {"strategy_type": "smart_denoise", "params": {"window_size": 10, "group_by": ["not_allowed_dim"]}}
    with pytest.raises(serializers.ValidationError):
        ser.validate(attrs)


def test_validate_aggregation_group_by_valid_dim_passes():
    ser = AlarmStrategySerializer(context=_ctx())
    attrs = {"strategy_type": "smart_denoise", "params": {"window_size": 10, "group_by": ["level", "source"]}}
    result = ser.validate(attrs)
    assert result["params"]["group_by"] == ["level", "source"]


# --------------------------------------------------------------------------
# _validate_missing_detection 额外分支
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


def test_validate_missing_detection_invalid_activation_mode_raises():
    ser = AlarmStrategySerializer(context=_ctx())
    with pytest.raises(serializers.ValidationError):
        ser.validate(_missing_attrs(activation_mode="weird"))


def test_validate_missing_detection_invalid_check_mode_raises():
    ser = AlarmStrategySerializer(context=_ctx())
    with pytest.raises(serializers.ValidationError):
        ser.validate(_missing_attrs(check_mode="interval"))


def test_validate_missing_detection_interval_value_rejected():
    ser = AlarmStrategySerializer(context=_ctx())
    with pytest.raises(serializers.ValidationError):
        ser.validate(_missing_attrs(interval_value=5))


def test_validate_missing_detection_interval_unit_rejected():
    ser = AlarmStrategySerializer(context=_ctx())
    with pytest.raises(serializers.ValidationError):
        ser.validate(_missing_attrs(interval_unit="minute"))


def test_validate_missing_detection_empty_level_raises():
    ser = AlarmStrategySerializer(context=_ctx())
    with pytest.raises(serializers.ValidationError):
        ser.validate(_missing_attrs(alert_template={"title": "标题", "level": "", "description": "详情"}))


def test_validate_missing_detection_empty_description_raises():
    ser = AlarmStrategySerializer(context=_ctx())
    with pytest.raises(serializers.ValidationError):
        ser.validate(_missing_attrs(alert_template={"title": "标题", "level": "1", "description": ""}))


def test_validate_missing_detection_auto_recovery_none_defaults_true():
    ser = AlarmStrategySerializer(context=_ctx())
    result = ser.validate(_missing_attrs(auto_recovery=None))
    assert result["params"]["auto_recovery"] is True
    # 运行时字段填充默认
    assert result["params"]["heartbeat_status"] is not None


# --------------------------------------------------------------------------
# validate_team / dispatch_team 非超管授权校验
# --------------------------------------------------------------------------


def test_validate_dispatch_team_unauthorized_raises(monkeypatch):
    ser = AlarmStrategySerializer(context=_ctx(superuser=False))
    monkeypatch.setattr(
        "apps.alerts.serializers.strategy.get_authorized_group_ids",
        lambda request: [1],
    )
    with pytest.raises(serializers.ValidationError):
        ser.validate_dispatch_team([1, 99])


def test_validate_team_authorized_passes(monkeypatch):
    ser = AlarmStrategySerializer(context=_ctx(superuser=False))
    monkeypatch.setattr(
        "apps.alerts.serializers.strategy.get_authorized_group_ids",
        lambda request: [1, 2],
    )
    assert ser.validate_team([1, 2]) == [1, 2]


def test_validate_team_no_request_returns_team_ids():
    # context 无 request 时直接返回归一化后的 team_ids
    ser = AlarmStrategySerializer(context={})
    assert ser.validate_team([3, 1, 2]) == [3, 1, 2]


# --------------------------------------------------------------------------
# save(): 保存后清理即时策略缓存（异常被吞）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_save_clears_instant_strategy_cache(monkeypatch):
    from apps.alerts.models.alert_operator import AlarmStrategy

    called = {"n": 0}

    def fake_clear():
        called["n"] += 1

    monkeypatch.setattr(
        "apps.alerts.aggregation.processor.instant_dispatcher.InstantStrategyCache.cache_clear",
        staticmethod(fake_clear),
    )

    instance = AlarmStrategy.objects.create(
        name="s1", strategy_type="smart_denoise", params={"window_size": 10}
    )
    ser = AlarmStrategySerializer(instance=instance, context=_ctx())
    # 直接调用 save 触发缓存清理逻辑（无需走 is_valid）
    ser.instance = instance
    ser._validated_data = {}
    ser._errors = {}
    ser.save()
    # save 内部触发即时策略缓存清理（至少一次）
    assert called["n"] >= 1
