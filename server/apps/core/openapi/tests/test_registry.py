"""注册表 fail-closed 契约测试（unit，无 DB）。"""

import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework import serializers

from apps.core.openapi.registry import OpenAPIRegistry
from apps.core.openapi.serializers import OpenAPIRequestSerializer

pytestmark = pytest.mark.unit


class GoodSerializer(OpenAPIRequestSerializer):
    name = serializers.CharField()


class TeamFieldSerializer(OpenAPIRequestSerializer):
    team = serializers.IntegerField()


class UserFieldSerializer(OpenAPIRequestSerializer):
    user = serializers.CharField()


def team_list_func(name, *, team=None):
    return {}


def user_info_func(name, user_info=None):
    return {}


def no_identity_func(name):
    return {}


def register(reg, **overrides):
    params = dict(
        path="demo/things",
        method="GET",
        serializer_class=GoodSerializer,
        func=team_list_func,
        inject="team_list",
    )
    params.update(overrides)
    return reg.register(**params)


def test_valid_registration_and_find():
    reg = OpenAPIRegistry()
    register(reg)
    assert reg.find("demo", "things", "GET") is not None
    assert reg.find("demo", "things", "POST") is None
    assert reg.services() == ["demo"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"serializer_class": None},
        {"serializer_class": object},
        {"path": "demo"},
        {"path": "_demo/things"},
        {"path": "Demo/things"},
        {"method": "PATCH"},
        {"inject": "bogus"},
        {"inject": None},
        {"inject": "team_list", "func": no_identity_func},
        {"inject": "team_list", "serializer_class": TeamFieldSerializer},
        {"inject": "user_info", "func": no_identity_func},
        {"inject": "user_info", "func": user_info_func, "serializer_class": UserFieldSerializer},
        {"team_free": True, "inject": "team_list"},
    ],
)
def test_fail_closed(overrides):
    reg = OpenAPIRegistry()
    with pytest.raises(ImproperlyConfigured):
        register(reg, **overrides)


def test_duplicate_path_rejected():
    reg = OpenAPIRegistry()
    register(reg)
    with pytest.raises(ImproperlyConfigured):
        register(reg)


def test_team_free_without_inject_allowed():
    reg = OpenAPIRegistry()
    endpoint = register(reg, team_free=True, inject=None, func=no_identity_func)
    assert endpoint.team_free is True


def test_user_info_registration():
    reg = OpenAPIRegistry()
    endpoint = register(reg, inject="user_info", func=user_info_func)
    assert endpoint.inject == "user_info"
