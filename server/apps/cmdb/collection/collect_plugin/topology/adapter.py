# 把 VictoriaMetrics 查回的 network_topo_info_gauge 指标行转换为
# collect_plugin.topology.parse.parse_aggregate_result 期望的 aggregate 结构。
from __future__ import annotations

from collections import defaultdict
from typing import Any

# group 标签由升级后的 agent 上报；TAG_GROUP_MAP 兜底覆盖注册表全部 tag，
# 防御标签在采集链路中丢失的情况。
TAG_GROUP_MAP = {
    "System-SysName": "system",
    "IFTable-IfDescr": "interfaces",
    "IFTable-PhysAddress": "interfaces",
    "IFTable-IfAlias": "interfaces",
    "IFXTable-IfName": "interfaces",
    "IpAddr-IpAddr": "ip",
    "ARP-IfIndex": "arp",
    "ARP-PhysAddress": "arp",
    "LLDP-LocPortIdSubtype": "neighbors",
    "LLDP-LocPortId": "neighbors",
    "LLDP-LocPortDesc": "neighbors",
    "LLDP-RemChassisIdSubtype": "neighbors",
    "LLDP-RemChassisId": "neighbors",
    "LLDP-RemPortIdSubtype": "neighbors",
    "LLDP-RemPortId": "neighbors",
    "LLDP-RemPortDesc": "neighbors",
    "LLDP-RemSysName": "neighbors",
    "CDP-AddressType": "neighbors",
    "CDP-Address": "neighbors",
    "CDP-DeviceId": "neighbors",
    "CDP-DevicePort": "neighbors",
    "CDP-Platform": "neighbors",
    "CDP-SysName": "neighbors",
    "FDP-DeviceId": "neighbors",
    "FDP-DevicePort": "neighbors",
    "FDP-Platform": "neighbors",
    "FDP-Version": "neighbors",
    "BRIDGE-BasePortIfIndex": "bridge",
    "FDB-MacAddress": "fdb",
    "FDB-Port": "fdb",
    "FDB-Status": "fdb",
    "QBRIDGE-FdbPort": "fdb",
    "QBRIDGE-FdbStatus": "fdb",
}


def build_pipeline_aggregate(topo_rows: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_by_device: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in topo_rows:
        if not isinstance(row, dict):
            continue
        instance_id = str(row.get("instance_id", "") or "")
        tag = str(row.get("tag", "") or "")
        group = str(row.get("group", "") or "") or TAG_GROUP_MAP.get(tag, "")
        if not instance_id or not group:
            continue
        evidence_by_device[instance_id][group].append(
            {
                "tag": tag,
                "ifindex": str(row.get("ifindex", "") or ""),
                "val": str(row.get("val", "") or ""),
            }
        )

    return {
        "devices": [
            {
                "device": {"host": instance_id},
                "success": True,
                "collector_result": {"result": {"evidence": dict(groups)}},
            }
            for instance_id, groups in evidence_by_device.items()
        ]
    }
