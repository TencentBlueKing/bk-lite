"""机房机柜俯视图：纯布局组装 + 只读数据拉取。

边界处理遵循设计：未定位/未分配 U 位的实例不静默丢弃，单独成列；
越界/重叠/同格冲突均标记返回，由前端高亮提示。
"""

import re

from apps.cmdb.constants.constants import INSTANCE_ASSOCIATION
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.instance_identity import optional_inst_uuid
from apps.core.logger import cmdb_logger as logger

RACK_LOCATION_PATTERN = re.compile(r"^([A-Z]+)(\d+)$")


def col_to_letter(col: int) -> str:
    """1->A, 26->Z, 27->AA。"""
    result = ""
    n = int(col)
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def letter_to_index(value: str) -> int:
    result = 0
    for char in value:
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result


def format_rack_location_label(row: int, col: int) -> str:
    """格式化机柜位置标签：字母为列（A–…）、数字为行（01–…）。"""
    return f"{col_to_letter(col)}{row:02d}"


def parse_rack_location(value) -> tuple[int, int] | None:
    """解析 rack.location，字母为列、数字为行；支持 A3/A03。

    与机房俯视图约定一致：列 A–L（横轴）、行 1–N（纵轴）。
    """
    if not isinstance(value, str):
        return None

    match = RACK_LOCATION_PATTERN.match(value.strip().upper())
    if not match:
        return None

    col = letter_to_index(match.group(1))
    row = int(match.group(2))
    if row < 1 or col < 1:
        return None
    return row, col


def build_room_layout(racks: list) -> dict:
    """把机柜列表组装成俯视平面图数据。

    入参每项：inst_uuid, inst_name, row, col, u_count, datacenter_type,
              datacenter_state, used_u（已占用 U 数）。
    """
    placed, unplaced, cells = [], [], {}
    for r in racks:
        # 行/列均为 1-based 网格坐标；缺任一坐标即视为"未定位"（不丢弃，单独成列）。
        # 用 is not None 而非真值判断，语义只关心"有没有坐标"，不把 0 误判为缺失。
        if r.get("row") is not None and r.get("col") is not None:
            u_count = r.get("u_count") or 0
            used_u = r.get("used_u") or 0
            item = {
                **r,
                "col_letter": col_to_letter(r["col"]),
                "usage": round(used_u / u_count * 100) if u_count else 0,
            }
            placed.append(item)
            cells.setdefault((r["row"], r["col"]), []).append(item["inst_uuid"])
        else:
            location = r.get("location")
            unplaced.append(
                {
                    **r,
                    "unplaced_reason": ("missing_location" if not isinstance(location, str) or not location.strip() else "invalid_location"),
                }
            )

    conflicts = [{"row": rc[0], "col": rc[1], "inst_uuids": uuids} for rc, uuids in cells.items() if len(uuids) > 1]
    return {
        "racks": placed,
        "unplaced": unplaced,
        "conflicts": conflicts,
        "grid": {
            "max_row": max((r["row"] for r in placed), default=0),
            "max_col": max((r["col"] for r in placed), default=0),
        },
    }


def build_rack_layout(u_count: int, devices: list) -> dict:
    """把机柜内设备组装成正视 U 图数据。

    入参每项：inst_uuid, inst_name, model_id, rack_u_start, u_size。
    """
    placed, unplaced = [], []
    for d in devices:
        u_start, u_size = d.get("rack_u_start"), d.get("u_size")
        if not u_start or not u_size:
            unplaced.append(d)
            continue
        u_end = u_start + u_size - 1
        overflow = u_start < 1 or (bool(u_count) and u_end > u_count)
        placed.append({**d, "u_end": u_end, "overflow": overflow})

    overlaps = []
    ordered = sorted(placed, key=lambda x: x["rack_u_start"])
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if b["rack_u_start"] > a["u_end"]:
                break
            overlaps.append([a["inst_uuid"], b["inst_uuid"]])

    free_u, max_free_u = free_u_stats(u_count, [(d["rack_u_start"], d["u_end"]) for d in placed])
    return {"u_count": u_count, "placed": placed, "unplaced": unplaced, "overlaps": overlaps, "free_u": free_u, "max_free_u": max_free_u}


def free_u_stats(u_count: int, ranges: list) -> tuple:
    """空闲 U 统计：free_u 总空闲数；max_free_u 最大连续空闲段
    （"能否塞下 N U 设备"）。ranges 为已占用的 [(u_start, u_end), ...]，越界自动裁剪。"""
    if not u_count or u_count <= 0:
        return 0, 0
    occupied = [False] * (u_count + 1)  # 下标 1..u_count
    for s, e in ranges:
        for pos in range(max(1, s), min(u_count, e) + 1):
            occupied[pos] = True
    free_u, max_free_u, run = 0, 0, 0
    for pos in range(1, u_count + 1):
        if occupied[pos]:
            run = 0
        else:
            free_u += 1
            run += 1
            max_free_u = max(max_free_u, run)
    return free_u, max_free_u


