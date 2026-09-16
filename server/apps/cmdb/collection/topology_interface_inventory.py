# -*- coding: utf-8 -*-
"""拓扑重放：用已入库接口解析端口，并独立写入 connect，不走接口对账/heartbeat。"""

from apps.cmdb.collection.collect_plugin.topology.parse import build_interface_name_candidates, normalize_interface_name, normalize_mac
from apps.cmdb.constants.constants import INSTANCE
from apps.core.logger import cmdb_logger as logger

INTERFACE_MODEL_ID = "interface"
_LOAD_FAILED_STAGE = "load_task_interfaces"
_APPLY_FAILED_STAGE = "apply_topology_relationships"


def _iface_belongs_to_device(iface, device_id: str) -> bool:
    prefix = f"{device_id}-"
    inst_name = str(iface.get("inst_name") or "")
    self_device = str(iface.get("self_device") or "")
    return inst_name.startswith(prefix) or self_device.startswith(prefix) or self_device == device_id


def _iface_name_values(iface, device_id: str) -> list[str]:
    values = [iface.get("name"), iface.get("inst_name")]
    inst_name = str(iface.get("inst_name") or "")
    prefix = f"{device_id}-"
    if inst_name.startswith(prefix):
        remainder = inst_name[len(prefix) :]
        values.append(remainder)
        _device_type, separator, suffix = remainder.partition("-")
        if separator and suffix:
            values.append(suffix)
    return values


def _name_keys(*values) -> set[str]:
    keys: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        keys.add(text)
        keys.update(build_interface_name_candidates(text))
        normalized = normalize_interface_name(text)
        if normalized:
            keys.add(normalized)
    return keys


def _unique_inst_name(hits) -> str | None:
    names = {str(item.get("inst_name") or "") for item in hits if item.get("inst_name")}
    names.discard("")
    if len(names) == 1:
        return next(iter(names))
    return None


def match_port_to_inventory_inst_name(port, interfaces) -> str | None:
    """把流水线端口（host/ifindex + 口名/MAC）唯一匹配到已入库 interface.inst_name。"""
    if not isinstance(port, dict):
        return None
    device_id = str(port.get("device_id") or "").strip()
    if not device_id:
        return None
    scoped = [item for item in interfaces or [] if isinstance(item, dict) and _iface_belongs_to_device(item, device_id)]
    if not scoped:
        return None

    port_names = {str(port.get(key) or "").strip() for key in ("ifname", "ifalias", "ifdescr", "display_name")}
    port_names.discard("")

    exact = _unique_inst_name([item for item in scoped if str(item.get("name") or "").strip() in port_names])
    if exact:
        return exact

    port_keys = _name_keys(*port_names)
    if port_keys:
        normalized = _unique_inst_name([item for item in scoped if _name_keys(*_iface_name_values(item, device_id)) & port_keys])
        if normalized:
            return normalized

    port_mac = normalize_mac(str(port.get("mac") or ""))
    if port_mac:
        mac_hit = _unique_inst_name([item for item in scoped if normalize_mac(str(item.get("mac") or "")) == port_mac])
        if mac_hit:
            return mac_hit
    return None


def merge_inventory_port_index(index_map, ports, interfaces) -> dict:
    """补全 { (device_id, ifindex): inst_name }，已有本轮映射不覆盖。"""
    target = index_map if index_map is not None else {}
    for port in ports or []:
        if not isinstance(port, dict):
            continue
        device_id = str(port.get("device_id") or "").strip()
        ifindex = str(port.get("ifindex") or "").strip()
        if not device_id or not ifindex:
            continue
        key = (device_id, ifindex)
        if target.get(key):
            continue
        inst_name = match_port_to_inventory_inst_name(port, interfaces)
        if inst_name:
            target[key] = inst_name
    return target


def port_index_needs_inventory(index_map, ports) -> bool:
    mapping = index_map or {}
    for port in ports or []:
        if not isinstance(port, dict):
            continue
        device_id = str(port.get("device_id") or "").strip()
        ifindex = str(port.get("ifindex") or "").strip()
        if device_id and ifindex and not mapping.get((device_id, ifindex)):
            return True
    return False


