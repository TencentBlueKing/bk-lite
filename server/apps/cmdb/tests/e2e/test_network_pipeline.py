"""Network 网络设备 SNMP 采集端到端流水线测试 —— network 大类代表。

特点：
  - 走 SNMP 协议而非 SSH/HTTP
  - 通过 sysobjectid 在 OidMapping 表查"设备型号/品牌/类型"
  - device_type 决定 model_id（switch / router / firewall…）
  - inst_name 格式：{ip}-{device_type}
"""
import jsonschema
import pytest

from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics


NETWORK_SYSTEM_METRIC = "network_system_info_gauge"
NETWORK_INTERFACE_METRIC = "network_interfaces_info_gauge"
NETWORK_TOPOLOGY_METRIC = "network_topo_info_gauge"
NETWORK_TOPOLOGY_FACTS_METRIC = "network_topology_facts_info_gauge"


def _build_metric(metric_name, instance_id, value="1", **metric):
    return {
        "metric": {"__name__": metric_name, "instance_id": instance_id, **metric},
        "value": [9999999999, value],
    }


def _build_network_vm_response(*extra_metrics):
    dev1 = "snmp-task-01-10.0.0.1"
    dev2 = "snmp-task-01-10.0.0.2"
    base_metrics = [
        _build_metric(
            NETWORK_SYSTEM_METRIC,
            dev1,
            ip_addr="10.0.0.1",
            sysname="edge-sw-1",
            sysobjectid="1.3.6.1.4.1.9.1.1208",
            port="161",
        ),
        _build_metric(
            NETWORK_SYSTEM_METRIC,
            dev2,
            ip_addr="10.0.0.2",
            sysname="dist-sw-1",
            sysobjectid="1.3.6.1.4.1.9.1.1208",
            port="161",
        ),
        _build_metric(
            NETWORK_INTERFACE_METRIC,
            dev1,
            index="101",
            description="GigabitEthernet1/0/1",
            alias="edge-uplink",
            mac_address="00aabbccdd01",
            oper_status="1",
        ),
        _build_metric(
            NETWORK_INTERFACE_METRIC,
            dev2,
            index="202",
            description="GigabitEthernet1/0/24",
            alias="dist-downlink",
            mac_address="00aabbccdd02",
            oper_status="1",
        ),
    ]
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [*base_metrics, *extra_metrics],
        },
    }


def _run_network_pipeline(monkeypatch, vm_resp, *, topo_enabled, sql_calls=None):
    def fake_query(self, sql, timeout=60):
        if sql_calls is not None:
            sql_calls.append(sql)
        return vm_resp

    monkeypatch.setattr("apps.cmdb.collection.query_vm.Collection.query", fake_query)

    oid_map = {
        "1.3.6.1.4.1.9.1.1208": {
            "oid": "1.3.6.1.4.1.9.1.1208",
            "model": "Cisco Catalyst 3850",
            "brand": "Cisco",
            "device_type": "switch",
            "built_in": True,
        }
    }
    monkeypatch.setattr(CollectNetworkMetrics, "get_oid_map", staticmethod(lambda: oid_map))

    from types import SimpleNamespace

    fake_task = SimpleNamespace(id=7001, is_network_topo=topo_enabled, instances=[])
    monkeypatch.setattr(CollectNetworkMetrics, "get_collect_inst", lambda self: fake_task)
    monkeypatch.setattr(CollectNetworkMetrics, "model_id", property(lambda self: "network"))

    runner = CollectNetworkMetrics(
        inst_name="snmp-task-01", inst_id=70001, task_id=7001,
    )
    runner.run()
    return runner


def _find_interface(result, inst_name):
    return next(item for item in result["interface"] if item["inst_name"] == inst_name)


def test_vm_response_matches_schema(load_fixture, load_schema):
    vm_resp = load_fixture("network/03_vm_metrics_response.json")
    schema = load_schema("network/03_vm_metrics.schema.json")
    jsonschema.validate(vm_resp, schema)


