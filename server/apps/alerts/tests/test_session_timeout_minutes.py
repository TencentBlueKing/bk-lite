"""会话观察时间 time_minutes 必须在保存和读取时都是 int。

数字字符串不能原样进入 WindowConfig，否则 timedelta 会抛 TypeError。
"""

import json
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.aggregation.window.factory import WindowFactory, WindowType
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.views.strategy import AlarmStrategyModelViewSet


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


def _payload(name, time_minutes, time_out=True):
    return {
        "name": name,
        "strategy_type": "smart_denoise",
        "team": [1],
        "dispatch_team": [1],
        "match_rules": [],
        "params": {
            "window_size": 10,
            "time_out": time_out,
            "time_minutes": time_minutes,
        },
        "auto_close": True,
        "close_minutes": 120,
    }


def _create(superuser, name, time_minutes, time_out=True):
    request = _request(
        "post",
        "/alarm_strategy/",
        superuser,
        data=_payload(name, time_minutes, time_out=time_out),
    )
    response = AlarmStrategyModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    return response


def _assert_session_minutes(strategy, minutes):
    assert strategy.params["time_minutes"] == minutes
    assert type(strategy.params["time_minutes"]) is int
    cfg = WindowFactory.create_from_strategy(strategy)
    assert cfg.window_type == WindowType.SESSION
    assert cfg.session_timeout_minutes == minutes
    assert type(cfg.session_timeout_minutes) is int
    end = cfg.get_session_end_time()
    assert end > timezone.now()


@pytest.mark.django_db
@pytest.mark.parametrize("time_minutes", [15, "15"])
def test_save_session_timeout_normalizes_to_int(superuser, time_minutes):
    response = _create(superuser, f"session-{time_minutes}", time_minutes)
    assert response.status_code == status.HTTP_201_CREATED
    strategy = AlarmStrategy.objects.get(name=f"session-{time_minutes}")
    _assert_session_minutes(strategy, 15)


@pytest.mark.django_db
@pytest.mark.parametrize("time_minutes", ["abc", True, 1.5, -1])
def test_save_rejects_unparseable_session_timeout(superuser, time_minutes):
    name = f"bad-{time_minutes}"
    response = _create(superuser, name, time_minutes)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not AlarmStrategy.objects.filter(name=name).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("time_minutes", [0, "0"])
def test_save_zero_session_timeout_keeps_sliding_window(superuser, time_minutes):
    name = f"zero-{time_minutes}"
    response = _create(superuser, name, time_minutes)
    assert response.status_code == status.HTTP_201_CREATED
    strategy = AlarmStrategy.objects.get(name=name)
    assert strategy.params["time_minutes"] == 0
    assert type(strategy.params["time_minutes"]) is int
    cfg = WindowFactory.create_from_strategy(strategy)
    assert cfg.window_type == WindowType.SLIDING
    assert cfg.session_timeout_minutes == 0
    cfg.get_session_end_time()


@pytest.mark.django_db
def test_time_out_off_keeps_existing_integer_minutes(superuser):
    response = _create(superuser, "timeout-off", 15, time_out=False)
    assert response.status_code == status.HTTP_201_CREATED
    strategy = AlarmStrategy.objects.get(name="timeout-off")
    assert strategy.params["time_minutes"] == 15
    assert type(strategy.params["time_minutes"]) is int
    cfg = WindowFactory.create_from_strategy(strategy)
    assert cfg.window_type == WindowType.SLIDING
    assert cfg.session_timeout_minutes == 0


def test_window_factory_numeric_string_opens_session():
    strategy = SimpleNamespace(
        params={"window_size": 10, "time_out": True, "time_minutes": "15"}
    )
    cfg = WindowFactory.create_from_strategy(strategy)
    assert cfg.window_type == WindowType.SESSION
    assert cfg.session_timeout_minutes == 15
    assert type(cfg.session_timeout_minutes) is int
    assert cfg.get_session_end_time() > timezone.now()


@pytest.mark.parametrize(
    "time_minutes",
    [0, "0", -1, True, False, 1.5, "abc"],
)
def test_window_factory_invalid_timeout_stays_on_sliding_window(time_minutes):
    strategy = SimpleNamespace(
        params={"window_size": 10, "time_out": True, "time_minutes": time_minutes}
    )
    cfg = WindowFactory.create_from_strategy(strategy)
    assert cfg.window_type == WindowType.SLIDING
    assert cfg.session_timeout_minutes == 0
    assert type(cfg.session_timeout_minutes) is int
    cfg.get_session_end_time()


def _legacy_string_strategy(name):
    return AlarmStrategy.objects.create(
        name=name,
        strategy_type="smart_denoise",
        team=[1],
        dispatch_team=[1],
        match_rules=[],
        params={"window_size": 10, "time_out": True, "time_minutes": "15"},
    )


@pytest.mark.django_db
def test_legacy_string_timeout_can_compute_session_end():
    strategy = _legacy_string_strategy("legacy-read")
    cfg = WindowFactory.create_from_strategy(strategy)
    assert cfg.session_timeout_minutes == 15
    assert type(cfg.session_timeout_minutes) is int
    assert cfg.get_session_end_time() > timezone.now()


@pytest.mark.django_db
def test_legacy_string_timeout_update_does_not_raise(superuser):
    strategy = _legacy_string_strategy("legacy-update")
    request = _request(
        "patch",
        f"/alarm_strategy/{strategy.id}/",
        superuser,
        data={"description": "仍可修改"},
    )
    response = AlarmStrategyModelViewSet.as_view({"patch": "partial_update"})(
        request, pk=str(strategy.id)
    )
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    strategy.refresh_from_db()
    assert strategy.description == "仍可修改"
    assert strategy.params["time_minutes"] == 15
    assert type(strategy.params["time_minutes"]) is int


@pytest.mark.django_db
def test_legacy_string_timeout_delete_does_not_raise(superuser):
    strategy = _legacy_string_strategy("legacy-delete")
    request = _request("delete", f"/alarm_strategy/{strategy.id}/", superuser)
    response = AlarmStrategyModelViewSet.as_view({"delete": "destroy"})(
        request, pk=str(strategy.id)
    )
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert not AlarmStrategy.objects.filter(id=strategy.id).exists()
