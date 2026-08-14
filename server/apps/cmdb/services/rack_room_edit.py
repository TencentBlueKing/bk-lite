# -- coding: utf-8 --
"""机房/机柜布局编辑：放置与移出。只改关联和位置字段，不删实例。"""
from apps.cmdb.services.rack_room import format_rack_location_label, parse_rack_location
from apps.core.logger import cmdb_logger as logger

PLACEABLE_DEVICE_MODELS = (
    "switch",
    "router",
    "firewall",
    "loadbalance",
    "physcial_server",
)

SCOPE_ROOM = "room"
SCOPE_RACK = "rack"

ACTION_PLACE_CREATE = "place_create"
ACTION_PLACE_EXISTING = "place_existing"
ACTION_UNPLACE = "unplace"

CANDIDATE_SELECTABLE = "selectable"
CANDIDATE_OCCUPIED = "occupied_elsewhere"
CANDIDATE_ALREADY_PLACED = "already_placed"

ROOM_RACK_ASST_ID = "run"
RACK_DEVICE_ASST_ID = "contains"

ACTION_PERMISSION = {
    ACTION_PLACE_CREATE: "asset_info-Add",
    ACTION_PLACE_EXISTING: "asset_info-Edit",
    ACTION_UNPLACE: "asset_info-Edit",
}


class RackRoomEditError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def user_has_asset_permission(user, permission: str) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    perms = getattr(user, "permission", {}) or {}
    if isinstance(perms, dict):
        return permission in (perms.get("cmdb") or set())
    return permission in perms


def required_asset_permission(action: str):
    return ACTION_PERMISSION.get(action)


def model_asst_id(src_model: str, asst_id: str, dst_model: str) -> str:
    return f"{src_model}_{asst_id}_{dst_model}"


def _safe_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _id_set(values) -> set[int]:
    result = set()
    for value in values or []:
        parsed = _safe_int(value)
        if parsed is not None:
            result.add(parsed)
    return result


def has_valid_rack_location(instance: dict | None) -> bool:
    if not instance:
        return False
    return parse_rack_location(instance.get("location")) is not None


def has_device_u_start(instance: dict | None) -> bool:
    if not instance:
        return False
    return bool(_safe_int(instance.get("rack_u_start")))


def classify_rack_candidate(current_room_id, related_room_ids, has_location: bool) -> str:
    current = _safe_int(current_room_id)
    related = _id_set(related_room_ids)
    others = related - ({current} if current is not None else set())
    if others:
        return CANDIDATE_OCCUPIED
    if current is not None and current in related and has_location:
        return CANDIDATE_ALREADY_PLACED
    return CANDIDATE_SELECTABLE


def classify_device_candidate(current_rack_id, related_rack_ids, has_u_start: bool) -> str:
    current = _safe_int(current_rack_id)
    related = _id_set(related_rack_ids)
    others = related - ({current} if current is not None else set())
    if others:
        return CANDIDATE_OCCUPIED
    if current is not None and current in related and has_u_start:
        return CANDIDATE_ALREADY_PLACED
    return CANDIDATE_SELECTABLE


def cell_is_occupied(placed_racks: list, row: int, col: int, exclude_inst_id=None) -> bool:
    exclude = str(exclude_inst_id) if exclude_inst_id is not None else None
    for rack in placed_racks or []:
        if exclude and str(rack.get("inst_id") or rack.get("_id")) == exclude:
            continue
        if rack.get("row") == row and rack.get("col") == col:
            return True
    return False


def device_u_conflict(placed_devices: list, u_start: int, u_size: int, u_count: int, exclude_inst_id=None) -> str | None:
    if not u_start or u_start < 1:
        return "起始 U 位无效"
    if not u_size or u_size < 1:
        return "U 高度无效"
    if not u_count or u_count < 1:
        return "机柜未配置总 U 数"
    u_end = u_start + u_size - 1
    if u_end > u_count:
        return "设备超出机柜 U 位"
    exclude = str(exclude_inst_id) if exclude_inst_id is not None else None
    for device in placed_devices or []:
        if exclude and str(device.get("inst_id") or device.get("_id")) == exclude:
            continue
        other_start = _safe_int(device.get("rack_u_start"))
        other_size = _safe_int(device.get("u_size"))
        if not other_start or not other_size:
            continue
        other_end = other_start + other_size - 1
        if u_start <= other_end and other_start <= u_end:
            return "U 位与已有设备重叠"
    return None


