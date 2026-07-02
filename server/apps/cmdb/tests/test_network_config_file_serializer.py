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
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *args, **kwargs: {})
    monkeypatch.setattr(CollectModelSerializer.Meta, "validators", [], raising=False)


def _payload(instances, params=None, credential=None):
    return {
        "name": "network-config",
        "task_type": CollectPluginTypes.CONFIG_FILE,
        "driver_type": CollectDriverTypes.PROTOCOL,
        "model_id": "network_config_file",
        "access_point": [{"id": 1}],
        "instances": instances,
        "cycle_value_type": "interval",
        "cycle_value": "60",
        "scan_cycle": "60",
        "timeout": 60,
        "team": [1],
        "params": {
            "config_name": "running-config",
            "commands": "show running-config\nshow version",
            "need_enable": False,
            **(params or {}),
        },
        "credential": credential or [{"username": "admin", "password": "secret", "port": 22}],
    }


def _serializer(payload):
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    return CollectModelSerializer(data=payload, context={"request": request})


def test_network_config_file_serializer_accepts_supported_branded_device():
    serializer = _serializer(_payload([{"_id": "1", "model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}]))

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["driver_type"] == CollectDriverTypes.PROTOCOL
    assert serializer.validated_data["params"]["commands"] == "show running-config\nshow version"
    assert serializer.validated_data["instances"][0]["device_type"] == "cisco_ios"


def test_network_config_file_serializer_rejects_empty_brand():
    serializer = _serializer(_payload([{"_id": "1", "model_id": "switch", "brand": "", "ip_addr": "10.0.0.1"}]))

    assert not serializer.is_valid()
    assert "厂商" in str(serializer.errors)


def test_network_config_file_serializer_rejects_dangerous_command():
    serializer = _serializer(
        _payload(
            [{"_id": "1", "model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}],
            params={"commands": "show version\nreload"},
        )
    )

    assert not serializer.is_valid()
    assert "高危" in str(serializer.errors)


def test_network_config_file_serializer_requires_enable_password_when_enable_is_true():
    serializer = _serializer(
        _payload(
            [{"_id": "1", "model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}],
            params={"need_enable": True},
            credential=[{"username": "admin", "password": "secret", "port": 22}],
        )
    )

    assert not serializer.is_valid()
    assert "特权密码" in str(serializer.errors)
