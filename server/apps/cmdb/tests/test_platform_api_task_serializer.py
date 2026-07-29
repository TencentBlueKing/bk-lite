from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
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


def _serializer(model_id, credential):
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    return CollectModelSerializer(
        data={
            "name": f"{model_id}-collect",
            "task_type": CollectPluginTypes.CLOUD,
            "driver_type": CollectDriverTypes.PROTOCOL,
            "model_id": model_id,
            "access_point": [{"id": 1}],
            "instances": [
                {
                    "_id": f"{model_id}-1",
                    "model_id": model_id,
                    "inst_name": f"{model_id}-target",
                    "ip_addr": "10.0.0.8",
                }
            ],
            "cycle_value_type": "cycle",
            "cycle_value": "5",
            "scan_cycle": "5",
            "timeout": 60,
            "team": [1],
            "params": {},
            "credential": [credential],
        },
        context={"request": request},
    )


@pytest.mark.parametrize("model_id,port", [("fusioninsight", 443), ("storage", 8088)])
def test_platform_api_accepts_username_password_and_tls(model_id, port):
    serializer = _serializer(
        model_id,
        {
            "username": " collector ",
            "password": "secret",
            "port": port,
            "verify_tls": True,
        },
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credential"][0]["username"] == "collector"


def test_platform_api_converts_legacy_aksk_to_username_password():
    serializer = _serializer(
        "fusioninsight",
        {
            "credential_id": "cred-legacy",
            "accessKey": "legacy-user",
            "accessSecret": "legacy-secret",
            "port": 9443,
            "verify_tls": False,
        },
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credential"] == [
        {
            "credential_id": "cred-legacy",
            "username": "legacy-user",
            "password": "legacy-secret",
            "port": 9443,
            "verify_tls": False,
        }
    ]


def test_fusioninsight_decrypts_legacy_encrypted_access_key():
    task = CollectModels(
        model_id="fusioninsight",
        driver_type=CollectDriverTypes.PROTOCOL,
        credential=[
            {
                "accessKey": CollectModels.encrypt_password("legacy-user"),
                "accessSecret": CollectModels.encrypt_password("legacy-secret"),
            }
        ],
    )

    assert task.decrypt_credentials == [
        {
            "accessKey": "legacy-user",
            "accessSecret": "legacy-secret",
        }
    ]


@pytest.mark.parametrize(
    "credential",
    [
        {"username": "", "password": "secret", "port": 443, "verify_tls": True},
        {"username": "user", "password": "", "port": 443, "verify_tls": True},
        {"username": "user", "password": "secret", "port": 0, "verify_tls": True},
        {"username": "user", "password": "secret", "port": 443, "verify_tls": "false"},
        {
            "username": "user",
            "password": "secret",
            "port": 443,
            "verify_tls": True,
            "unexpected": "wrong-contract",
        },
    ],
)
def test_platform_api_rejects_invalid_or_cloud_aksk_contract(credential):
    serializer = _serializer("fusioninsight", credential)

    assert serializer.is_valid() is False
    assert "credential" in serializer.errors
