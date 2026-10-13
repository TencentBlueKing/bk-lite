"""批量解析机房里的机柜和设备。

只跟随 server_room → rack → 设备这条出边，不沿关联图递归。
直接挂在机房上、没有经过机柜的设备不进入结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.cmdb.constants.constants import INSTANCE_ASSOCIATION
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.instance_identity import optional_inst_uuid

ROOM_MODEL_ID = "server_room"
RACK_MODEL_ID = "rack"


@dataclass
class RoomRackDevices:
    racks: list[dict] = field(default_factory=list)
    devices_by_rack_uuid: dict[str, list[dict]] = field(default_factory=dict)


def query_outgoing_edges(src_uuids: list[str], src_model_id: str, dst_model_id: str | None = None) -> list[dict]:
    """一次查出若干源实例的出边。只查 src→dst，不把反向边算进来。"""
    normalized = []
    seen = set()
    for value in src_uuids or []:
        inst_uuid = optional_inst_uuid(value)
        if not inst_uuid or inst_uuid in seen:
            continue
        seen.add(inst_uuid)
        normalized.append(inst_uuid)
    if not normalized or not src_model_id:
        return []
    query = [
        {"field": "src_inst_uuid", "type": "str[]", "value": normalized},
        {"field": "src_model_id", "type": "str=", "value": src_model_id},
    ]
    if dst_model_id:
        query.append({"field": "dst_model_id", "type": "str=", "value": dst_model_id})
    with GraphClient() as client:
        edges = client.query_edge(INSTANCE_ASSOCIATION, query) or []
    kept = []
    allowed = set(normalized)
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        if edge.get("src_inst_uuid") not in allowed:
            continue
        edge_dst_model = edge.get("dst_model_id")
        if dst_model_id and edge_dst_model not in (None, "", dst_model_id):
            continue
        kept.append(edge)
    return kept


def _visible_instances(inst_uuids: list[str], permission_map, user) -> list[dict]:
    if not inst_uuids:
        return []
    rows = InstanceManage.query_entity_by_uuids(list(inst_uuids)) or []
    by_uuid = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        inst_uuid = optional_inst_uuid(row.get("inst_uuid"))
        if not inst_uuid:
            continue
        if permission_map and not InstanceManage._has_topology_view_permission(row, permission_map, user=user):
            continue
        by_uuid[inst_uuid] = row
    return [by_uuid[inst_uuid] for inst_uuid in inst_uuids if inst_uuid in by_uuid]


def resolve_room_rack_devices(room_uuid: str, permission_map=None, user=None) -> RoomRackDevices:
    """机房 → 机柜 → 设备。直接挂在机房上、没有经过机柜的设备不进入结果。"""
    normalized_room = optional_inst_uuid(room_uuid)
    if not normalized_room:
        return RoomRackDevices()
    rack_edges = query_outgoing_edges([normalized_room], ROOM_MODEL_ID, RACK_MODEL_ID)
    rack_uuids = []
    seen_racks = set()
    for edge in rack_edges:
        if edge.get("src_inst_uuid") != normalized_room:
            continue
        rack_uuid = optional_inst_uuid(edge.get("dst_inst_uuid"))
        if not rack_uuid or rack_uuid in seen_racks:
            continue
        seen_racks.add(rack_uuid)
        rack_uuids.append(rack_uuid)
    racks = [item for item in _visible_instances(rack_uuids, permission_map, user) if item.get("model_id") == RACK_MODEL_ID]
    devices_by_rack = {item["inst_uuid"]: [] for item in racks if item.get("inst_uuid")}
    if not devices_by_rack:
        return RoomRackDevices(racks=racks, devices_by_rack_uuid={})

    device_edges = query_outgoing_edges(list(devices_by_rack), RACK_MODEL_ID, None)
    device_uuids = []
    pairs = []
    seen_devices = set()
    seen_pairs = set()
    for edge in device_edges:
        rack_uuid = edge.get("src_inst_uuid")
        device_uuid = optional_inst_uuid(edge.get("dst_inst_uuid"))
        if rack_uuid not in devices_by_rack or not device_uuid:
            continue
        pair = (rack_uuid, device_uuid)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        pairs.append(pair)
        if device_uuid not in seen_devices:
            seen_devices.add(device_uuid)
            device_uuids.append(device_uuid)
    visible_devices = {item["inst_uuid"]: item for item in _visible_instances(device_uuids, permission_map, user) if item.get("inst_uuid")}
    for rack_uuid, device_uuid in pairs:
        device = visible_devices.get(device_uuid)
        if device:
            devices_by_rack[rack_uuid].append(device)
    return RoomRackDevices(racks=racks, devices_by_rack_uuid=devices_by_rack)
