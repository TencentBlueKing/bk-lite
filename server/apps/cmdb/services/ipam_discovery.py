# -- coding: utf-8 --
"""IP 发现采集 server 端：子网参数提取、VM 指标落库、IPAM 台账回写。"""
from datetime import datetime
from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.core.exceptions.base_app_exception import BaseAppException


def extract_subnet_discovery_params(task) -> tuple:
    """从采集任务 model 实例或 dict 中提取 (subnet_ids, scan_method, ports)。

    存储约定（见 instances 字段注释）：
        instances = {"subnet_ids": [1, 2, ...], "scan_method": "icmp", "ports": [22, 80, ...]}

    返回 (subnet_ids: list, scan_method: str, ports: list | None)。
    subnet_ids 缺失时返回空列表；scan_method 缺失时默认 "icmp"；ports 缺失时返回 None（由
    端口缺失时由下发侧/采集侧使用默认端口）。
    """
    if hasattr(task, "instances"):
        raw_instances = task.instances
        raw_params = getattr(task, "params", {}) or {}
    else:
        raw_instances = task.get("instances", {})
        raw_params = task.get("params", {}) or {}

    if not isinstance(raw_instances, dict):
        raw_instances = {}
    if not isinstance(raw_params, dict):
        raw_params = {}

    raw_instances = {**raw_instances, **raw_params}

    subnet_ids = raw_instances.get("subnet_ids", [])
    if not isinstance(subnet_ids, list):
        subnet_ids = list(subnet_ids) if subnet_ids else []

    scan_method = raw_instances.get("scan_method", "icmp") or "icmp"
    ports = raw_instances.get("ports", None)
    if ports is not None and not isinstance(ports, list):
        ports = list(ports)

    return subnet_ids, scan_method, ports


def _load_subnets_by_ids(subnet_ids: list) -> list:
    ids = [int(i) for i in subnet_ids]
    with GraphClient() as ag:
        rows, _ = ag.query_entity(INSTANCE, [
            {"field": "model_id", "type": "str=", "value": "subnet"},
            {"field": "id", "type": "id[]", "value": ids}])
    return rows or []


# ---------------------------------------------------------------------------
# 回写层：apply_discovery_result (§13.4)
# ---------------------------------------------------------------------------

def _dedupe_ip_rows(rows: list) -> list:
    result = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        identity = row.get("_id") or (row.get("subnet_id"), row.get("ip_addr"))
        if identity in seen:
            continue
        seen.add(identity)
        result.append(row)
    return result


def _load_subnet_ips_by_field(subnet_id) -> list:
    """兼容旧数据：按 subnet_id 字段查询某子网下所有 IP 记录。"""
    with GraphClient() as ag:
        rows, _ = ag.query_entity(INSTANCE, [
            {"field": "model_id", "type": "str=", "value": "ip"},
            {"field": "subnet_id", "type": "str=", "value": str(subnet_id)},
        ])
    return rows or []


def _load_subnet_associated_ips(subnet_id) -> list:
    """按 subnet_group_ip 关联查询子网下的 IP。"""
    from apps.cmdb.services.instance import InstanceManage

    associations = InstanceManage.instance_association_instance_list("subnet", int(subnet_id)) or []
    rows = []
    for item in associations:
        if item.get("model_asst_id") != "subnet_group_ip":
            continue
        rows.extend(item.get("inst_list") or [])
    return rows


def _load_subnet_ips(subnet_id) -> list:
    """查询某子网下所有 IP 记录（关联优先，字段兜底兼容历史数据）。"""
    return _dedupe_ip_rows(_load_subnet_associated_ips(subnet_id) + _load_subnet_ips_by_field(subnet_id))


def _ensure_subnet_ip_association(subnet_id, ip_id) -> dict:
    """确保 subnet --group--> ip 关联存在；重复关联视为成功幂等。"""
    from apps.cmdb.services.instance import InstanceManage

    data = {
        "src_inst_id": int(subnet_id),
        "dst_inst_id": int(ip_id),
        "asst_id": "group",
        "src_model_id": "subnet",
        "dst_model_id": "ip",
        "model_asst_id": "subnet_group_ip",
    }
    try:
        InstanceManage.instance_association_create(data, "system")
        return {"success": [data], "failed": []}
    except BaseAppException as exc:
        message = getattr(exc, "message", "") or str(exc)
        if "repetition" in message:
            return {"success": [data], "failed": []}
        error_data = dict(data)
        error_data["error"] = message
        return {"success": [], "failed": [error_data]}