def test_vm_response_includes_topology_fact_metric(load_fixture, load_schema):
    vm_resp = load_fixture("network/03_vm_metrics_response.json")
    schema = load_schema("network/03_vm_metrics.schema.json")

    jsonschema.validate(vm_resp, schema)

    topology_facts = [
        item["metric"]
        for item in vm_resp["data"]["result"]
        if item["metric"]["__name__"] == NETWORK_TOPOLOGY_FACTS_METRIC
    ]

    assert topology_facts
    assert topology_facts[0]["instance_id"].startswith("snmp-task-")
    assert topology_facts[0]["source_protocol"] == "lldp"
    assert 0 <= float(topology_facts[0]["confidence"]) <= 1


@pytest.mark.django_db
def test_network_device_pipeline(load_fixture, monkeypatch):
    vm_resp = load_fixture("network/03_vm_metrics_response.json")

    # 边界拦截
    monkeypatch.setattr(
        "apps.cmdb.collection.query_vm.Collection.query",
        lambda self, sql, timeout=60: vm_resp,
    )

    # OidMapping DB 查询 → 内存替身
    OID_MAP = {
        "1.3.6.1.4.1.9.1.1208": {
            "oid": "1.3.6.1.4.1.9.1.1208",
            "model": "Cisco Catalyst 3850",
            "brand": "Cisco",
            "device_type": "switch",
            "built_in": True,
        }
    }
    monkeypatch.setattr(CollectNetworkMetrics, "get_oid_map", staticmethod(lambda: OID_MAP))

    # 任务对象 + 关掉 topo
    from types import SimpleNamespace
    fake_task = SimpleNamespace(id=7001, is_network_topo=False, instances=[])
    monkeypatch.setattr(CollectNetworkMetrics, "get_collect_inst", lambda self: fake_task)
    monkeypatch.setattr(CollectNetworkMetrics, "model_id", property(lambda self: "network"))

    runner = CollectNetworkMetrics(
        inst_name="snmp-task-01", inst_id=70001, task_id=7001,
    )
    runner.run()

    # 设备类型由 sysobjectid 推导出 "switch" → result["switch"]
    assert "switch" in runner.result
    devices = runner.result["switch"]
    assert len(devices) == 1
    dev = devices[0]
    assert dev["inst_name"] == "10.0.0.1-switch"
    assert dev["ip_addr"] == "10.0.0.1"
    assert dev["brand"] == "Cisco"
    assert dev["model"] == "Cisco Catalyst 3850"


def test_drift_detection_unknown_metric(load_schema):
    bad = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{
                "metric": {"__name__": "some_other_metric", "instance_id": "x", "ip_addr": "1.1.1.1"},
                "value": [1, "1"],
            }],
        },
    }
    schema = load_schema("network/03_vm_metrics.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


@pytest.mark.django_db
def test_network_topology_prefers_fact_payload_when_resolvable(monkeypatch):
    vm_resp = _build_network_vm_response(
        _build_metric(
            NETWORK_TOPOLOGY_FACTS_METRIC,
            "snmp-task-01-10.0.0.1",
            source_protocol="lldp",
            local_port_id="101",
            local_port_name="GigabitEthernet1/0/1",
            remote_device_id="dist-sw-1",
            remote_port_id="202",
            remote_port_name="GigabitEthernet1/0/24",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_FACTS_METRIC,
            "snmp-task-01-10.0.0.1",
            source_protocol="cdp",
            local_port_id="101",
            local_port_name="GigabitEthernet1/0/1",
            remote_device_id="dist-sw-1",
            remote_port_id="202",
            remote_port_name="GigabitEthernet1/0/24",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="ARP-IfIndex",
            ifindex="10.0.0.2",
            val="101",
        ),
    )

    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=True)

    source_interface = _find_interface(runner.result, "10.0.0.1-switch-edge-uplink")
    assert source_interface["assos"].count(
        {
            "asst_id": "connect",
            "inst_name": "10.0.0.2-switch-dist-downlink",
            "model_asst_id": "interface_connect_interface",
            "model_id": "interface",
        }
    ) == 1