def rack_place_attrs(row: int, col: int) -> dict:
    if row < 1 or col < 1:
        raise RackRoomEditError("机柜位置无效")
    return {"location": format_rack_location_label(row, col)}


def rack_unplace_attrs() -> dict:
    return {"location": ""}


def device_place_attrs(u_start: int, u_size: int) -> dict:
    return {"rack_u_start": u_start, "u_size": u_size}


def device_unplace_attrs() -> dict:
    return {"rack_u_start": ""}


def normalize_device_u_size(value, default=1) -> int:
    parsed = _safe_int(value)
    if parsed and parsed > 0:
        return parsed
    return default


def _ensure_association(src, dst, asst_id: str, operator: str) -> None:
    from apps.cmdb.services.instance import InstanceManage
    from apps.core.exceptions.base_app_exception import BaseAppException

    payload = {
        "src_inst_id": src["_id"],
        "dst_inst_id": dst["_id"],
        "asst_id": asst_id,
        "model_asst_id": model_asst_id(src["model_id"], asst_id, dst["model_id"]),
        "src_model_id": src["model_id"],
        "dst_model_id": dst["model_id"],
    }
    try:
        InstanceManage.instance_association_create(payload, operator)
    except BaseAppException as exc:
        if "repetition" in str(exc).lower() or "already exists" in str(exc).lower():
            logger.info("[RackRoom] skip existing layout association src=%s dst=%s", src.get("_id"), dst.get("_id"))
            return
        raise RackRoomEditError(str(exc)) from exc


def _delete_association(src, dst, asst_id: str, operator: str) -> None:
    from apps.cmdb.services.instance import InstanceManage
    from apps.core.exceptions.base_app_exception import BaseAppException

    src_uuid = src.get("inst_uuid")
    dst_uuid = dst.get("inst_uuid")
    if not src_uuid or not dst_uuid:
        raise RackRoomEditError("实例缺少 inst_uuid，无法解除布局关联")
    key = model_asst_id(src["model_id"], asst_id, dst["model_id"])
    try:
        InstanceManage.instance_association_delete_by_key(
            src_inst_uuid=src_uuid,
            dst_inst_uuid=dst_uuid,
            model_asst_id=key,
            operator=operator,
        )
    except BaseAppException as exc:
        if "不存在" in str(exc):
            return
        raise RackRoomEditError(str(exc)) from exc


def _related_ids(model_id: str, inst_id: int, related_model: str) -> list[int]:
    from apps.cmdb.services.instance import InstanceManage

    relation_map = InstanceManage.instance_association_map(model_id, [int(inst_id)], related_model=related_model)
    return relation_map.get(int(inst_id)) or []


def execute_layout_action(
    *,
    action: str,
    scope: str,
    container: dict,
    operator: str,
    allowed_org_ids: list | None,
    user_groups: list,
    roles: list,
    existing: dict | None = None,
    instance_info: dict | None = None,
    model_id: str | None = None,
    row=None,
    col=None,
    u_start=None,
    u_size=None,
) -> dict:
    """执行已鉴权的布局变更。调用方必须先完成菜单权限与实例 Operate 校验。"""
    from apps.cmdb.services.instance import InstanceManage
    from apps.cmdb.services.rack_room import get_rack_layout, get_room_layout

    if action not in {ACTION_PLACE_CREATE, ACTION_PLACE_EXISTING, ACTION_UNPLACE}:
        raise RackRoomEditError(f"未知操作: {action}")
    if scope not in {SCOPE_ROOM, SCOPE_RACK}:
        raise RackRoomEditError("布局范围无效")

    if scope == SCOPE_ROOM:
        if container.get("model_id") != "server_room":
            raise RackRoomEditError("只能在机房中放置机柜")
        return _execute_room_action(
            action=action,
            room=container,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
            user_groups=user_groups,
            roles=roles,
            existing=existing,
            instance_info=instance_info,
            row=row,
            col=col,
            get_room_layout=get_room_layout,
            InstanceManage=InstanceManage,
        )

    if container.get("model_id") != "rack":
        raise RackRoomEditError("只能在机柜中放置设备")
    return _execute_rack_action(
        action=action,
        rack=container,
        operator=operator,
        allowed_org_ids=allowed_org_ids,
        user_groups=user_groups,
        roles=roles,
        existing=existing,
        instance_info=instance_info,
        model_id=model_id,
        u_start=u_start,
        u_size=u_size,
        get_rack_layout=get_rack_layout,
        InstanceManage=InstanceManage,
    )