def _safe_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _scalar(value):
    """枚举字段（如 datacenter_type/state）在 CMDB 中以列表存储（单选也是 ['1']），
    取首个值归一为标量供前端按枚举 id 着色；空列表/None 返回 None。"""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _rack_device_instances(rack_id, permission_map=None, user=None) -> list:
    """机柜直接 contains 的设备实例（已按权限过滤）。"""
    assocs = InstanceManage.instance_association_instance_list("rack", int(rack_id))
    ids = [item["_id"] for a in assocs if a["src_model_id"] == "rack" for item in a["inst_list"]]
    if not ids:
        return []
    inst_map = InstanceManage._query_instance_map_by_ids({int(i) for i in ids})
    devices = []
    for i in ids:
        inst = inst_map.get(int(i))
        if not inst:
            continue
        if permission_map and not InstanceManage._has_topology_view_permission(inst, permission_map, user=user):
            continue
        devices.append(inst)
    return devices


def _normalize_int_ids(values) -> list[int]:
    result = []
    seen = set()
    for value in values or []:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _rack_device_relations(rack_ids: list[int]) -> tuple[dict[int, list[int]], dict[int, dict]]:
    relation_map = {rack_id: [] for rack_id in rack_ids}
    if not rack_ids:
        return relation_map, {}

    rack_instances = InstanceManage.query_entity_by_ids(rack_ids)
    rack_uuid_by_id = {
        int(instance["_id"]): instance["inst_uuid"]
        for instance in rack_instances
        if instance.get("_id") in relation_map and instance.get("inst_uuid")
    }
    rack_id_by_uuid = {inst_uuid: rack_id for rack_id, inst_uuid in rack_uuid_by_id.items()}
    rack_uuids = [rack_uuid_by_id[rack_id] for rack_id in rack_ids if rack_id in rack_uuid_by_id]
    if not rack_uuids:
        return relation_map, {}

    query_data = [
        {"field": "src_inst_uuid", "type": "str[]", "value": rack_uuids},
        {"field": "src_model_id", "type": "str=", "value": "rack"},
    ]
    with GraphClient() as ag:
        edges = ag.query_edge(INSTANCE_ASSOCIATION, query_data)

    device_uuids = sorted({edge.get("dst_inst_uuid") for edge in edges or [] if edge.get("dst_inst_uuid")})
    device_instances = InstanceManage.query_entity_by_uuids(device_uuids) if device_uuids else []
    device_map = {int(instance["_id"]): instance for instance in device_instances if instance.get("_id") is not None}
    device_id_by_uuid = {
        instance["inst_uuid"]: int(instance["_id"]) for instance in device_instances if instance.get("_id") is not None and instance.get("inst_uuid")
    }
    seen_by_rack = {rack_id: set() for rack_id in rack_ids}
    for edge in edges or []:
        rack_id = rack_id_by_uuid.get(edge.get("src_inst_uuid"))
        device_id = device_id_by_uuid.get(edge.get("dst_inst_uuid"))
        if rack_id is None or device_id is None:
            continue
        if device_id in seen_by_rack[rack_id]:
            continue
        seen_by_rack[rack_id].add(device_id)
        relation_map[rack_id].append(device_id)
    return relation_map, device_map


def get_room3d_rack_device_summaries(rack_uuids, permission_map=None, user=None) -> dict:
    """批量组装 Room3D 机柜设备摘要，避免按机柜重复查询正视图布局。"""
    normalized_rack_uuids = [value for item in rack_uuids or [] if (value := optional_inst_uuid(item))]
    if not normalized_rack_uuids:
        return {}

    rack_instances = InstanceManage.query_entity_by_uuids(normalized_rack_uuids)
    rack_uuid_by_id = {int(item["_id"]): item["inst_uuid"] for item in rack_instances if item.get("_id") is not None and item.get("inst_uuid")}
    normalized_rack_ids = list(rack_uuid_by_id)

    relation_map, device_map = _rack_device_relations(normalized_rack_ids)
    summaries = {rack_uuid: {"devices": [], "device_count": 0, "unplaced_device_count": 0} for rack_uuid in normalized_rack_uuids}

    for rack_id in normalized_rack_ids:
        rack_uuid = rack_uuid_by_id[rack_id]
        for device_id in relation_map.get(rack_id, []):
            inst = device_map.get(int(device_id))
            if not inst:
                continue
            if permission_map and not InstanceManage._has_topology_view_permission(inst, permission_map, user=user):
                continue

            inst_uuid = optional_inst_uuid(inst.get("inst_uuid"))
            if not inst_uuid:
                logger.warning("Room3D 设备缺少合法 inst_uuid，已安全跳过: graph_id=%s", inst.get("_id"))
                continue
            summaries[rack_uuid]["device_count"] += 1
            rack_u_start = _safe_int(inst.get("rack_u_start"))
            u_size = _safe_int(inst.get("u_size"))
            if not rack_u_start or not u_size:
                summaries[rack_uuid]["unplaced_device_count"] += 1
                continue
            summaries[rack_uuid]["devices"].append(
                {
                    "device_id": inst_uuid,
                    "device_name": inst.get("inst_name") or "",
                    "model_id": inst.get("model_id"),
                    "rack_u_start": rack_u_start,
                    "u_size": u_size,
                    "status": _scalar(inst.get("status") or inst.get("datacenter_state")),
                }
            )

    return summaries


