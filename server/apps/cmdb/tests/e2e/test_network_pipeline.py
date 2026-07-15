"""Network 网络设备 SNMP 采集端到端流水线测试 —— network 大类代表。

特点：
  - 走 SNMP 协议而非 SSH/HTTP
  - 通过 sysobjectid 在 OidMapping 表查"设备型号/品牌/类型"
  - device_type 决定 model_id（switch / router / firewall…）
  - inst_name 格式：{ip}-{device_type}
  - 拓扑发现走新流水线：server 消费 network_topo_info_gauge 原始证据行
    （instance_id/tag/ifindex/val/group），经 build_pipeline_aggregate →
    parse_aggregate_result 推断链路，再映射为 interface_connect_interface 关联
"""
import jsonschema
import pytest

from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics
from apps.cmdb.tests.e2e import pipeline


NETWORK_SYSTEM_METRIC = "network_system_info_gauge"
NETWORK_INTERFACE_METRIC = "network_interfaces_info_gauge"
NETWORK_TOPOLOGY_METRIC = "network_topo_info_gauge"
NETWORK_TOPOLOGY_FACTS_METRIC = "network_topology_facts_info_gauge"

DEV1 = "snmp-task-01-10.0.0.1"
DEV2 = "snmp-task-01-10.0.0.2"


def _build_metric(metric_name, instance_id, value="1", **metric):
    return {
        "metric": {"__name__": metric_name, "instance_id": instance_id, **metric},
        "value": [9999999999, value],
    }


def _topo_row(instance_id, tag, ifindex, val, group):
    """network_topo_info_gauge 原始证据行。

    Prometheus 会丢弃空标签：ifindex 为空字符串时不写该标签，
    顺带验证适配器对缺失 ifindex 标签的容错。
    """
    metric = {"tag": tag, "val": val, "group": group}
    if ifindex != "":
        metric["ifindex"] = ifindex
    return _build_metric(NETWORK_TOPOLOGY_METRIC, instance_id, **metric)


