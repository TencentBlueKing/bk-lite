from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer

_TRUSTED_INSTANCES = {}


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
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.InstanceManage.query_entity_by_uuids",
        lambda uuids: [_TRUSTED_INSTANCES[inst_uuid] for inst_uuid in uuids],
    )
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.InstanceManage._has_topology_view_permission",
        lambda *args, **kwargs: True,
    )


def _payload(instances, params=None, credential=None):
    instances = [
        {
            **item,
            "inst_uuid": item.get("inst_uuid") or f"63e4a53{index + 1}-b6bb-43cc-9eae-8eb8a09f795e",
        }
        for index, item in enumerate(instances)
    ]
    return {
        "name": "network-config",
        "task_type": CollectPluginTypes.CONFIG_FILE,
        "driver_type": CollectDriverTypes.PROTOCOL,
        "model_id": "network_config_file",
        "is_interval": True,
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
    global _TRUSTED_INSTANCES
    _TRUSTED_INSTANCES = {item["inst_uuid"]: dict(item) for item in payload.get("instances", [])}
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    return CollectModelSerializer(data=payload, context={"request": request})


def test_network_config_file_serializer_accepts_supported_branded_device():
    serializer = _serializer(_payload([{"model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}]))

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["driver_type"] == CollectDriverTypes.PROTOCOL
    assert serializer.validated_data["params"]["commands"] == "show running-config\nshow version"
    assert serializer.validated_data["instances"][0]["device_type"] == "cisco_ios"


def test_network_config_file_serializer_rejects_empty_brand():
    serializer = _serializer(_payload([{"model_id": "switch", "brand": "", "ip_addr": "10.0.0.1"}]))

    assert not serializer.is_valid()
    assert "厂商" in str(serializer.errors)


def test_network_config_file_serializer_rejects_dangerous_command():
    serializer = _serializer(
        _payload(
            [{"model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}],
            params={"commands": "show version\nreload"},
        )
    )

    assert not serializer.is_valid()
    assert "高危" in str(serializer.errors)


def test_network_config_file_serializer_derives_enable_mode_from_enable_password():
    serializer = _serializer(
        _payload(
            [{"model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}],
            params={"need_enable": False},
            credential=[{"username": "admin", "password": "secret", "enable_password": "enable-secret", "port": 22}],
        )
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["params"]["need_enable"] is True


def test_network_config_file_serializer_disables_enable_mode_without_enable_password():
    serializer = _serializer(
        _payload(
            [{"model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}],
            params={"need_enable": True},
            credential=[{"username": "admin", "password": "secret", "port": 22}],
        )
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["params"]["need_enable"] is False


def test_network_config_file_serializer_rejects_non_periodic_task():
    payload = _payload([{"model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}])
    payload["is_interval"] = False

    serializer = _serializer(payload)

    assert not serializer.is_valid()
    assert "仅支持周期执行" in str(serializer.errors)