def get_rack_layout(rack_id, permission_map=None, user=None) -> dict:
    rack = InstanceManage.query_entity_by_id(int(rack_id)) or {}
    u_count = _safe_int(rack.get("u_count")) or 0
    devices = [
        {
            "inst_uuid": d["inst_uuid"],
            "inst_name": d.get("inst_name"),
            "model_id": d.get("model_id"),
            "rack_u_start": _safe_int(d.get("rack_u_start")),
            "u_size": _safe_int(d.get("u_size")),
            "status": _scalar(d.get("status") or d.get("datacenter_state")),
            "organization": d.get("organization") or [],
            "_creator": d.get("_creator"),
        }
        for d in _rack_device_instances(rack_id, permission_map, user)
        if d.get("inst_uuid")
    ]
    layout = build_rack_layout(u_count, devices)
    layout["rack"] = {
        "inst_uuid": rack.get("inst_uuid"),
        "inst_name": rack.get("inst_name"),
        "u_count": u_count,
    }
    return layout


def get_room_layout(server_room_id, permission_map=None, user=None) -> dict:
    assocs = InstanceManage.instance_association_instance_list("server_room", int(server_room_id))
    rack_ids = [item["_id"] for a in assocs if a["src_model_id"] == "server_room" and a["dst_model_id"] == "rack" for item in a["inst_list"]]
    racks = []
    if rack_ids:
        inst_map = InstanceManage._query_instance_map_by_ids({int(i) for i in rack_ids})
        for rid in rack_ids:
            r = inst_map.get(int(rid))
            if not r:
                continue
            if permission_map and not InstanceManage._has_topology_view_permission(r, permission_map, user=user):
                continue
            if not r.get("inst_uuid"):
                continue
            u_count = _safe_int(r.get("u_count")) or 0
            ranges = []
            for d in _rack_device_instances(rid, permission_map, user):
                us = _safe_int(d.get("rack_u_start"))
                sz = _safe_int(d.get("u_size"))
                if us and sz:
                    ranges.append((us, us + sz - 1))
            free_u, max_free_u = free_u_stats(u_count, ranges)
            # 已占用 = 总U - 空闲U（去重计数）：忽略未分配设备、重叠不重复计、永不超 100%，
            # 与机柜抽屉概览口径一致
            used_u = u_count - free_u
            row_col = parse_rack_location(r.get("location"))
            row, col = row_col if row_col else (None, None)
            racks.append(
                {
                    "inst_uuid": r.get("inst_uuid"),
                    "inst_name": r.get("inst_name"),
                    "model_id": r.get("model_id") or "rack",
                    "row": row,
                    "col": col,
                    "location": r.get("location"),
                    "u_count": u_count,
                    "datacenter_type": _scalar(r.get("datacenter_type")),
                    "datacenter_state": _scalar(r.get("datacenter_state")),
                    "used_u": used_u,
                    "free_u": free_u,
                    "max_free_u": max_free_u,
                    "organization": r.get("organization") or [],
                    "_creator": r.get("_creator"),
                }
            )
    return build_room_layout(racks)


# 业务上限：单次拉取最多返回 N 条机房记录。机房数业务上不会超过该值，
# 不分页（避免前端分页复杂度）；如未来业务量超限再调整。
_ROOM_LIST_PAGE_SIZE = 1000


def list_server_rooms(permission_map: dict | None = None, user_info=None) -> list:
    """列出当前用户可见的 server_room，返回 CMDB 原始字段。

    作为运维分析参数动态选项源。返回字段保持 CMDB 原样
    （_id, inst_name, model_id, organization, ...），不做 _id→id 等重命名。

    复用 ``InstanceManage.instance_list`` 的现成权限过滤逻辑。
    """
    inst_list, _count = InstanceManage.instance_list(
        model_id="server_room",
        params=[],
        page=1,
        page_size=_ROOM_LIST_PAGE_SIZE,
        order="inst_name",
        permission_map=permission_map or {},
    )
    return inst_list or []
