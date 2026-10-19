"""注册表 fail-closed 契约测试（unit，无 DB）。"""

import json
import logging

import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework import serializers

from apps.core.openapi import catalog
from apps.core.openapi.dispatcher import dispatch
from apps.core.openapi.identity import CREDENTIAL_JWT, CallerIdentity
from apps.core.openapi.registry import OpenAPIRegistry
from apps.core.openapi.serializers import OpenAPIRequestSerializer

pytestmark = pytest.mark.unit


class GoodSerializer(OpenAPIRequestSerializer):
    name = serializers.CharField()


class TeamFieldSerializer(OpenAPIRequestSerializer):
    team = serializers.IntegerField()


class UserFieldSerializer(OpenAPIRequestSerializer):
    user = serializers.CharField()


class GoodResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()


class UnsupportedRequestSerializer(OpenAPIRequestSerializer):
    amount = serializers.DecimalField(max_digits=8, decimal_places=2)


class UnsupportedResponseSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=8, decimal_places=2)


SensitiveUnsupportedField = type("CATALOG_SENSITIVE_SENTINEL", (serializers.Field,), {})


class SensitiveUnsupportedRequestSerializer(OpenAPIRequestSerializer):
    secret = SensitiveUnsupportedField()


class SensitiveUnsupportedResponseSerializer(serializers.Serializer):
    secret = SensitiveUnsupportedField()


def team_list_func(name, *, team=None):
    return {}


def user_info_func(name, user_info=None):
    return {}


def team_list_with_user_func(name, *, team=None, user_info=None):
    return {}


class AnchorSerializer(OpenAPIRequestSerializer):
    name = serializers.CharField()
    team = serializers.IntegerField(required=False)


def no_identity_func(name):
    return {}


def decimal_func(amount, *, team=None):
    return {"amount": str(amount), "team": team}


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


def test_response_serializer_is_optional_until_endpoint_contract_is_migrated():
    reg = OpenAPIRegistry()
    endpoint = register(reg)
    assert endpoint.response_serializer_class is None

    endpoint = register(
        OpenAPIRegistry(),
        path="demo/with-response",
        response_serializer_class=GoodResponseSerializer,
    )
    assert endpoint.response_serializer_class is GoodResponseSerializer


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
        # 锚点式必须声明 team 字段，否则 JWT 调用方永久 400 且无法补传
        {"inject": "user_info", "func": user_info_func},
        # 声明 permission 却漏 permission_app 会导致非超管全量 403（superuser 直通掩盖）
        {"permission": "patch_target-View"},
        {"team_free": True, "inject": "team_list"},
    ],
)
def test_fail_closed(overrides):
    reg = OpenAPIRegistry()
    with pytest.raises(ImproperlyConfigured):
        register(reg, **overrides)


def test_non_serializer_response_contract_fails_registration():
    with pytest.raises(ImproperlyConfigured, match="response_schema"):
        register(OpenAPIRegistry(), response_serializer_class=object)


def test_schema_projection_support_does_not_block_registration_or_dispatch():
    endpoint = register(
        OpenAPIRegistry(),
        serializer_class=UnsupportedRequestSerializer,
        response_serializer_class=UnsupportedResponseSerializer,
        func=decimal_func,
    )

    response = dispatch(
        CallerIdentity(user="tester", domain="example.com", credential_type=CREDENTIAL_JWT, team_ids=[7]),
        endpoint,
        {"amount": "12.34"},
    )

    assert response.status_code == 200
    assert json.loads(response.content) == {"result": True, "data": {"amount": "12.34", "team": [7]}}


@pytest.mark.parametrize(
    ("serializer_class", "response_serializer_class"),
    [
        (SensitiveUnsupportedRequestSerializer, None),
        (GoodSerializer, SensitiveUnsupportedResponseSerializer),
    ],
)
def test_schema_projection_failure_only_omits_the_affected_endpoint(
    monkeypatch,
    caplog,
    serializer_class,
    response_serializer_class,
):
    reg = OpenAPIRegistry()
    broken = register(
        reg,
        path="demo/things",
        serializer_class=serializer_class,
        response_serializer_class=response_serializer_class,
    )
    register(reg, path="demo/things", method="POST")
    register(reg, path="other/items")
    monkeypatch.setattr(catalog.default_registry, "endpoints", reg.endpoints)
    monkeypatch.setattr(
        "apps.core.openapi.renderer.get_external_catalog",
        lambda: [{"name": "itsm", "doc_url": "http://itsm.example/docs"}],
    )

    with caplog.at_level(logging.WARNING, logger="openapi"):
        result = catalog.build_docs_catalog()

    assert result == {
        "services": [
            {
                "name": "demo",
                "kind": "internal",
                "endpoints": [
                    {
                        "path": "demo/things",
                        "method": "POST",
                        "summary": "",
                        "inject": "team_list",
                        "permission": "",
                        "request_schema": catalog.serializer_to_schema(GoodSerializer),
                        "response_schema": None,
                    }
                ],
            },
            {
                "name": "other",
                "kind": "internal",
                "endpoints": [
                    {
                        "path": "other/items",
                        "method": "GET",
                        "summary": "",
                        "inject": "team_list",
                        "permission": "",
                        "request_schema": catalog.serializer_to_schema(GoodSerializer),
                        "response_schema": None,
                    }
                ],
            },
            {"name": "itsm", "kind": "external", "doc_url": "http://itsm.example/docs"},
        ]
    }
    records = [record for record in caplog.records if record.name == "openapi"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.msg == ("event=openapi_catalog_endpoint_skipped method=%s path=%s " "failed_stage=schema_projection error_type=%s")
    assert record.args == (broken.method, broken.path, "ValueError")
    assert record.getMessage() == (
        "event=openapi_catalog_endpoint_skipped method=GET path=demo/things " "failed_stage=schema_projection error_type=ValueError"
    )
    assert "CATALOG_SENSITIVE_SENTINEL" not in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR or record.exc_info]


def test_catalog_does_not_swallow_unexpected_projection_errors(monkeypatch):
    endpoint = register(OpenAPIRegistry())
    failure = RuntimeError("unexpected projection failure")

    def fail_projection(_serializer_class):
        raise failure

    monkeypatch.setattr(catalog.default_registry, "endpoints", lambda: [endpoint])
    monkeypatch.setattr(catalog, "serializer_to_schema", fail_projection)

    with pytest.raises(RuntimeError) as raised:
        catalog.build_docs_catalog()

    assert raised.value is failure


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
    endpoint = register(reg, inject="user_info", func=user_info_func, serializer_class=AnchorSerializer)
    assert endpoint.inject == "user_info"


def test_team_list_with_user_registration_requires_both_trusted_parameters():
    reg = OpenAPIRegistry()
    endpoint = register(reg, inject="team_list_with_user", func=team_list_with_user_func)
    assert endpoint.inject == "team_list_with_user"

    with pytest.raises(ImproperlyConfigured):
        register(OpenAPIRegistry(), inject="team_list_with_user", func=team_list_func)


def test_permission_with_app_accepted():
    reg = OpenAPIRegistry()
    endpoint = register(reg, permission="patch_target-View", permission_app="patch")
    assert endpoint.permission_app == "patch"
