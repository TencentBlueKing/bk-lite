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
                    "inst_name": f"{model_id}-account",
                }
            ],
            "cycle_value_type": "cycle",
            "cycle_value": "5",
            "scan_cycle": "5",
            "timeout": 60,
            "team": [1],
            "params": {},
            "credential": credential,
        },
        context={"request": request},
    )


def test_hwcloud_requires_project_id():
    serializer = _serializer(
        "hwcloud",
        {
            "accessKey": "AK",
            "accessSecret": "SK",
            "regions": {"resource_id": "cn-north-4"},
        },
    )

    assert serializer.is_valid() is False
    assert "credential" in serializer.errors


def test_hwcloud_accepts_and_normalizes_project_id():
    serializer = _serializer(
        "hwcloud",
        {
            "accessKey": "AK",
            "accessSecret": "SK",
            "project_id": " project-123 ",
            "regions": {"resource_id": "cn-north-4"},
        },
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credential"][0]["project_id"] == "project-123"


def test_hwcloud_accepts_service_normalized_credential_pool():
    serializer = _serializer(
        "hwcloud",
        [
            {
                "credential_id": "cred-hwcloud",
                "accessKey": "AK",
                "accessSecret": "SK",
                "project_id": " project-123 ",
                "regions": {"resource_id": "cn-north-4"},
            }
        ],
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credential"] == [
        {
            "credential_id": "cred-hwcloud",
            "accessKey": "AK",
            "accessSecret": "SK",
            "project_id": "project-123",
            "regions": {"resource_id": "cn-north-4"},
        }
    ]


def test_hwcloud_create_rejects_masked_access_keys():
    serializer = _serializer(
        "hwcloud",
        {
            "accessKey": "******",
            "accessSecret": "******",
            "project_id": "project-1",
            "regions": {"resource_id": "cn-north-4"},
        },
    )

    assert serializer.is_valid() is False
    assert set(serializer.errors["credential"]) == {
        "accessKey",
        "accessSecret",
    }


@pytest.mark.parametrize("model_id", ["aliyun_account", "qcloud"])
def test_other_public_clouds_do_not_require_project_id(model_id):
    serializer = _serializer(
        model_id,
        {
            "accessKey": "AK",
            "accessSecret": "SK",
            "regions": {"resource_id": "region-1"},
        },
    )

    assert serializer.is_valid(), serializer.errors
