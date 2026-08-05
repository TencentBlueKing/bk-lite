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


def _serializer(credential, **overrides):
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    data = {
        "name": "influxdb-collect",
        "task_type": CollectPluginTypes.PROTOCOL,
        "driver_type": CollectDriverTypes.PROTOCOL,
        "model_id": "influxdb",
        "access_point": [{"id": 1}],
        "instances": [
            {
                "_id": "influx-1",
                "model_id": "influxdb",
                "inst_name": "influx.local",
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
    }
    data.update(overrides)
    return CollectModelSerializer(
        data=data,
        context={"request": request},
    )


def test_influxdb_accepts_http_without_operator_token():
    serializer = _serializer(
        {"scheme": "http", "port": 8086, "verify_tls": True}
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credential"] == [
        {"scheme": "http", "port": 8086, "verify_tls": True}
    ]


def test_influxdb_create_rejects_masked_operator_token():
    serializer = _serializer(
        {
            "scheme": "https",
            "port": 8086,
            "verify_tls": True,
            "token": "******",
        }
    )

    assert serializer.is_valid() is False
    assert "token" in serializer.errors["credential"]


@pytest.mark.parametrize(
    "target",
    [
        {
            "instances": [
                {"_id": "influx-1", "ip_addr": "10.0.0.8"},
                {"_id": "influx-2", "ip_addr": "10.0.0.9"},
            ]
        },
        {
            "instances": [],
            "ip_range": "10.0.0.1-10.0.0.3",
        },
    ],
)
def test_influxdb_requires_exactly_one_endpoint(target):
    serializer = _serializer(
        {"scheme": "http", "port": 8086, "verify_tls": True},
        **target,
    )

    assert serializer.is_valid() is False
    assert "instances" in serializer.errors


@pytest.mark.parametrize(
    "credential",
    [
        {"scheme": "ftp", "port": 8086, "verify_tls": True},
        {"scheme": "https", "port": 0, "verify_tls": True},
        {"scheme": "https", "port": 8086, "verify_tls": "maybe"},
        {
            "scheme": "https",
            "port": 8086,
            "verify_tls": True,
            "username": "must-not-be-used",
        },
    ],
)
def test_influxdb_rejects_invalid_connection_contract(credential):
    serializer = _serializer(credential)

    assert serializer.is_valid() is False
    assert "credential" in serializer.errors