def load_task_interfaces(task_id) -> list[dict]:
    """加载本采集任务已入库的 interface；失败返回空列表，不编造。"""
    if task_id in (None, ""):
        return []
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    rows_by_id = {}
    lookups = [("str=", str(task_id))]
    try:
        lookups.append(("int=", int(task_id)))
    except (TypeError, ValueError):
        pass
    with GraphClient() as ag:
        for field_type, value in lookups:
            found, _ = ag.query_entity(
                INSTANCE,
                [
                    {"field": "model_id", "type": "str=", "value": INTERFACE_MODEL_ID},
                    {"field": "collect_task", "type": field_type, "value": value},
                ],
            )
            for row in found or []:
                if not isinstance(row, dict):
                    continue
                row_id = row.get("_id")
                if row_id in (None, ""):
                    continue
                rows_by_id[row_id] = row
    return list(rows_by_id.values())


def apply_topology_relationships(relationships, *, task_id=None) -> dict:
    """按已解析的 inst_name 直接写 connect，不依赖本轮接口 CRUD / heartbeat。"""
    result = {"success": 0, "failed": 0}
    if not relationships:
        return result
    from apps.cmdb.collection.common import Management
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    names = []
    seen = set()
    for relation in relationships:
        if not isinstance(relation, dict):
            continue
        source_name = str(relation.get("source_inst_name") or "")
        if source_name and source_name not in seen:
            seen.add(source_name)
            names.append(source_name)
    if not names:
        return result

    writer = Management.__new__(Management)
    with GraphClient() as ag:
        sources = ag.query_entity_by_inst_names(names, model_id=INTERFACE_MODEL_ID) or []
        source_by_name = {}
        task_key = str(task_id) if task_id not in (None, "") else ""
        for item in sources:
            if not isinstance(item, dict) or not item.get("inst_name") or item.get("_id") in (None, ""):
                continue
            inst_name = str(item["inst_name"])
            owner = str(item.get("collect_task") or "")
            existing = source_by_name.get(inst_name)
            if existing is None:
                source_by_name[inst_name] = item
                continue
            if task_key and owner == task_key and str(existing.get("collect_task") or "") != task_key:
                source_by_name[inst_name] = item

        for relation in relationships:
            if not isinstance(relation, dict):
                continue
            source = source_by_name.get(str(relation.get("source_inst_name") or ""))
            target_name = str(relation.get("target_inst_name") or "")
            if not source or not target_name:
                result["failed"] += 1
                continue
            asso_result = writer.setting_assos(
                {"model_id": INTERFACE_MODEL_ID, "_id": source["_id"], "inst_name": source.get("inst_name")},
                [
                    {
                        "asst_id": relation.get("asst_id", "connect"),
                        "inst_name": target_name,
                        "model_asst_id": relation.get("model_asst_id", "interface_connect_interface"),
                        "model_id": relation.get("model_id", INTERFACE_MODEL_ID),
                    }
                ],
            )
            if asso_result.get("failed"):
                result["failed"] += 1
            else:
                result["success"] += 1
    return result


def load_task_interfaces_safe(task_id) -> list[dict]:
    try:
        return load_task_interfaces(task_id)
    except Exception as exc:  # noqa: BLE001 — 拓扑主路径不因库存查询失败中断
        logger.warning(
            "event=network_topology_inventory_load_failed task_id=%s failed_stage=%s error_type=%s",
            task_id or "",
            _LOAD_FAILED_STAGE,
            type(exc).__name__,
        )
        return []


def apply_topology_relationships_safe(relationships, *, task_id=None) -> dict:
    try:
        return apply_topology_relationships(relationships, task_id=task_id)
    except Exception as exc:  # noqa: BLE001 — 边写入失败保留快照，不阻断重放标记
        logger.warning(
            "event=network_topology_relationship_apply_failed task_id=%s failed_stage=%s error_type=%s",
            task_id or "",
            _APPLY_FAILED_STAGE,
            type(exc).__name__,
        )
        return {"success": 0, "failed": len(relationships or [])}