def _build_network_vm_response(*extra_metrics):
    base_metrics = [
        _build_metric(
            NETWORK_SYSTEM_METRIC,
            DEV1,
            ip_addr="10.0.0.1",
            sysname="edge-sw-1",
            sysobjectid="1.3.6.1.4.1.9.1.1208",
            port="161",
        ),
        _build_metric(
            NETWORK_SYSTEM_METRIC,
            DEV2,
            ip_addr="10.0.0.2",
            sysname="dist-sw-1",
            sysobjectid="1.3.6.1.4.1.9.1.1208",
            port="161",
        ),
        _build_metric(
            NETWORK_INTERFACE_METRIC,
            DEV1,
            index="101",
            description="GigabitEthernet1/0/1",
            alias="edge-uplink",
            mac_address="00aabbccdd01",
            oper_status="1",
        ),
        _build_metric(
            NETWORK_INTERFACE_METRIC,
            DEV2,
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


def _interfaces_rows(instance_id, ifindex, descr, alias, mac):
    return [
        _topo_row(instance_id, "IFTable-IfDescr", ifindex, descr, "interfaces"),
        _topo_row(instance_id, "IFTable-IfAlias", ifindex, alias, "interfaces"),
        _topo_row(instance_id, "IFTable-PhysAddress", ifindex, mac, "interfaces"),
    ]


def _lldp_neighbor_rows(instance_id, local_ifindex, local_port_name, remote_sysname, remote_port_name):
    suffix = f"0.{local_ifindex}.1"
    return [
        _topo_row(instance_id, "LLDP-RemSysName", suffix, remote_sysname, "neighbors"),
        _topo_row(instance_id, "LLDP-RemPortId", suffix, remote_port_name, "neighbors"),
        _topo_row(instance_id, "LLDP-RemPortIdSubtype", suffix, "5", "neighbors"),
        _topo_row(instance_id, "LLDP-LocPortId", local_ifindex, local_port_name, "neighbors"),
        _topo_row(instance_id, "LLDP-LocPortIdSubtype", local_ifindex, "5", "neighbors"),
    ]


def _arp_pair_rows():
    """dev1 的 ARP 表看到 dev2 的接口 MAC，双方 interfaces 组带 PhysAddress"""
    return [
        *_interfaces_rows(DEV1, "101", "GigabitEthernet1/0/1", "edge-uplink", "0x00aabbccdd01"),
        _topo_row(DEV1, "ARP-IfIndex", "10.0.0.2", "101", "arp"),
        _topo_row(DEV1, "ARP-PhysAddress", "10.0.0.2", "0x00aabbccdd02", "arp"),
        *_interfaces_rows(DEV2, "202", "GigabitEthernet1/0/24", "dist-downlink", "0x00aabbccdd02"),
    ]


def _run_network_pipeline(monkeypatch, vm_resp, *, topo_enabled, sql_calls=None, min_confidence=0.0):
    def fake_query(self, sql, timeout=60):
        if sql_calls is not None:
            sql_calls.append(sql)
        # 模拟真实 VM 行为：只返回 sql 实际请求的指标
        requested = {part.split("{")[0].strip() for part in sql.split(" or ")}
        filtered = [item for item in vm_resp["data"]["result"] if item["metric"]["__name__"] in requested]
        return {**vm_resp, "data": {**vm_resp["data"], "result": filtered}}

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

    fake_task = SimpleNamespace(
        id=7001,
        is_network_topo=topo_enabled,
        instances=[],
        topology_contract={
            "has_network_topo": topo_enabled,
            "topology_protocols": ["lldp", "cdp", "fdb", "arp"],
            "topology_fallback_strategy": "prefer_neighbors_then_fdb_then_arp",
            "min_confidence": min_confidence,
        },
        topology_snapshot={},
    )
    monkeypatch.setattr(CollectNetworkMetrics, "get_collect_inst", lambda self: fake_task)
    monkeypatch.setattr(CollectNetworkMetrics, "model_id", property(lambda self: "network"))
    # e2e 不落库：拓扑快照写入直接旁路
    monkeypatch.setattr(CollectNetworkMetrics, "save_topology_snapshot", lambda self, snapshot: None)

    runner = CollectNetworkMetrics(
        inst_name="snmp-task-01", inst_id=70001, task_id=7001,
    )
    runner.run()
    return runner


def _find_interface(result, inst_name):
    return next(item for item in result["interface"] if item["inst_name"] == inst_name)


def _connect_assos(interface):
    return [asso for asso in interface["assos"] if asso["asst_id"] == "connect"]


def _connect_asso(target_inst_name):
    return {
        "asst_id": "connect",
        "inst_name": target_inst_name,
        "model_asst_id": "interface_connect_interface",
        "model_id": "interface",
    }


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

    # 关掉 topo：fake_query 按 sql 过滤指标，fixture 中的 topo/facts 行不会被消费
    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=False)

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
def test_network_topology_lldp_authoritative_link(monkeypatch):
    """双方 LLDP 邻居证据 → authoritative 链路 → 接口 connect 关联"""
    vm_resp = _build_network_vm_response(
        _topo_row(DEV1, "System-SysName", "", "edge-sw-1", "system"),
        *_interfaces_rows(DEV1, "101", "GigabitEthernet1/0/1", "edge-uplink", "0x00aabbccdd01"),
        *_lldp_neighbor_rows(DEV1, "101", "GigabitEthernet1/0/1", "dist-sw-1", "GigabitEthernet1/0/24"),
        _topo_row(DEV2, "System-SysName", "", "dist-sw-1", "system"),
        *_interfaces_rows(DEV2, "202", "GigabitEthernet1/0/24", "dist-downlink", "0x00aabbccdd02"),
        *_lldp_neighbor_rows(DEV2, "202", "GigabitEthernet1/0/24", "edge-sw-1", "GigabitEthernet1/0/1"),
    )

    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=True)

    uplink = _find_interface(runner.result, "10.0.0.1-switch-edge-uplink")
    downlink = _find_interface(runner.result, "10.0.0.2-switch-dist-downlink")
    forward = _connect_assos(uplink)
    reverse = _connect_assos(downlink)
    # 双向证据经流水线收敛后至少产出一向 connect 关联，且无重复
    assert forward or reverse
    assert forward in ([], [_connect_asso("10.0.0.2-switch-dist-downlink")])
    assert reverse in ([], [_connect_asso("10.0.0.1-switch-edge-uplink")])


@pytest.mark.django_db
def test_network_topology_arp_inferred_link(monkeypatch):
    """无邻居协议证据时，ARP + 接口 MAC 推断出 connect 关联"""
    vm_resp = _build_network_vm_response(*_arp_pair_rows())

    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=True)

    source_interface = _find_interface(runner.result, "10.0.0.1-switch-edge-uplink")
    assert _connect_assos(source_interface) == [_connect_asso("10.0.0.2-switch-dist-downlink")]


# 复现线上现象：真实 agent 给同一任务所有设备盖的是任务级 instance_id（cmdb_{task_id}），
# 仅靠每行 host 区分设备。下面构造这种 VM 数据，验证 server 仍能按 host 把多台设备分开，
# 否则多台会被合并成 1 台、跨设备拓扑关联全部消失（实测 topology_snapshot.devices=1）。
SHARED_IID = "cmdb_777"