@pytest.mark.django_db
def test_network_topology_falls_back_to_raw_topo_when_facts_absent(monkeypatch):
    vm_resp = _build_network_vm_response(
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="IFTable-IfDescr",
            ifindex="101",
            val="GigabitEthernet1/0/1",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="IFTable-IfAlias",
            ifindex="101",
            val="edge-uplink",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="IFTable-PhysAddress",
            ifindex="101",
            val="00aabbccdd01",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="ARP-IfIndex",
            ifindex="10.0.0.2",
            val="101",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="ARP-PhysAddress",
            ifindex="10.0.0.2",
            val="00aabbccdd02",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.2",
            tag="IFTable-IfDescr",
            ifindex="202",
            val="GigabitEthernet1/0/24",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.2",
            tag="IFTable-IfAlias",
            ifindex="202",
            val="dist-downlink",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.2",
            tag="IFTable-PhysAddress",
            ifindex="202",
            val="00aabbccdd02",
        ),
    )

    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=True)

    source_interface = _find_interface(runner.result, "10.0.0.1-switch-edge-uplink")
    assert {
        "asst_id": "connect",
        "inst_name": "10.0.0.2-switch-dist-downlink",
        "model_asst_id": "interface_connect_interface",
        "model_id": "interface",
    } in source_interface["assos"]


@pytest.mark.django_db
def test_network_topology_mixes_resolved_facts_with_raw_fallback_for_unresolved_edges(monkeypatch):
    vm_resp = _build_network_vm_response(
        _build_metric(
            NETWORK_SYSTEM_METRIC,
            "snmp-task-01-10.0.0.3",
            ip_addr="10.0.0.3",
            sysname="access-sw-1",
            sysobjectid="1.3.6.1.4.1.9.1.1208",
            port="161",
        ),
        _build_metric(
            NETWORK_INTERFACE_METRIC,
            "snmp-task-01-10.0.0.1",
            index="303",
            description="GigabitEthernet1/0/3",
            alias="edge-backup",
            mac_address="00aabbccdd03",
            oper_status="1",
        ),
        _build_metric(
            NETWORK_INTERFACE_METRIC,
            "snmp-task-01-10.0.0.3",
            index="404",
            description="GigabitEthernet1/0/48",
            alias="access-uplink",
            mac_address="00aabbccdd04",
            oper_status="1",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_FACTS_METRIC,
            "snmp-task-01-10.0.0.1",
            source_protocol="lldp",
            local_port_id="101",
            local_port_name="GigabitEthernet1/0/1",
            remote_device_id="dist-sw-1",
            remote_port_id="202",
            remote_port_name="GigabitEthernet1/0/24",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_FACTS_METRIC,
            "snmp-task-01-10.0.0.1",
            source_protocol="fdb",
            local_port_id="303",
            local_port_name="GigabitEthernet1/0/3",
            remote_device_id="00:11:22:33:44:55",
            remote_port_name="dynamic-mac",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="IFTable-IfDescr",
            ifindex="101",
            val="GigabitEthernet1/0/1",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="IFTable-IfAlias",
            ifindex="101",
            val="edge-uplink",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="IFTable-PhysAddress",
            ifindex="101",
            val="00aabbccdd01",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="ARP-IfIndex",
            ifindex="10.0.0.2",
            val="101",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="ARP-PhysAddress",
            ifindex="10.0.0.2",
            val="00aabbccdd02",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.2",
            tag="IFTable-IfDescr",
            ifindex="202",
            val="GigabitEthernet1/0/24",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.2",
            tag="IFTable-IfAlias",
            ifindex="202",
            val="dist-downlink",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.2",
            tag="IFTable-PhysAddress",
            ifindex="202",
            val="00aabbccdd02",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="IFTable-IfDescr",
            ifindex="303",
            val="GigabitEthernet1/0/3",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="IFTable-IfAlias",
            ifindex="303",
            val="edge-backup",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="IFTable-PhysAddress",
            ifindex="303",
            val="00aabbccdd03",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="ARP-IfIndex",
            ifindex="10.0.0.3",
            val="303",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="ARP-PhysAddress",
            ifindex="10.0.0.3",
            val="00aabbccdd04",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.3",
            tag="IFTable-IfDescr",
            ifindex="404",
            val="GigabitEthernet1/0/48",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.3",
            tag="IFTable-IfAlias",
            ifindex="404",
            val="access-uplink",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.3",
            tag="IFTable-PhysAddress",
            ifindex="404",
            val="00aabbccdd04",
        ),
    )

    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=True)

    uplink_interface = _find_interface(runner.result, "10.0.0.1-switch-edge-uplink")
    uplink_connect_assos = [asso for asso in uplink_interface["assos"] if asso["asst_id"] == "connect"]
    assert uplink_connect_assos == [
        {
            "asst_id": "connect",
            "inst_name": "10.0.0.2-switch-dist-downlink",
            "model_asst_id": "interface_connect_interface",
            "model_id": "interface",
        }
    ]

    backup_interface = _find_interface(runner.result, "10.0.0.1-switch-edge-backup")
    backup_connect_assos = [asso for asso in backup_interface["assos"] if asso["asst_id"] == "connect"]
    assert backup_connect_assos == [
        {
            "asst_id": "connect",
            "inst_name": "10.0.0.3-switch-access-uplink",
            "model_asst_id": "interface_connect_interface",
            "model_id": "interface",
        }
    ]


