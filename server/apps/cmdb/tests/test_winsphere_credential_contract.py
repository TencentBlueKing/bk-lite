from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer
from apps.cmdb.services.collect_credential_contract import (
    get_collect_credential_contract,
)


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
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.get_collect_object_meta",
        lambda model_id, driver_type=None: (
            {"model_id": model_id, "type": driver_type}
            if model_id == "winsphere"
            else {}
        ),
    )


def _payload(credential):
    return {
        "name": "winsphere-collect",
        "task_type": CollectPluginTypes.CLOUD,
        "driver_type": CollectDriverTypes.PROTOCOL,
        "model_id": "winsphere",
        "access_point": [{"id": 1}],
        "instances": [
            {
                "_id": "winsphere-1",
                "model_id": "winsphere",
                "inst_name": "winsphere-prod",
                "management_address": "WS.EXAMPLE.COM.",
            }
        ],
        "cycle_value_type": "cycle",
        "cycle_value": "5",
        "scan_cycle": "5",
        "timeout": 600,
        "team": [1],
        "params": {},
        "credential": credential,
    }


def _serializer(credential, *, instance=None):
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    return CollectModelSerializer(
        instance=instance,
        data=_payload(credential),
        context={"request": request},
    )


def test_winsphere_contract_is_static_metadata_not_a_database_model():
    contract = get_collect_credential_contract("winsphere")

    assert contract["schema_version"] == 1
    assert contract["task_type"] == CollectPluginTypes.CLOUD
    assert contract["driver_type"] == CollectDriverTypes.PROTOCOL
    assert contract["allow_multiple"] is False
    assert contract["allow_unknown_fields"] is False
    assert contract["encrypted_fields"] == ["password"]
    assert [field["key"] for field in contract["fields"]] == [
        "user",
        "password",
        "https_port",
        "verify_tls",
    ]
    assert contract["fields"][2]["default"] == 443
    assert contract["fields"][2]["min"] == 1
    assert contract["fields"][2]["max"] == 65535
    assert all(
        "help" not in field
        and "help_key" not in field
        and "label_key" not in field
        for field in contract["fields"]
    )


def test_winsphere_serializer_applies_defaults_and_normalizes_endpoint():
    serializer = _serializer({"user": " api-reader ", "password": "secret"})

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credential"] == [
        {
            "user": "api-reader",
            "password": "secret",
            "https_port": 443,
            "verify_tls": False,
        }
    ]
    assert serializer.validated_data["instances"][0]["management_address"] == (
        "ws.example.com"
    )
    assert serializer.validated_data["instances"][0]["endpoint"] == (
        "https://ws.example.com:443"
    )


def test_winsphere_serializer_rejects_task_when_enterprise_capability_is_disabled(
    monkeypatch,
):
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.get_collect_object_meta",
        lambda *args, **kwargs: {},
    )
    serializer = _serializer({"user": "reader", "password": "secret"})

    assert serializer.is_valid() is False
    assert "model_id" in serializer.errors


def test_winsphere_serializer_rejects_non_protocol_driver():
    payload = _payload({"user": "reader", "password": "secret"})
    payload["driver_type"] = CollectDriverTypes.JOB
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    serializer = CollectModelSerializer(
        data=payload,
        context={"request": request},
    )

    assert serializer.is_valid() is False
    assert "driver_type" in serializer.errors


def test_winsphere_serializer_rejects_non_cloud_task_type():
    payload = _payload({"user": "reader", "password": "secret"})
    payload["task_type"] = CollectPluginTypes.HOST
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    serializer = CollectModelSerializer(
        data=payload,
        context={"request": request},
    )

    assert serializer.is_valid() is False
    assert "task_type" in serializer.errors


def test_winsphere_serializer_rejects_ip_range_alongside_management_endpoint():
    payload = _payload({"user": "reader", "password": "secret"})
    payload["ip_range"] = "10.0.0.10"
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    serializer = CollectModelSerializer(
        data=payload,
        context={"request": request},
    )

    assert serializer.is_valid() is False
    assert "ip_range" in serializer.errors


