"""把 CMDB 实例 UUID 映射成监控实例标识，供告警分布复用同一套分组。"""

from __future__ import annotations

from apps.monitor.services.generic_query import GenericQueryError
from apps.monitor.services.generic_query_limits import CMDB_ALERT_UUID_MAX

_UUID_CHUNK = 200


def normalize_cmdb_uuids(uuids) -> list[str]:
    """收下平铺的 uuid 列表。空列表失败，超出上限失败。"""
    uuid_list = _text_list(uuids, "实例标识")
    if not uuid_list:
        raise GenericQueryError("实例标识不能为空")
    if len(uuid_list) > CMDB_ALERT_UUID_MAX:
        raise GenericQueryError(f"实例标识不能超过 {CMDB_ALERT_UUID_MAX} 个")
    return uuid_list


def fetch_cmdb_monitor_mappings(uuids: list[str], user_info) -> list[dict]:
    """复用现有 CMDB 身份映射，按 uuid 返回有权看到的模型与监控实例标识。"""
    from apps.cmdb.nats import nats as cmdb_nats
    from apps.cmdb.services.instance import InstanceManage
    from apps.cmdb.services.instance_identity import optional_inst_uuid

    unique: list[str] = []
    seen: set[str] = set()
    for raw in uuids:
        normalized = optional_inst_uuid(raw) or str(raw or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    if not unique:
        return []

    permission_map = cmdb_nats._build_nats_permission_map(user_info)
    if permission_map is None:
        return []
    user = cmdb_nats._normalize_permission_user(
        (user_info or {}).get("user"),
        domain=(user_info or {}).get("domain"),
    )
    entities: list[dict] = []
    for index in range(0, len(unique), _UUID_CHUNK):
        chunk = unique[index : index + _UUID_CHUNK]
        entities.extend(InstanceManage.query_entity_by_uuids(chunk) or [])

    items = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        inst_uuid = optional_inst_uuid(entity.get("inst_uuid")) or str(entity.get("inst_uuid") or "").strip()
        if not inst_uuid:
            continue
        if not InstanceManage._has_topology_view_permission(entity, permission_map, user=user):
            continue
        monitor_id = entity.get("monitor_id")
        items.append(
            {
                "inst_uuid": inst_uuid,
                "model_id": str(entity.get("model_id") or "").strip(),
                "monitor_id": "" if monitor_id in (None, "") else str(monitor_id),
            }
        )
    return items


def select_mapped_monitor_ids(uuids: list[str], mappings: list[dict]) -> list[str]:
    """按 uuid 取已关联的监控实例标识。对不上、无权限或未关联监控的跳过。"""
    from apps.cmdb.services.instance_identity import optional_inst_uuid

    by_uuid: dict[str, dict] = {}
    for item in mappings:
        key = str(item.get("inst_uuid") or "").strip()
        if key and key not in by_uuid:
            by_uuid[key] = item

    selected: list[str] = []
    seen: set[str] = set()
    for raw_uuid in uuids:
        uuid = optional_inst_uuid(raw_uuid) or str(raw_uuid or "").strip()
        item = by_uuid.get(uuid)
        if item is None:
            continue
        monitor_id = str(item.get("monitor_id") or "").strip()
        if not monitor_id or monitor_id in seen:
            continue
        seen.add(monitor_id)
        selected.append(monitor_id)
    return selected


def _text_list(value, label: str) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(part).strip() for part in value if str(part).strip()]
    raise GenericQueryError(f"{label}格式错误")