def _upsert_alive_ip(existing_id=None, subnet_id=None, ip_addr=None, mac="", organization=None):
    """创建或更新在线 IP 记录。subnet_id 以字符串写入，保证查询一致性。"""
    from apps.cmdb.services.instance import InstanceManage
    payload = {
        "ip_addr": ip_addr,
        "inst_name": ip_addr,
        "subnet_id": str(subnet_id),
        "ip_status": ["online"],
        "auto_collect": True,
        "mac": mac,
        "organization": organization or [],
        "collect_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if existing_id:
        InstanceManage.instance_update(
            [], [], existing_id, payload, "system",
            skip_permission_check=True, allowed_org_ids=organization or [], record_change=False,
        )
        ip_id = existing_id
    else:
        created = InstanceManage.instance_create(
            "ip",
            payload,
            "system",
            allowed_org_ids=organization or [],
            record_change=False,
        )
        ip_id = created["_id"]
    payload_with_id = {**payload, "_id": ip_id, "model_id": "ip"}
    assos_result = _ensure_subnet_ip_association(subnet_id, ip_id)
    return {"_id": ip_id, "inst_info": payload_with_id, "assos_result": assos_result}


def _mark_offline(ip_id):
    """将单条自动发现 IP 置为离线，不影响手工记录。"""
    from apps.cmdb.services.instance import InstanceManage
    InstanceManage.instance_update(
        [], [], ip_id, {"ip_status": ["offline"]}, "system",
        skip_permission_check=True, record_change=False,
    )


def _writeback_subnet_utilization(subnet_ids):
    """重算子网利用率统计（复用 P1 同款 helper，保持口径一致）。"""
    from apps.cmdb.services.ipam_reconcile import _writeback_subnet_utilization as wb
    wb(set(subnet_ids))


def apply_discovery_result(subnet_id, alive: list) -> dict:
    """活跃 IP 回写台账。规格 §13.4。

    - 在线 IP → 创建/更新 ip 实例（online + MAC + auto_collect=True）。
    - 原自动发现 IP 未出现在本次扫描结果 → 标记 offline。
    - 手工记录（auto_collect=False）→ 永不修改。
    - IP 冲突（同地址多记录）不在此处裁决，交由 P1 周期对账任务处理。
    - 最后回写子网利用率统计（与 P1 reconcile 共享同一 _writeback_subnet_utilization）。
    """
    # DEFECT A fix: load subnet to extract organization so instance_create gets a
    # real org value (ip model has is_required=True for organization).
    subnet_rows = _load_subnets_by_ids([subnet_id])
    organization = subnet_rows[0].get("organization", []) if subnet_rows else []

    existing = _load_subnet_ips(subnet_id)
    existing_by_addr = {i.get("ip_addr"): i for i in existing}
    alive_addrs = {a["ip"] for a in alive}

    created = updated = offline = 0
    format_data = {"add": [], "update": [], "delete": [], "association": [], "all": 0}
    for a in alive:
        prev = existing_by_addr.get(a["ip"])
        if prev and prev.get("auto_collect") is not True:
            # 手工录入不被自动发现覆盖（仅 auto_collect is True 的记录归发现采集所有、可写）
            continue
        upsert_result = _upsert_alive_ip(
            existing_id=(prev or {}).get("_id"),
            subnet_id=subnet_id,
            ip_addr=a["ip"],
            mac=a.get("mac", ""),
            organization=organization,
        ) or {}
        upsert_inst_info = upsert_result.get("inst_info") or {
            "_id": (prev or {}).get("_id"),
            "model_id": "ip",
            "inst_name": a["ip"],
            "ip_addr": a["ip"],
            "subnet_id": str(subnet_id),
            "ip_status": ["online"],
            "auto_collect": True,
            "mac": a.get("mac", ""),
            "organization": organization,
        }
        if upsert_result.get("assos_result"):
            for status, rows in upsert_result["assos_result"].items():
                for row in rows:
                    format_data["association"].append({**row, "_status": status})
        if prev:
            updated += 1
            format_data["update"].append({"_status": "success", **upsert_inst_info})
        else:
            created += 1
            format_data["add"].append({"_status": "success", **upsert_inst_info})

    for ip in existing:
        if ip.get("auto_collect") is True and ip.get("ip_addr") not in alive_addrs:
            _mark_offline(ip["_id"])
            offline += 1
            format_data["update"].append({
                "_status": "success",
                "_id": ip["_id"],
                "model_id": "ip",
                "inst_name": ip.get("inst_name") or ip.get("ip_addr"),
                "ip_addr": ip.get("ip_addr"),
                "subnet_id": str(subnet_id),
                "ip_status": ["offline"],
                "auto_collect": True,
            })

    _writeback_subnet_utilization([subnet_id])
    format_data["all"] = len(format_data["add"]) + len(format_data["update"]) + len(format_data["delete"])
    return {"created": created, "updated": updated, "offline": offline, "format_data": format_data}


def apply_ip_discovery_vm_rows(task, rows: list[dict]) -> dict:
    """把 VM 中的 ip_info 指标行回写到 IPAM 台账。

    C2 链路下 Stargazer 不再通过 NATS 回调结果，CMDB 周期任务从 VM 拉取
    `ip_info` 指标后调用本函数。函数以任务所选子网为准，因此某个子网本轮
    没有任何在线 IP 时，也会触发原自动发现记录置离线。
    """
    selected_subnet_ids, _, _ = extract_subnet_discovery_params(task)
    alive_by_subnet: dict[str, list[dict]] = {}
    for row in rows or []:
        if row.get("collect_status", "success") == "failed":
            continue
        subnet_id = str(row.get("subnet_id") or "").strip()
        ip_addr = str(row.get("ip_addr") or row.get("ip") or "").strip()
        if not subnet_id or not ip_addr:
            continue
        alive_by_subnet.setdefault(subnet_id, []).append(
            {"ip": ip_addr, "mac": row.get("mac", "")}
        )

    subnet_ids = [str(item) for item in selected_subnet_ids] or sorted(alive_by_subnet)
    summary = {
        "created": 0,
        "updated": 0,
        "offline": 0,
        "format_data": {"add": [], "update": [], "delete": [], "association": [], "all": 0},
    }
    for subnet_id in subnet_ids:
        result = apply_discovery_result(subnet_id, alive_by_subnet.get(str(subnet_id), []))
        for key in ("created", "updated", "offline"):
            summary[key] += int(result.get(key, 0))
        result_format_data = result.get("format_data") or {}
        for key in ("add", "update", "delete", "association"):
            summary["format_data"][key].extend(result_format_data.get(key) or [])
        summary["format_data"]["all"] += int(result_format_data.get("all", 0) or 0)
    return summary