@pytest.mark.parametrize(
    "management_address",
    [
        "ws.example.com:8443",
        "https://ws.example.com",
        "ws.example.com/path",
        "ws.example.com?query=1",
        "2001:db8::1",
        "bad host",
        "-bad.example.com",
        "bad..example.com",
    ],
)
def test_winsphere_serializer_rejects_non_host_management_address(
    management_address,
):
    payload = _payload({"user": "reader", "password": "secret"})
    payload["instances"][0]["management_address"] = management_address
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    serializer = CollectModelSerializer(
        data=payload,
        context={"request": request},
    )

    assert serializer.is_valid() is False
    assert "instances" in serializer.errors


@pytest.mark.parametrize(
    "credential",
    [
        [],
        [
            {
                "user": "one",
                "password": "secret",
                "https_port": 443,
                "verify_tls": False,
            },
            {
                "user": "two",
                "password": "secret",
                "https_port": 443,
                "verify_tls": False,
            },
        ],
        {"user": "", "password": "secret"},
        {"user": "reader", "password": ""},
        {"user": "reader", "password": "secret", "https_port": 0},
        {
            "user": "reader",
            "password": "secret",
            "verify_tls": "false",
        },
        {
            "user": "reader",
            "password": "secret",
            "username": "wrong-contract",
        },
    ],
)
def test_winsphere_serializer_rejects_invalid_contract(credential):
    serializer = _serializer(credential)

    assert serializer.is_valid() is False
    assert "credential" in serializer.errors


def test_winsphere_update_preserves_existing_encrypted_password():
    instance = SimpleNamespace(
        model_id="winsphere",
        task_type=CollectPluginTypes.CLOUD,
        credential=[
            {
                "credential_id": "cred-existing",
                "user": "old-reader",
                "password": "enc:existing-secret",
                "https_port": 443,
                "verify_tls": False,
            }
        ],
        params={},
    )
    serializer = _serializer(
        {
            "credential_id": "cred-existing",
            "user": "new-reader",
            "https_port": 8443,
            "verify_tls": True,
        },
        instance=instance,
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credential"][0]["password"] == (
        "enc:existing-secret"
    )


def test_winsphere_update_treats_api_password_mask_as_unchanged():
    instance = SimpleNamespace(
        model_id="winsphere",
        task_type=CollectPluginTypes.CLOUD,
        credential=[
            {
                "user": "old-reader",
                "password": "enc:existing-secret",
                "https_port": 443,
                "verify_tls": False,
            }
        ],
        params={},
    )
    serializer = _serializer(
        {
            "user": "new-reader",
            "password": "******",
            "https_port": 443,
            "verify_tls": False,
        },
        instance=instance,
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credential"][0]["password"] == (
        "enc:existing-secret"
    )


def test_winsphere_create_rejects_api_password_mask():
    serializer = _serializer(
        {
            "user": "reader",
            "password": "******",
        }
    )

    assert serializer.is_valid() is False
    assert "password" in serializer.errors["credential"]


def test_winsphere_partial_update_reuses_existing_endpoint_and_credential():
    instance = SimpleNamespace(
        model_id="winsphere",
        task_type=CollectPluginTypes.CLOUD,
        driver_type=CollectDriverTypes.PROTOCOL,
        credential=[
            {
                "user": "reader",
                "password": "enc:existing-secret",
                "https_port": 8443,
                "verify_tls": True,
            }
        ],
        instances=[
            {
                "_id": "winsphere-1",
                "model_id": "winsphere",
                "inst_name": "winsphere-prod",
                "management_address": "WS.EXAMPLE.COM.",
            }
        ],
        params={},
    )
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    serializer = CollectModelSerializer(
        instance=instance,
        data={"name": "renamed"},
        partial=True,
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["instances"][0]["endpoint"] == (
        "https://ws.example.com:8443"
    )


@pytest.mark.django_db
def test_winsphere_password_is_encrypted_at_rest_and_masked_in_api():
    task = CollectModels.objects.create(
        name="winsphere-encryption-contract",
        task_type=CollectPluginTypes.CLOUD,
        driver_type=CollectDriverTypes.PROTOCOL,
        model_id="winsphere",
        cycle_value_type="cycle",
        instances=[],
        access_point={},
        credential=[
            {
                "user": "reader",
                "password": "plain-secret",
                "https_port": 443,
                "verify_tls": False,
            }
        ],
    )
    task.refresh_from_db()

    assert task.credential[0]["password"].startswith("enc:")
    assert "plain-secret" not in task.credential[0]["password"]

    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    representation = CollectModelSerializer(
        instance=task,
        context={"request": request},
    ).data
    assert representation["credential"][0]["password"] == "******"