def _shared_iid_arp_pair_rows():
    def sys(host, ip, sysname):
        return _build_metric(NETWORK_SYSTEM_METRIC, SHARED_IID, host=host, ip_addr=ip,
                             sysname=sysname, sysobjectid="1.3.6.1.4.1.9.1.1208", port="161")

    def iface(host, idx, descr, alias, mac):
        return _build_metric(NETWORK_INTERFACE_METRIC, SHARED_IID, host=host, index=idx,
                             description=descr, alias=alias, mac_address=mac, oper_status="1")

    def topo(host, tag, ifindex, val, group):
        metric = {"host": host, "tag": tag, "val": val, "group": group}
        if ifindex != "":
            metric["ifindex"] = ifindex
        return _build_metric(NETWORK_TOPOLOGY_METRIC, SHARED_IID, **metric)

    return [
        sys("10.0.0.1", "10.0.0.1", "edge-sw-1"),
        sys("10.0.0.2", "10.0.0.2", "dist-sw-1"),
        iface("10.0.0.1", "101", "GigabitEthernet1/0/1", "edge-uplink", "00aabbccdd01"),
        iface("10.0.0.2", "202", "GigabitEthernet1/0/24", "dist-downlink", "00aabbccdd02"),
        # dev1 接口 MAC + ARP 看到 dev2 的接口 MAC
        topo("10.0.0.1", "IFTable-IfDescr", "101", "GigabitEthernet1/0/1", "interfaces"),
        topo("10.0.0.1", "IFTable-IfAlias", "101", "edge-uplink", "interfaces"),
        topo("10.0.0.1", "IFTable-PhysAddress", "101", "0x00aabbccdd01", "interfaces"),
        topo("10.0.0.1", "ARP-IfIndex", "10.0.0.2", "101", "arp"),
        topo("10.0.0.1", "ARP-PhysAddress", "10.0.0.2", "0x00aabbccdd02", "arp"),
        topo("10.0.0.2", "IFTable-IfDescr", "202", "GigabitEthernet1/0/24", "interfaces"),
        topo("10.0.0.2", "IFTable-IfAlias", "202", "dist-downlink", "interfaces"),
        topo("10.0.0.2", "IFTable-PhysAddress", "202", "0x00aabbccdd02", "interfaces"),
    ]


@pytest.mark.django_db
def test_topology_separates_devices_by_host_under_shared_instance_id(monkeypatch):
    vm_resp = {"status": "success", "data": {"resultType": "vector", "result": _shared_iid_arp_pair_rows()}}

    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=True)

    # 两台设备必须被分别识别（而不是因共享 instance_id 合并成一台）
    assert len(runner.result.get("switch", [])) == 2
    # 跨设备 ARP 推断出 connect 关联
    source_interface = _find_interface(runner.result, "10.0.0.1-switch-edge-uplink")
    assert _connect_assos(source_interface) == [_connect_asso("10.0.0.2-switch-dist-downlink")]


@pytest.mark.django_db
def test_network_topology_authoritative_suppresses_arp_duplicate(monkeypatch):
    """同一对端点同时有 LLDP 与 ARP 证据，关联只产出一份"""
    vm_resp = _build_network_vm_response(
        _topo_row(DEV1, "System-SysName", "", "edge-sw-1", "system"),
        _topo_row(DEV2, "System-SysName", "", "dist-sw-1", "system"),
        *_lldp_neighbor_rows(DEV1, "101", "GigabitEthernet1/0/1", "dist-sw-1", "GigabitEthernet1/0/24"),
        *_arp_pair_rows(),
    )

    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=True)

    uplink = _find_interface(runner.result, "10.0.0.1-switch-edge-uplink")
    downlink = _find_interface(runner.result, "10.0.0.2-switch-dist-downlink")
    all_connects = _connect_assos(uplink) + _connect_assos(downlink)
    assert len(all_connects) == 1
    assert all_connects == [_connect_asso("10.0.0.2-switch-dist-downlink")]


@pytest.mark.django_db
def test_network_topology_unresolved_neighbor_does_not_create_relation(monkeypatch):
    """LLDP 邻居指向不存在的 sysname（ghost）→ 不产生幽灵关联，正常 ARP 关联不受影响"""
    vm_resp = _build_network_vm_response(
        _topo_row(DEV1, "System-SysName", "", "edge-sw-1", "system"),
        *_lldp_neighbor_rows(DEV1, "101", "GigabitEthernet1/0/1", "ghost", "GigabitEthernet1/0/99"),
        *_arp_pair_rows(),
    )

    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=True)

    for interface in runner.result["interface"]:
        for asso in _connect_assos(interface):
            assert "ghost" not in asso["inst_name"]

    source_interface = _find_interface(runner.result, "10.0.0.1-switch-edge-uplink")
    assert _connect_assos(source_interface) == [_connect_asso("10.0.0.2-switch-dist-downlink")]