def _execute_room_action(
    *,
    action,
    room,
    operator,
    allowed_org_ids,
    user_groups,
    roles,
    existing,
    instance_info,
    row,
    col,
    get_room_layout,
    InstanceManage,
):
    layout = get_room_layout(room["_id"])
    if action == ACTION_UNPLACE:
        if not existing:
            raise RackRoomEditError("机柜实例不存在")
        _delete_association(room, existing, ROOM_RACK_ASST_ID, operator)
        updated = InstanceManage.instance_update(
            user_groups,
            roles,
            existing["_id"],
            rack_unplace_attrs(),
            operator,
            allowed_org_ids=allowed_org_ids,
        )
        return {"action": ACTION_UNPLACE, "instance": updated}

    row = _safe_int(row)
    col = _safe_int(col)
    if row is None or col is None:
        raise RackRoomEditError("机柜位置不能为空")
    attrs = rack_place_attrs(row, col)
    if cell_is_occupied(layout.get("racks") or [], row, col, exclude_inst_id=existing.get("_id") if existing else None):
        raise RackRoomEditError("该网格位已被占用")

    if action == ACTION_PLACE_CREATE:
        payload = dict(instance_info or {})
        payload.pop("row", None)
        payload.pop("col", None)
        payload.update(attrs)
        created = InstanceManage.instance_create("rack", payload, operator, allowed_org_ids=allowed_org_ids)
        _ensure_association(room, created, ROOM_RACK_ASST_ID, operator)
        return {"action": ACTION_PLACE_CREATE, "instance": created}

    if not existing:
        raise RackRoomEditError("机柜实例不存在")
    related = _related_ids("rack", existing["_id"], "server_room")
    status = classify_rack_candidate(room["_id"], related, has_valid_rack_location(existing))
    if status == CANDIDATE_OCCUPIED:
        raise RackRoomEditError("该机柜已在其他机房中，请先在详情中解除关联")
    if status == CANDIDATE_ALREADY_PLACED:
        raise RackRoomEditError("该机柜已在当前机房布局中")
    updated = InstanceManage.instance_update(
        user_groups,
        roles,
        existing["_id"],
        attrs,
        operator,
        allowed_org_ids=allowed_org_ids,
    )
    _ensure_association(room, updated, ROOM_RACK_ASST_ID, operator)
    return {"action": ACTION_PLACE_EXISTING, "instance": updated}


