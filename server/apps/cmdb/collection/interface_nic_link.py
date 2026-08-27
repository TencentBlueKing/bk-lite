# -*- coding: utf-8 -*-
"""拓扑关系计算：FDB 学到的 MAC 匹配已入库 nic，写出 interface connect nic。

不把 nic 改成 interface，不编造 nic，不把逻辑主机 host 混进这条路径。
"""
from apps.cmdb.collection.nic_inventory import normalize_nic_mac
from apps.core.logger import cmdb_logger as logger

INTERFACE_MODEL_ID = "interface"
NIC_MODEL_ID = "nic"
CONNECT_ASST_ID = "connect"
INTERFACE_CONNECT_NIC = "interface_connect_nic"
LEARNED_FDB_STATUSES = frozenset({"3", "learned", "learned(3)"})
_NEIGHBOR_MAC_FIELDS = (
    "remote_device_name",
    "remote_port_name",
    "remote_chassis_id",
    "remote_address",
)
_NEIGHBOR_RAW_MAC_FIELDS = (
    "LLDP-RemChassisId",
    "LLDP-RemPortId",
    "CDP-DeviceId",
    "FDP-DeviceId",
)


def _raw_to_nic_mac(raw) -> str:
    token = str(raw or "").strip().lower()
    if token.startswith("0x"):
        token = token[2:]
    return normalize_nic_mac(token)


def inventory_interface_macs(normalized) -> set[str]:
    """拓扑本轮已经作为 interface 入库的 MAC（交换机端口自身 MAC）。"""
    macs = set()
    ports = (normalized or {}).get("ports") or []
    for port in ports:
        if not isinstance(port, dict):
            continue
        mac = normalize_nic_mac(port.get("mac"))
        if mac:
            macs.add(mac)
    return macs


def learned_fdb_macs(normalized) -> set[str]:
    macs = set()
    for entry in (normalized or {}).get("fdb_observations") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status", "")) not in LEARNED_FDB_STATUSES:
            continue
        mac = normalize_nic_mac(entry.get("mac"))
        if mac:
            macs.add(mac)
    return macs


def _neighbor_mac_candidates(item) -> list[str]:
    if not isinstance(item, dict):
        return []
    seen = set()
    candidates = []

    def _add(raw):
        mac = _raw_to_nic_mac(raw)
        if mac and mac not in seen:
            seen.add(mac)
            candidates.append(mac)

    for field in _NEIGHBOR_MAC_FIELDS:
        _add(item.get(field))
    raw_fields = item.get("raw_remote_fields") or {}
    if isinstance(raw_fields, dict):
        for field in _NEIGHBOR_RAW_MAC_FIELDS:
            _add(raw_fields.get(field))
    return candidates


def neighbor_mac_candidates(unresolved_neighbors) -> set[str]:
    macs = set()
    for item in unresolved_neighbors or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("resolution_state", "")) != "unresolved_remote":
            continue
        protocol = str(item.get("protocol", "") or "")
        if protocol not in {"lldp", "cdp", "fdp"}:
            continue
        macs.update(_neighbor_mac_candidates(item))
    return macs


def candidate_nic_lookup_macs(normalized, unresolved_neighbors) -> set[str]:
    """需要向 CMDB 查询的 MAC：学到的 FDB MAC + 未解析邻居里像 MAC 的值，排除本轮 interface MAC。"""
    interface_macs = inventory_interface_macs(normalized)
    return (learned_fdb_macs(normalized) | neighbor_mac_candidates(unresolved_neighbors)) - interface_macs


def nic_index_from_instances(instances) -> dict[str, dict]:
    """只收 model_id=nic 的实例；host 即使 MAC 相同也丢掉。"""
    index = {}
    for item in instances or []:
        if not isinstance(item, dict):
            continue
        if item.get("model_id") != NIC_MODEL_ID:
            continue
        mac = normalize_nic_mac(item.get("nic_mac") or item.get("inst_name"))
        if not mac:
            continue
        index[mac] = {
            "inst_name": str(item.get("inst_name") or mac),
            "model_id": NIC_MODEL_ID,
        }
    return index


def interface_connect_nic_relation(source_inst_name: str, nic_inst_name: str) -> dict:
    return {
        "source_inst_name": source_inst_name,
        "target_inst_name": nic_inst_name,
        "model_id": NIC_MODEL_ID,
        "asst_id": CONNECT_ASST_ID,
        "model_asst_id": INTERFACE_CONNECT_NIC,
    }


