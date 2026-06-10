import pytest

from apps.cmdb.collection.collect_plugin.topology.adapter import build_pipeline_aggregate

pytestmark = [pytest.mark.unit]


def _row(instance_id, tag, ifindex, val, group=None, **extra):
    row = {
        "index_key": "network_topo_info_gauge",
        "instance_id": instance_id,
        "tag": tag,
        "ifindex": ifindex,
        "val": val,
        **extra,
    }
    if group is not None:
        row["group"] = group
    return row


def test_groups_rows_by_instance_and_evidence_group():
    rows = [
        _row("dev-a", "System-SysName", "", "sw-a", group="system"),
        _row("dev-a", "IFTable-IfDescr", "7", "Gi0/0/7", group="interfaces"),
        _row("dev-b", "ARP-IfIndex", "10.0.0.1", "7", group="arp"),
    ]
    aggregate = build_pipeline_aggregate(rows)
    devices = {item["device"]["host"]: item for item in aggregate["devices"]}
    assert set(devices) == {"dev-a", "dev-b"}
    evidence_a = devices["dev-a"]["collector_result"]["result"]["evidence"]
    assert evidence_a["system"] == [{"tag": "System-SysName", "ifindex": "", "val": "sw-a"}]
    assert evidence_a["interfaces"] == [{"tag": "IFTable-IfDescr", "ifindex": "7", "val": "Gi0/0/7"}]
    assert devices["dev-a"]["success"] is True


def test_falls_back_to_tag_group_map_when_group_label_missing():
    rows = [
        _row("dev-a", "BRIDGE-BasePortIfIndex", "5", "23"),  # 无 group 标签
        _row("dev-a", "QBRIDGE-FdbPort", "1.0.0.94.0.0.1", "5"),
        _row("dev-a", "LLDP-RemSysName", "0.5.1", "sw-b"),
    ]
    aggregate = build_pipeline_aggregate(rows)
    evidence = aggregate["devices"][0]["collector_result"]["result"]["evidence"]
    assert evidence["bridge"][0]["val"] == "23"
    assert evidence["fdb"][0]["tag"] == "QBRIDGE-FdbPort"
    assert evidence["neighbors"][0]["tag"] == "LLDP-RemSysName"


def test_missing_ifindex_label_defaults_to_empty_string():
    rows = [
        {"instance_id": "dev-a", "tag": "System-SysName", "val": "sw-a", "group": "system"},
    ]
    aggregate = build_pipeline_aggregate(rows)
    evidence = aggregate["devices"][0]["collector_result"]["result"]["evidence"]
    assert evidence["system"] == [{"tag": "System-SysName", "ifindex": "", "val": "sw-a"}]


def test_drops_rows_without_instance_or_resolvable_group():
    rows = [
        {"tag": "IFTable-IfDescr", "ifindex": "1", "val": "x", "group": "interfaces"},  # 无 instance_id
        _row("dev-a", "Unknown-Tag", "1", "y"),  # 无 group 且 tag 不在映射表
    ]
    aggregate = build_pipeline_aggregate(rows)
    assert aggregate["devices"] == []


def test_empty_input_yields_empty_devices():
    assert build_pipeline_aggregate([]) == {"devices": []}


def test_adapter_output_feeds_pipeline_end_to_end():
    from apps.cmdb.collection.collect_plugin.topology.parse import parse_aggregate_result

    rows = [
        # dev-a：接口 + 自己的 MAC + 指向 dev-b 的 ARP
        _row("dev-a", "IFTable-IfDescr", "7", "Gi0/0/7", group="interfaces"),
        _row("dev-a", "IFTable-PhysAddress", "7", "0xaaaaaaaaaa01", group="interfaces"),
        _row("dev-a", "ARP-IfIndex", "10.0.0.2", "7", group="arp"),
        _row("dev-a", "ARP-PhysAddress", "10.0.0.2", "0xbbbbbbbbbb01", group="arp"),
        # dev-b：接口
        _row("dev-b", "IFTable-IfDescr", "9", "Gi0/0/9", group="interfaces"),
        _row("dev-b", "IFTable-PhysAddress", "9", "0xbbbbbbbbbb01", group="interfaces"),
    ]
    result = parse_aggregate_result(build_pipeline_aggregate(rows))
    assert result["summary"]["devices"] == 2
    assert result["summary"]["inferred_links"] == 1
    link = result["topology"]["inferred_links"][0]
    assert link["evidence_source"] == "arp"
    assert {link["source_device"], link["target_device"]} == {"dev-a", "dev-b"}
