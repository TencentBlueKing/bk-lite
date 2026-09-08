from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer


@pytest.fixture(autouse=True)
def _stub_auth_serializer_dependencies(monkeypatch):
    class _UserQuery:
        @staticmethod
        def values(*args):
            return []

    class _UserManager:
        @staticmethod
        def all():
            return _UserQuery()

    monkeypatch.setattr("apps.core.utils.serializers.User.objects", _UserManager())
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        CollectModelSerializer.Meta,
        "validators",
        [],
        raising=False,
    )


def _serializer(credential, *, protocol="redfish"):
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    return CollectModelSerializer(
        data={
            "name": "redfish-collect",
            "task_type": CollectPluginTypes.PROTOCOL,
            "driver_type": CollectDriverTypes.PROTOCOL,
            "model_id": "physcial_server",
            "access_point": [{"id": 1}],
            "instances": [],
            "ip_range": "10.0.0.8-10.0.0.9",
            "cycle_value_type": "cycle",
            "cycle_value": "5",
            "scan_cycle": "5",
            "timeout": 60,
            "team": [1],
            "params": {"collection_protocol": protocol},
            "credential": [credential],
        },
        context={"request": request},
    )


def test_redfish_credential_defaults_tls_verification_to_enabled():
    serializer = _serializer(
        {
            "username": "Administrator",
            "password": "secret",
            "port": 443,
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credential"] == [
        {
            "username": "Administrator",
            "password": "secret",
            "port": 443,
            "verify_tls": True,
        }
    ]


def test_redfish_credential_preserves_explicitly_disabled_tls_verification():
    serializer = _serializer(
        {
            "username": "Administrator",
            "password": "secret",
            "port": 443,
            "verify_tls": False,
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credential"][0]["verify_tls"] is False


def test_redfish_credential_rejects_non_boolean_tls_verification():
    serializer = _serializer(
        {
            "username": "Administrator",
            "password": "secret",
            "port": 443,
            "verify_tls": "false",
        }
    )

    assert serializer.is_valid() is False
    assert "verify_tls" in serializer.errors["credential"][0]


@pytest.mark.parametrize(
    ("credential", "field"),
    [
        ({"username": "", "password": "secret", "port": 443}, "username"),
        ({"username": "Administrator", "password": "", "port": 443}, "password"),
        ({"username": "Administrator", "password": "secret", "port": 0}, "port"),
        ({"username": "Administrator", "password": "secret", "port": 65536}, "port"),
        ({"username": "Administrator", "password": "secret", "port": "bad"}, "port"),
    ],
)
def test_redfish_credential_rejects_invalid_required_fields(credential, field):
    serializer = _serializer(credential)

    assert serializer.is_valid() is False
    assert field in serializer.errors["credential"][0]


def test_redfish_credential_rejects_unknown_fields():
    serializer = _serializer(
        {
            "username": "Administrator",
            "password": "secret",
            "port": 443,
            "unexpected": "value",
        }
    )

    assert serializer.is_valid() is False
    assert "fields" in serializer.errors["credential"][0]


def test_physical_server_protocol_rejects_unknown_protocol():
    serializer = _serializer(
        {
            "username": "Administrator",
            "password": "secret",
            "port": 443,
        },
        protocol="not-redfish",
    )

    assert serializer.is_valid() is False
    assert "collection_protocol" in serializer.errors["params"]


def test_ipmi_credential_is_validated_and_normalized():
    serializer = _serializer(
        {
            "user": " admin ",
            "password": "secret",
            "ipmi_port": "623",
            "privilege": "administrator",
        },
        protocol="ipmi",
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credential"] == [
        {
            "username": "admin",
            "password": "secret",
            "port": 623,
            "privilege": "administrator",
        }
    ]