def bind_fdb_learned_macs_to_nics(
    *,
    normalized,
    nic_index: dict,
    resolve_source_inst_name,
) -> tuple[list[dict], set[str], list[dict]]:
    """FDB 学到的 MAC → 已有 nic。未命中只丢弃并计入 unmatched。"""
    interface_macs = inventory_interface_macs(normalized)
    relationships = []
    unmatched = set()
    dropped = []
    seen = set()
    for entry in (normalized or {}).get("fdb_observations") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status", "")) not in LEARNED_FDB_STATUSES:
            continue
        mac = normalize_nic_mac(entry.get("mac"))
        if not mac:
            continue
        if mac in interface_macs:
            continue
        source_inst_name = resolve_source_inst_name(entry.get("local_port_id"))
        if not source_inst_name:
            unmatched.add(mac)
            dropped.append({"mac": mac, "drop_reason": "interface_not_in_inventory", "evidence_source": "fdb"})
            continue
        nic = nic_index.get(mac)
        if not nic:
            unmatched.add(mac)
            dropped.append({"mac": mac, "drop_reason": "unmatched_mac", "evidence_source": "fdb"})
            continue
        relation = interface_connect_nic_relation(source_inst_name, nic["inst_name"])
        edge_key = (relation["source_inst_name"], relation["target_inst_name"], relation["model_asst_id"])
        if edge_key in seen:
            continue
        seen.add(edge_key)
        relationships.append(relation)
    return relationships, unmatched, dropped


def bind_unresolved_neighbors_to_nics(
    *,
    unresolved_neighbors,
    nic_index: dict,
    interface_macs: set[str],
    resolve_source_inst_name,
) -> list[dict]:
    """LLDP/CDP 对端未能匹配交换机 interface 时，用机箱/端口 MAC 试 nic（便宜路径）。"""
    relationships = []
    seen = set()
    for item in unresolved_neighbors or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("resolution_state", "")) != "unresolved_remote":
            continue
        protocol = str(item.get("protocol", "") or "")
        if protocol not in {"lldp", "cdp", "fdp"}:
            continue
        source_inst_name = resolve_source_inst_name(item.get("source_port_id"))
        if not source_inst_name:
            continue
        for mac in _neighbor_mac_candidates(item):
            if mac in interface_macs:
                continue
            nic = nic_index.get(mac)
            if not nic:
                continue
            relation = interface_connect_nic_relation(source_inst_name, nic["inst_name"])
            edge_key = (relation["source_inst_name"], relation["target_inst_name"], relation["model_asst_id"])
            if edge_key in seen:
                continue
            seen.add(edge_key)
            relationships.append(relation)
            break
    return relationships


def load_nic_instances_by_mac(macs) -> list[dict]:
    """按 inst_name（规范化 MAC）查询已入库 nic，绝不查询或创建 host。"""
    mac_list = [mac for mac in macs if mac]
    if not mac_list:
        return []
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    with GraphClient() as ag:
        return ag.query_entity_by_inst_names(mac_list, model_id=NIC_MODEL_ID) or []


_ENSURE_FAILED_TEMPLATE = "event=network_topology_nic_association_ensure_failed task_id=%s failed_stage=%s error_type=%s"
_ENSURE_FAILED_STAGE = "ensure_interface_connect_nic_association"


def _log_nic_association_ensure_failed(task_id, error_type: str) -> None:
    logger.warning(_ENSURE_FAILED_TEMPLATE, task_id or "", _ENSURE_FAILED_STAGE, error_type)


def ensure_interface_connect_nic_association(task_id=None) -> bool:
    """存量环境若缺少 interface_connect_nic 模型关联则补上；已存在则幂等成功。"""
    from apps.cmdb.services.model import ModelManage
    from apps.core.exceptions.base_app_exception import BaseAppException

    existing = ModelManage.model_association_info_search(INTERFACE_CONNECT_NIC)
    if existing:
        return True
    src = ModelManage.search_model_info(INTERFACE_MODEL_ID)
    dst = ModelManage.search_model_info(NIC_MODEL_ID)
    if not src or not dst:
        _log_nic_association_ensure_failed(task_id, "model_not_found")
        return False
    try:
        ModelManage.model_association_create(
            src_id=src["_id"],
            dst_id=dst["_id"],
            src_model_id=INTERFACE_MODEL_ID,
            dst_model_id=NIC_MODEL_ID,
            asst_id=CONNECT_ASST_ID,
            asst_name="关联",
            mapping="n:n",
            on_delete="none",
            is_pre=True,
            model_asst_id=INTERFACE_CONNECT_NIC,
        )
    except BaseAppException as exc:
        message = str(getattr(exc, "message", exc) or "")
        if "repetition" in message.lower() or "already exists" in message.lower():
            return True
        _log_nic_association_ensure_failed(task_id, type(exc).__name__)
        return False
    return True