@pytest.mark.django_db
def test_network_topology_min_confidence_filters_arp(monkeypatch):
    """契约 min_confidence=0.9（→90）高于 ARP 推断 confidence=50 → 关联被过滤"""
    vm_resp = _build_network_vm_response(*_arp_pair_rows())

    runner = _run_network_pipeline(monkeypatch, vm_resp, topo_enabled=True, min_confidence=0.9)

    for interface in runner.result["interface"]:
        assert _connect_assos(interface) == []


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


# ============================================================================
# Task 2.5: network A 端 + B 端对齐全覆盖测试
# ============================================================================


def test_network_a_b_alignment(load_fixture, load_schema, monkeypatch):
    """network A 端 + B 端对齐全覆盖测试。

    network 走 minimal path:验证 A 端 metric.__name__ / instance_id / business labels +
    B 端通过 03 fixture 走 CollectNetworkMetrics 实例字段校验。
    """
    from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def

    raw = load_fixture("network/01_stargazer_raw.json")
    expected = load_fixture("network/04_expected_cmdb_result.json")

    # A 端:01 → 02 → 03
    p2 = pipeline.step1_stargazer_normalize_generic([raw], model_id="network")
    p3 = pipeline.step2_push_to_vm(p2, task_id=77777)

    main_metric = "network_info_gauge"
    found_main = False
    for result_item in p3["data"]["result"]:
        metric_name = result_item["metric"]["__name__"]
        if metric_name == main_metric:
            found_main = True
            assert result_item["metric"]["instance_id"] == "cmdb_77777"
            # 业务 label 集合 ⊇ model 必填字段
            model_fields = get_model_field_def("network")
            required = {f.name for f in model_fields.values() if f.is_required}
            labels = set(result_item["metric"].keys())
            exclude = {"__name__", "instance_id", "collect_status", "inst_name",
                       "model_id", "id", "create_time", "update_time", "assos"}
            missing = required - labels - exclude
            assert not missing, f"A 端 03 metric 缺 model 必填字段: {missing}"
    assert found_main, f"主 metric {main_metric} 在 03 fixture 中不存在"

    # B 端:03 → 04
    from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics
    vm_resp = load_fixture("network/03_vm_metrics_response.json")

    # Mock VM 走 sql filter
    def fake_query(self, sql, timeout=60):
        requested = {part.split("{")[0].strip() for part in sql.split(" or ")}
        filtered = [item for item in vm_resp["data"]["result"] if item["metric"]["__name__"] in requested]
        return {**vm_resp, "data": {**vm_resp["data"], "result": filtered}}
    monkeypatch.setattr("apps.cmdb.collection.query_vm.Collection.query", fake_query)

    # OID map for Cisco
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
    fake_task = SimpleNamespace(
        id=77777,
        is_network_topo=False,
        instances=[],
        topology_contract={"has_network_topo": False, "topology_protocols": [],
                          "topology_fallback_strategy": "prefer_neighbors_then_fdb_then_arp",
                          "min_confidence": 0.0},
        topology_snapshot={},
    )
    monkeypatch.setattr(CollectNetworkMetrics, "get_collect_inst", lambda self: fake_task)
    monkeypatch.setattr(CollectNetworkMetrics, "model_id", property(lambda self: "network"))
    monkeypatch.setattr(CollectNetworkMetrics, "save_topology_snapshot", lambda self, snapshot: None)

    runner = CollectNetworkMetrics(
        inst_name="snmp-task-01", inst_id=77777, task_id=77777,
    )
    runner.run()

    # 设备类型由 sysobjectid 推导出 "switch" → result["switch"]
    assert "switch" in runner.result
    devices = runner.result["switch"]
    assert len(devices) >= 1

    inst = devices[0]
    # B 端:实例字段 ⊆ model 字段定义
    model_fields = get_model_field_def("network")
    system_fields = {
        "inst_name", "model_id", "id", "create_time", "update_time",
        "_placeholder_reason", "license_status", "assos",
    }
    model_field_names = set(model_fields.keys()) - system_fields
    inst_fields = set(inst.keys())
    missing = model_field_names - inst_fields
    assert not missing, f"B 端 04 实例缺 model 字段: {missing}"

    # B 端:必填字段非空(model_id 由 runner 后续在 result['switch'] key 体现,不在实例 dict 内)
    for field_name in {"inst_name", "ip_addr"}:
        value = inst.get(field_name)
        assert value, f"必填字段 {field_name!r} 为空: {value}"

    # B 端:inst_name 格式 {ip}-{device_type}
    assert inst["inst_name"].endswith("-switch"), f"inst_name 应以 -switch 结尾: {inst['inst_name']}"