@pytest.mark.django_db
def test_network_topology_skips_ambiguous_fact_device_lookup_and_keeps_raw_fallback_safe(monkeypatch):
    vm_resp = _build_network_vm_response(
        _build_metric(
            NETWORK_SYSTEM_METRIC,
            "snmp-task-01-10.0.0.3",
            ip_addr="10.0.0.3",
            sysname="dist-sw-1",
            sysobjectid="1.3.6.1.4.1.9.1.1208",
            port="161",
        ),
        _build_metric(
            NETWORK_INTERFACE_METRIC,
            "snmp-task-01-10.0.0.3",
            index="303",
            description="GigabitEthernet1/0/48",
            alias="shadow-downlink",
            mac_address="00aabbccdd03",
            oper_status="1",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_FACTS_METRIC,
            "snmp-task-01-10.0.0.1",
            source_protocol="lldp",
            local_port_id="101",
            local_port_name="GigabitEthernet1/0/1",
            remote_device_id="dist-sw-1",
            remote_port_id="303",
            remote_port_name="GigabitEthernet1/0/48",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="IFTable-IfDescr",
            ifindex="101",
            val="GigabitEthernet1/0/1",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="IFTable-IfAlias",
            ifindex="101",
            val="edge-uplink",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="IFTable-PhysAddress",
            ifindex="101",
            val="00aabbccdd01",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="ARP-IfIndex",
            ifindex="10.0.0.2",
            val="101",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.1",
            tag="ARP-PhysAddress",
            ifindex="10.0.0.2",
            val="00aabbccdd02",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.2",
            tag="IFTable-IfDescr",
            ifindex="202",
            val="GigabitEthernet1/0/24",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.2",
            tag="IFTable-IfAlias",
            ifindex="202",
            val="dist-downlink",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.2",
            tag="IFTable-PhysAddress",
            ifindex="202",
            val="00aabbccdd02",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.3",
            tag="IFTable-IfDescr",
            ifindex="303",
            val="GigabitEthernet1/0/48",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.3",
            tag="IFTable-IfAlias",
            ifindex="303",
            val="shadow-downlink",
        ),
        _build_metric(
            NETWORK_TOPOLOGY_METRIC,
            "snmp-task-01-10.0.0.3",
            tag="IFTable-PhysAddress",
            ifindex="303",
            val="00aabbccdd03",
        ),
    )

    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=True)

    uplink_interface = _find_interface(runner.result, "10.0.0.1-switch-edge-uplink")
    uplink_connect_assos = [asso for asso in uplink_interface["assos"] if asso["asst_id"] == "connect"]
    assert uplink_connect_assos == [
        {
            "asst_id": "connect",
            "inst_name": "10.0.0.2-switch-dist-downlink",
            "model_asst_id": "interface_connect_interface",
            "model_id": "interface",
        }
    ]


@pytest.mark.django_db
def test_network_topology_disabled_keeps_existing_inventory_behavior(monkeypatch):
    vm_resp = _build_network_vm_response()
    sql_calls = []
    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=False, sql_calls=sql_calls)

    interface = _find_interface(runner.result, "10.0.0.1-switch-edge-uplink")
    assert sql_calls == [
        "network_system_info_gauge{instance_id='cmdb_7001'} or "
        "network_interfaces_info_gauge{instance_id='cmdb_7001'}"
    ]
    assert interface["assos"] == [
        {
            "model_id": "switch",
            "inst_name": "10.0.0.1-switch",
            "asst_id": "belong",
            "model_asst_id": "interface_belong_switch",
        }
    ]
