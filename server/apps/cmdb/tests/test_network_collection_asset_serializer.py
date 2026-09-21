from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer

SWITCH_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
ROUTER_UUID = "4c6643d2-4dc5-4a2a-8f24-3af72f33f7bc"
HOST_UUID = "7f1d3c20-0b11-4a8c-9e3a-21d4b6c8e901"
FIREWALL_UUID = "a2b3c4d5-e6f7-4890-abcd-1234567890ab"
LOADBALANCE_UUID = "b3c4d5e6-f7a8-4901-bcde-234567890abc"

INSTANCE_CATALOG = {
    SWITCH_UUID: {"model_id": "switch", "inst_name": "10.0.0.1-switch", "ip_addr": "10.0.0.1"},
    ROUTER_UUID: {"model_id": "router", "inst_name": "10.0.0.2-router", "ip_addr": "10.0.0.2"},
    HOST_UUID: {"model_id": "host", "inst_name": "host-a", "ip_addr": "10.0.0.8"},
    FIREWALL_UUID: {"model_id": "firewall", "inst_name": "10.0.0.3-firewall", "ip_addr": "10.0.0.3"},
    LOADBALANCE_UUID: {"model_id": "loadbalance", "inst_name": "10.0.0.4-lb", "ip_addr": "10.0.0.4"},
}


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
        "apps.cmdb.serializers.collect_serializer.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.InstanceManage._has_topology_view_permission",
        lambda *args, **kwargs: True,
    )

    def _query(uuids):
        rows = []
        for inst_uuid in uuids:
            catalog = INSTANCE_CATALOG.get(inst_uuid)
            if catalog is None:
                continue
            rows.append({"inst_uuid": inst_uuid, **catalog})
        return rows

    monkeypatch.setattr("apps.cmdb.serializers.collect_serializer.InstanceManage.query_entity_by_uuids", _query)


def _serializer(*, instances, ip_range="", extra=None, instance=None):
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    data = {
        "name": "network-cross-model",
        "task_type": CollectPluginTypes.SNMP,
        "driver_type": CollectDriverTypes.PROTOCOL,
        "model_id": "network",
        "cycle_value_type": "cycle",
        "instances": instances,
        "ip_range": ip_range,
        "access_point": [{"id": 1}],
        "credential": [{"version": "v2", "snmp_port": 161, "community": "public"}],
        "timeout": 60,
        "params": {},
        "team": [1],
    }
    if extra:
        data.update(extra)
    return CollectModelSerializer(instance, data=data, context={"request": request})


def test_network_task_accepts_switch_and_router_snapshots():
    serializer = _serializer(
        instances=[
            {"inst_uuid": SWITCH_UUID},
            {"inst_uuid": ROUTER_UUID},
        ]
    )
    assert serializer.is_valid(), serializer.errors
    snapshots = serializer.validated_data["instances"]
    assert [(item["model_id"], item["ip_addr"]) for item in snapshots] == [
        ("switch", "10.0.0.1"),
        ("router", "10.0.0.2"),
    ]


@pytest.mark.parametrize("inst_uuid", [SWITCH_UUID, ROUTER_UUID, FIREWALL_UUID, LOADBALANCE_UUID])
def test_each_allowed_network_model_can_be_selected_alone(inst_uuid):
    serializer = _serializer(instances=[{"inst_uuid": inst_uuid}])
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["instances"][0]["model_id"] == INSTANCE_CATALOG[inst_uuid]["model_id"]


def test_network_task_rejects_host_instance():
    serializer = _serializer(instances=[{"inst_uuid": HOST_UUID}])
    assert serializer.is_valid() is False
    assert "instances" in serializer.errors


def test_network_ip_range_skips_asset_model_check():
    serializer = _serializer(instances=[], ip_range="10.0.0.1-10.0.0.10")
    assert serializer.is_valid(), serializer.errors


def test_network_task_rejects_missing_manage_ip(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.InstanceManage.query_entity_by_uuids",
        lambda uuids: [
            {"inst_uuid": SWITCH_UUID, "model_id": "switch", "inst_name": "sw", "ip_addr": ""},
        ],
    )
    serializer = _serializer(instances=[{"inst_uuid": SWITCH_UUID}])
    assert serializer.is_valid() is False
    assert "instances" in serializer.errors


def test_update_rejects_duplicate_manage_ip(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.InstanceManage.query_entity_by_uuids",
        lambda uuids: [
            {"inst_uuid": SWITCH_UUID, "model_id": "switch", "inst_name": "sw", "ip_addr": "10.0.0.1"},
            {"inst_uuid": ROUTER_UUID, "model_id": "router", "inst_name": "rt", "ip_addr": " 10.0.0.1 "},
        ],
    )
    existing = CollectModels(
        name="existing-network",
        task_type=CollectPluginTypes.SNMP,
        driver_type=CollectDriverTypes.PROTOCOL,
        model_id="network",
        timeout=60,
    )
    serializer = _serializer(
        instances=[{"inst_uuid": SWITCH_UUID}, {"inst_uuid": ROUTER_UUID}],
        instance=existing,
    )
    assert serializer.is_valid() is False
    assert "instances" in serializer.errors
