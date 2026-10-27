"""即时告警和缺失检测省略 params 的局部更新。

同类型 PATCH 只改描述或启停时，必填校验沿用已保存参数，不把它们当成空配置。
显式空 params、创建缺模板、切换类型且不带新参数仍然拒绝，并且不落库。
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.constants import HeartbeatActivationMode, HeartbeatCheckMode, HeartbeatStatus
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.views.strategy import AlarmStrategyModelViewSet

MATCH_RULES = [[{"key": "title", "operator": "eq", "value": "cpu"}]]
INSTANT_PARAMS = {"alert_template": {"title": "CPU 过高", "description": "主机 CPU 持续过高"}}
MISSING_PARAMS = {
    "check_mode": HeartbeatCheckMode.CRON,
    "cron_expr": "*/5 * * * *",
    "grace_period": 3,
    "activation_mode": HeartbeatActivationMode.IMMEDIATE,
    "auto_recovery": False,
    "heartbeat_status": HeartbeatStatus.ALERTING,
    "last_heartbeat_time": "2026-03-20T00:00:00+08:00",
    "last_heartbeat_context": {"service": "backup"},
    "alert_template": {"title": "心跳缺失", "level": "1", "description": "备份心跳中断"},
}


def _request(method, path, user, data=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    force_authenticate(request, user=user)
    return request


def _render(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


def _patch(strategy, user, data):
    request = _request("patch", f"/alarm_strategy/{strategy.id}/", user, data=data)
    response = AlarmStrategyModelViewSet.as_view({"patch": "partial_update"})(request, pk=str(strategy.id))
    return response, _render(response)


def _instant(name, **overrides):
    fields = {
        "name": name,
        "strategy_type": "instant",
        "description": "旧描述",
        "is_active": True,
        "team": [1],
        "dispatch_team": [1],
        "match_rules": MATCH_RULES,
        "params": INSTANT_PARAMS,
    }
    fields.update(overrides)
    return AlarmStrategy.objects.create(**fields)


def _missing(name):
    return AlarmStrategy.objects.create(
        name=name,
        strategy_type="missing_detection",
        description="旧描述",
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=MATCH_RULES,
        params=MISSING_PARAMS,
    )


@pytest.mark.django_db
def test_instant_patch_description_keeps_saved_params(superuser):
    strategy = _instant("即时只改描述")
    response, _payload = _patch(strategy, superuser, {"description": "新描述"})
    assert response.status_code == status.HTTP_200_OK
    strategy.refresh_from_db()
    assert strategy.description == "新描述"
    assert strategy.params == INSTANT_PARAMS
    assert strategy.match_rules == MATCH_RULES


@pytest.mark.django_db
def test_instant_patch_is_active_keeps_saved_params(superuser):
    strategy = _instant("即时只改启停")
    response, _payload = _patch(strategy, superuser, {"is_active": False})
    assert response.status_code == status.HTTP_200_OK
    strategy.refresh_from_db()
    assert strategy.is_active is False
    assert strategy.params == INSTANT_PARAMS
    assert strategy.match_rules == MATCH_RULES


@pytest.mark.django_db
def test_missing_detection_patch_description_keeps_saved_params(superuser):
    strategy = _missing("缺失只改描述")
    response, _payload = _patch(strategy, superuser, {"description": "新描述"})
    assert response.status_code == status.HTTP_200_OK
    strategy.refresh_from_db()
    assert strategy.description == "新描述"
    assert strategy.params["cron_expr"] == "*/5 * * * *"
    assert strategy.params["grace_period"] == 3
    assert strategy.params["alert_template"] == MISSING_PARAMS["alert_template"]
    assert strategy.params["heartbeat_status"] == HeartbeatStatus.ALERTING
    assert strategy.params["last_heartbeat_time"] == "2026-03-20T00:00:00+08:00"
    assert strategy.params["last_heartbeat_context"] == {"service": "backup"}
    assert strategy.params == MISSING_PARAMS
    assert strategy.match_rules == MATCH_RULES


@pytest.mark.django_db
def test_missing_detection_patch_is_active_keeps_saved_params(superuser):
    strategy = _missing("缺失只改启停")
    response, _payload = _patch(strategy, superuser, {"is_active": False})
    assert response.status_code == status.HTTP_200_OK
    strategy.refresh_from_db()
    assert strategy.is_active is False
    assert strategy.params["cron_expr"] == "*/5 * * * *"
    assert strategy.params["grace_period"] == 3
    assert strategy.params["alert_template"] == MISSING_PARAMS["alert_template"]
    assert strategy.params["heartbeat_status"] == HeartbeatStatus.ALERTING
    assert strategy.params["last_heartbeat_time"] == "2026-03-20T00:00:00+08:00"
    assert strategy.params["last_heartbeat_context"] == {"service": "backup"}
    assert strategy.params == MISSING_PARAMS
    assert strategy.match_rules == MATCH_RULES


@pytest.mark.django_db
def test_instant_patch_empty_params_rejected_and_description_unchanged(superuser):
    strategy = _instant("即时空参数")
    response, payload = _patch(strategy, superuser, {"params": {}})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = json.dumps(payload, ensure_ascii=False)
    assert "告警模板标题不能为空。" in body or "告警模板描述不能为空。" in body
    strategy.refresh_from_db()
    assert strategy.description == "旧描述"
    assert strategy.params == INSTANT_PARAMS


@pytest.mark.django_db
def test_create_instant_without_template_rejected(superuser):
    data = {
        "name": "即时缺模板",
        "strategy_type": "instant",
        "team": [1],
        "dispatch_team": [1],
        "match_rules": MATCH_RULES,
        "params": {},
    }
    request = _request("post", "/alarm_strategy/", superuser, data=data)
    response = AlarmStrategyModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not AlarmStrategy.objects.filter(name="即时缺模板").exists()


@pytest.mark.django_db
def test_switch_smart_denoise_to_instant_without_params_rejected(superuser):
    strategy = AlarmStrategy.objects.create(
        name="降噪待切换",
        strategy_type="smart_denoise",
        description="保持",
        team=[1],
        dispatch_team=[1],
        match_rules=MATCH_RULES,
        params={"window_size": 10, "group_by": ["service"]},
    )
    response, _payload = _patch(strategy, superuser, {"strategy_type": "instant"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    strategy.refresh_from_db()
    assert strategy.strategy_type == "smart_denoise"
    assert strategy.params == {"window_size": 10, "group_by": ["service"]}
