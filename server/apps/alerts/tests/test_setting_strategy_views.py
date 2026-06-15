"""系统设置与告警策略视图集覆盖测试。

对照 spec/prd/告警中心·配置：系统配置维护、相关性(告警)策略增删改查与缺失检查校验。
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.models.sys_setting import SystemSetting
from apps.alerts.views.strategy import AlarmStrategyModelViewSet
from apps.alerts.views.system_setting import SystemSettingModelViewSet


def _request(method, path, user, data=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    force_authenticate(request, user=user)
    return request


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


def _render(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


# --------------------------------------------------------------------------
# SystemSetting
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_system_setting_create(superuser):
    data = {"key": "demo_key", "value": {"x": 1}, "description": "d", "is_activate": True, "is_build": False}
    request = _request("post", "/settings/", superuser, data=data)
    response = SystemSettingModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_201_CREATED
    assert SystemSetting.objects.filter(key="demo_key").exists()
    assert OperatorLog.objects.filter(operator_object="系统配置-创建").exists()


@pytest.mark.django_db
def test_system_setting_get_setting_key_found(superuser):
    SystemSetting.objects.create(key="k1", value={"a": 1}, description="d")
    request = _request("get", "/settings/get_setting_key/k1/", superuser)
    response = SystemSettingModelViewSet.as_view({"get": "get_setting_key"})(request, setting_key="k1")
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["key"] == "k1"


@pytest.mark.django_db
def test_system_setting_get_setting_key_not_found(superuser):
    request = _request("get", "/settings/get_setting_key/missing/", superuser)
    response = SystemSettingModelViewSet.as_view({"get": "get_setting_key"})(request, setting_key="missing")
    _render(response)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_system_setting_update_non_dispatch_key(superuser):
    setting = SystemSetting.objects.create(key="other_key", value={"v": 1}, description="d", is_activate=False)
    data = {"value": {"v": 2}, "is_activate": True}
    request = _request("patch", f"/settings/{setting.id}/", superuser, data=data)
    response = SystemSettingModelViewSet.as_view({"patch": "update"})(request, pk=str(setting.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    setting.refresh_from_db()
    assert setting.value == {"v": 2}
    assert OperatorLog.objects.filter(operator_object="系统配置-修改").exists()


@pytest.mark.django_db
def test_system_setting_update_no_dispatch_activates_task(superuser, monkeypatch):
    from apps.alerts.views import system_setting as ss_mod

    calls = {}

    class FakeCelery:
        @staticmethod
        def is_task_enabled(name):
            return None

        @staticmethod
        def create_or_update_periodic_task(**kwargs):
            calls["created"] = kwargs

        @staticmethod
        def disable_periodic_task(name):
            calls["disabled"] = name

    monkeypatch.setattr(ss_mod, "CeleryUtils", FakeCelery)

    setting = SystemSetting.objects.create(
        key="no_dispatch_alert_notice", value={"notify_every": 30}, is_activate=False,
    )
    data = {"value": {"notify_every": 30}, "is_activate": True}
    request = _request("patch", f"/settings/{setting.id}/", superuser, data=data)
    response = SystemSettingModelViewSet.as_view({"patch": "update"})(request, pk=str(setting.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    # 从未激活变激活 → 创建周期任务
    assert "created" in calls


def test_convert_minutes_to_crontab_variants():
    fn = SystemSettingModelViewSet._convert_minutes_to_crontab
    assert fn(30) == "*/30 * * * *"
    assert fn(60) == "0 * * * *"
    assert fn(120) == "0 */2 * * *"
    assert fn(1440) == "0 0 * * *"
    assert fn(90) == "0 * * * *"  # 不能整除60，简化为每小时


def test_convert_minutes_to_crontab_invalid_raises():
    with pytest.raises(Exception):
        SystemSettingModelViewSet._convert_minutes_to_crontab("notint")


def test_convert_minutes_to_crontab_non_positive_defaults_60():
    assert SystemSettingModelViewSet._convert_minutes_to_crontab(0) == "0 * * * *"


@pytest.mark.django_db
def test_system_setting_get_channel_list(superuser):
    from apps.system_mgmt.models.channel import Channel

    Channel.objects.create(name="邮件", channel_type="email")
    Channel.objects.create(name="内部", channel_type="nats")
    request = _request("get", "/settings/get_channel_list/", superuser)
    response = SystemSettingModelViewSet.as_view({"get": "get_channel_list"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    # nats 渠道被排除
    names = [c["channel_type"] for c in payload["data"]]
    assert "nats" not in names
    assert "email" in names


# --------------------------------------------------------------------------
# AlarmStrategy
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_strategy_create_smart_denoise(superuser):
    data = {
        "name": "降噪策略",
        "strategy_type": "smart_denoise",
        "team": [1],
        "dispatch_team": [1],
        "match_rules": [],
        "params": {"window_size": 10},
        "auto_close": True,
        "close_minutes": 120,
    }
    request = _request("post", "/alarm_strategy/", superuser, data=data)
    response = AlarmStrategyModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_201_CREATED
    strategy = AlarmStrategy.objects.get(name="降噪策略")
    # window_size 经 parse_aggregation_window_size 归一
    assert strategy.params["window_size"] == 10
    assert OperatorLog.objects.filter(operator_object="告警策略-新增").exists()


@pytest.mark.django_db
def test_strategy_create_missing_detection_requires_match_rules(superuser):
    data = {
        "name": "缺失策略",
        "strategy_type": "missing_detection",
        "team": [1],
        "dispatch_team": [1],
        "match_rules": [],
        "params": {},
    }
    request = _request("post", "/alarm_strategy/", superuser, data=data)
    response = AlarmStrategyModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_strategy_list(superuser):
    AlarmStrategy.objects.create(name="s1", strategy_type="smart_denoise", team=[1])
    request = _request("get", "/alarm_strategy/", superuser)
    response = AlarmStrategyModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    assert len(items) == 1


@pytest.mark.django_db
def test_strategy_destroy(superuser):
    strategy = AlarmStrategy.objects.create(name="s1", strategy_type="smart_denoise", team=[1])
    request = _request("delete", f"/alarm_strategy/{strategy.id}/", superuser)
    response = AlarmStrategyModelViewSet.as_view({"delete": "destroy"})(request, pk=str(strategy.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert not AlarmStrategy.objects.filter(id=strategy.id).exists()
    assert OperatorLog.objects.filter(operator_object="告警策略-删除").exists()


@pytest.mark.django_db
def test_strategy_list_non_superuser_team_scoped(authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"alarm": {"correlation_rules-View"}}
    AlarmStrategy.objects.create(name="s1", strategy_type="smart_denoise", team=[1])
    AlarmStrategy.objects.create(name="s2", strategy_type="smart_denoise", team=[2])
    factory = APIRequestFactory()
    request = factory.get("/alarm_strategy/")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)
    response = AlarmStrategyModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    names = {i["name"] for i in items}
    assert "s1" in names
    assert "s2" not in names


@pytest.mark.django_db
def test_strategy_retrieve(superuser):
    strategy = AlarmStrategy.objects.create(name="s1", strategy_type="smart_denoise", team=[1], params={"window_size": 10})
    request = _request("get", f"/alarm_strategy/{strategy.id}/", superuser)
    response = AlarmStrategyModelViewSet.as_view({"get": "retrieve"})(request, pk=str(strategy.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["name"] == "s1"


@pytest.mark.django_db
def test_strategy_update(superuser):
    strategy = AlarmStrategy.objects.create(
        name="s1", strategy_type="smart_denoise", team=[1], dispatch_team=[1],
        match_rules=[], params={"window_size": 10},
    )
    data = {
        "name": "s1-改",
        "strategy_type": "smart_denoise",
        "team": [1],
        "dispatch_team": [1],
        "match_rules": [],
        "params": {"window_size": 20},
        "auto_close": True,
        "close_minutes": 120,
    }
    request = _request("put", f"/alarm_strategy/{strategy.id}/", superuser, data=data)
    response = AlarmStrategyModelViewSet.as_view({"put": "update"})(request, pk=str(strategy.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    strategy.refresh_from_db()
    assert strategy.name == "s1-改"
    assert strategy.params["window_size"] == 20
    assert OperatorLog.objects.filter(operator_object="告警策略-修改").exists()


@pytest.mark.django_db
def test_strategy_partial_update(superuser):
    strategy = AlarmStrategy.objects.create(
        name="s1", strategy_type="smart_denoise", team=[1], dispatch_team=[1],
        match_rules=[], params={"window_size": 10},
    )
    request = _request("patch", f"/alarm_strategy/{strategy.id}/", superuser, data={"description": "新描述"})
    response = AlarmStrategyModelViewSet.as_view({"patch": "partial_update"})(request, pk=str(strategy.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    strategy.refresh_from_db()
    assert strategy.description == "新描述"