def _execute_rack_action(
    *,
    action,
    rack,
    operator,
    allowed_org_ids,
    user_groups,
    roles,
    existing,
    instance_info,
    model_id,
    u_start,
    u_size,
    get_rack_layout,
    InstanceManage,
):
    layout = get_rack_layout(rack["_id"])
    u_count = _safe_int((layout.get("rack") or {}).get("u_count") or rack.get("u_count")) or 0
    if action == ACTION_UNPLACE:
        if not existing:
            raise RackRoomEditError("设备实例不存在")
        _delete_association(rack, existing, RACK_DEVICE_ASST_ID, operator)
        updated = InstanceManage.instance_update(
            user_groups,
            roles,
            existing["_id"],
            device_unplace_attrs(),
            operator,
            allowed_org_ids=allowed_org_ids,
        )
        return {"action": ACTION_UNPLACE, "instance": updated}

    start = _safe_int(u_start)
    size = normalize_device_u_size(u_size if u_size not in (None, "") else (existing or {}).get("u_size"))
    conflict = device_u_conflict(
        layout.get("placed") or [],
        start or 0,
        size,
        u_count,
        exclude_inst_id=existing.get("_id") if existing else None,
    )
    if conflict:
        raise RackRoomEditError(conflict)
    attrs = device_place_attrs(start, size)

    if action == ACTION_PLACE_CREATE:
        target_model = str(model_id or "").strip()
        if target_model not in PLACEABLE_DEVICE_MODELS:
            raise RackRoomEditError("该模型不能放置到机柜 U 位")
        payload = dict(instance_info or {})
        payload.update(attrs)
        created = InstanceManage.instance_create(target_model, payload, operator, allowed_org_ids=allowed_org_ids)
        _ensure_association(rack, created, RACK_DEVICE_ASST_ID, operator)
        return {"action": ACTION_PLACE_CREATE, "instance": created}

    if not existing:
        raise RackRoomEditError("设备实例不存在")
    if existing.get("model_id") not in PLACEABLE_DEVICE_MODELS:
        raise RackRoomEditError("该模型不能放置到机柜 U 位")
    related = _related_ids(existing["model_id"], existing["_id"], "rack")
    status = classify_device_candidate(rack["_id"], related, has_device_u_start(existing))
    if status == CANDIDATE_OCCUPIED:
        raise RackRoomEditError("该设备已在其他机柜中，请先在详情中解除关联")
    if status == CANDIDATE_ALREADY_PLACED:
        raise RackRoomEditError("该设备已在当前机柜布局中")
    updated = InstanceManage.instance_update(
        user_groups,
        roles,
        existing["_id"],
        attrs,
        operator,
        allowed_org_ids=allowed_org_ids,
    )
    _ensure_association(rack, updated, RACK_DEVICE_ASST_ID, operator)
    return {"action": ACTION_PLACE_EXISTING, "instance": updated}


def list_layout_candidates(
    *,
    scope: str,
    container: dict,
    model_id: str,
    permission_map: dict | None,
    page: int = 1,
    page_size: int = 20,
    search: str = "",
) -> dict:
    from apps.cmdb.services.instance import InstanceManage

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    if scope == SCOPE_ROOM:
        if model_id != "rack":
            raise RackRoomEditError("机房布局只能选择机柜")
        related_model = "server_room"
        container_id = container["_id"]
        classify = classify_rack_candidate
        placed = has_valid_rack_location
    elif scope == SCOPE_RACK:
        if model_id not in PLACEABLE_DEVICE_MODELS:
            raise RackRoomEditError("该模型不能放置到机柜 U 位")
        related_model = "rack"
        container_id = container["_id"]
        classify = classify_device_candidate
        placed = has_device_u_start
    else:
        raise RackRoomEditError("布局范围无效")

    params = []
    keyword = str(search or "").strip()
    if keyword:
        params.append({"field": "inst_name", "type": "str*", "value": keyword})
    rows, count = InstanceManage.instance_list(
        model_id=model_id,
        params=params,
        page=page,
        page_size=page_size,
        order="inst_name",
        permission_map=permission_map or {},
    )
    inst_ids = [_safe_int(row.get("_id")) for row in rows or [] if _safe_int(row.get("_id")) is not None]
    relation_map = InstanceManage.instance_association_map(model_id, inst_ids, related_model=related_model) if inst_ids else {}
    items = []
    for row in rows or []:
        inst_id = _safe_int(row.get("_id"))
        status = classify(container_id, relation_map.get(inst_id) or [], placed(row))
        if status == CANDIDATE_ALREADY_PLACED:
            continue
        items.append(
            {
                "inst_uuid": row.get("inst_uuid"),
                "inst_name": row.get("inst_name"),
                "model_id": row.get("model_id"),
                "organization": row.get("organization") or [],
                "_creator": row.get("_creator"),
                "u_size": row.get("u_size"),
                "status": status,
            }
        )
    return {"count": count, "items": items}
