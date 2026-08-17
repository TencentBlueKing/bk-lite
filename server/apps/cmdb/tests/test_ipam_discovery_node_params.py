# -*- coding: utf-8 -*-
import json
import types

from apps.cmdb.constants.constants import CollectDriverTypes, CollectInputMethod
from apps.cmdb.node_configs.config_factory import NodeParamsFactory

SUBNET_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"


def _fake_task():
    task = types.SimpleNamespace()
    task.id = 321
    task.model_id = "ip"
    task.driver_type = CollectDriverTypes.PROTOCOL
    task.timeout = 90
    task.decrypt_credentials = {}
    task.instances = []
    task.params = {
        "subnet_uuids": [SUBNET_UUID],
        "scan_method": "tcp",
        "ports": [22, 443],
        "reserved_addresses": ["10.0.1.254"],
    }
    task.input_method = CollectInputMethod.SUBNET
    task.access_point = [{"id": "node-1"}]
    task.ip_range = ""
    return task


def test_factory_resolves_ip_discovery_node_params():
    cls = NodeParamsFactory.get_params_class("ip", CollectDriverTypes.PROTOCOL)
    assert cls.supported_model_id == "ip"
    assert cls.plugin_name == "ip_discovery"


def test_ip_discovery_push_params_uses_subnet_scope(monkeypatch):
    from apps.cmdb.node_configs.ipam import ip_discovery

    monkeypatch.setattr(
        ip_discovery.IPDiscoveryNodeParams,
        "_load_subnet_scopes",
        lambda self: [
            {
                "subnet_uuid": SUBNET_UUID,
                "cidr": "10.0.1.0/24",
                "gateway": "10.0.1.1",
                "reserved_addresses": ["10.0.1.1", "10.0.1.254"],
            }
        ],
    )

    node = NodeParamsFactory.get_node_params(_fake_task())
    config = node.main("push")[0]
    headers = node.custom_headers()

    assert config["node_id"] == "node-1"
    assert config["collector_name"] == "Telegraf"
    assert config["type"] == "ip"
    assert headers["cmdbplugin_name"] == "ip_discovery"
    assert headers["cmdbmodel_id"] == "ip"
    assert headers["cmdbexecutor_type"] == "protocol"
    assert headers["cmdbscan_method"] == "tcp"
    assert json.loads(headers["cmdbports"]) == [22, 443]
    assert json.loads(headers["cmdbsubnets"]) == [
        {
            "subnet_uuid": SUBNET_UUID,
            "cidr": "10.0.1.0/24",
            "gateway": "10.0.1.1",
            "reserved_addresses": ["10.0.1.1", "10.0.1.254"],
        }
    ]
    assert config["env_config"] == {}


def test_ip_discovery_accepts_single_subnet_uuid_and_port_value(monkeypatch):
    from apps.cmdb.node_configs.ipam import ip_discovery

    task = _fake_task()
    task.params = {"subnet_uuids": SUBNET_UUID, "scan_method": "tcp", "ports": "22"}
    captured = {}

    def fake_load(self):
        captured["subnet_uuids"] = self._subnet_uuids()
        return []

    monkeypatch.setattr(ip_discovery.IPDiscoveryNodeParams, "_load_subnet_scopes", fake_load)

    node = NodeParamsFactory.get_node_params(task)
    headers = node.custom_headers()

    assert captured["subnet_uuids"] == [SUBNET_UUID]
    assert json.loads(headers["cmdbports"]) == ["22"]


def test_ip_discovery_maps_legacy_subnet_id_before_agent_payload(monkeypatch):
    from apps.cmdb.node_configs.ipam import ip_discovery

    task = _fake_task()
    task.params = {"subnet_ids": [101]}

    class FakeGraph:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query_entity(self, _label, filters):
            assert filters[1] == {"field": "id", "type": "id[]", "value": [101]}
            return ([{"_id": 101, "inst_uuid": SUBNET_UUID, "subnet_address": "10.0.1.0", "subnet_mask": "24"}], 1)

    monkeypatch.setattr(ip_discovery, "GraphClient", FakeGraph)
    node = NodeParamsFactory.get_node_params(task)

    assert node._load_subnet_scopes()[0]["subnet_uuid"] == SUBNET_UUID
