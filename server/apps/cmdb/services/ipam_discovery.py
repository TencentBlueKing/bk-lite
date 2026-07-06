# -- coding: utf-8 --
"""IP 发现采集 server 端：子网参数提取、VM 指标落库、IPAM 台账回写。"""
from datetime import datetime
from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.core.logger import cmdb_logger as logger


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

def _load_subnet_ips(subnet_id) -> list:
    """查询某子网下所有 IP 记录（含手工和自动发现）。"""
    with GraphClient() as ag:
        rows, _ = ag.query_entity(INSTANCE, [
            {"field": "model_id", "type": "str=", "value": "ip"},
            {"field": "subnet_id", "type": "str=", "value": str(subnet_id)},
        ])
    return rows or []


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
            skip_permission_check=True, record_change=False,
        )
    else:
        InstanceManage.instance_create("ip", payload, "system", record_change=False)


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

    P0-1.2 兜底:子网不存在或子网无 organization 时(ip 模型 is_required=True),
    早返回 skipped=True,避免 instance_create 抛「organization is empty」。
    """
    # DEFECT A fix: load subnet to extract organization so instance_create gets a
    # real org value (ip model has is_required=True for organization).
    subnet_rows = _load_subnets_by_ids([subnet_id])
    if not subnet_rows:
        logger.warning("[IPDiscovery] 子网不存在,跳过 subnet_id=%s alive_count=%s", subnet_id, len(alive))
        return {"created": 0, "updated": 0, "offline": 0, "skipped": True}
    organization = subnet_rows[0].get("organization") or []
    if not organization:
        logger.warning("[IPDiscovery] 子网 %s 缺少 organization,ip 模型要求必填,跳过", subnet_id)
        return {"created": 0, "updated": 0, "offline": 0, "skipped": True}

    existing = _load_subnet_ips(subnet_id)
    existing_by_addr = {i.get("ip_addr"): i for i in existing}
    alive_addrs = {a["ip"] for a in alive}

    created = updated = offline = 0
    for a in alive:
        prev = existing_by_addr.get(a["ip"])
        if prev and prev.get("auto_collect") is not True:
            # 手工录入不被自动发现覆盖（仅 auto_collect is True 的记录归发现采集所有、可写）
            continue
        _upsert_alive_ip(
            existing_id=(prev or {}).get("_id"),
            subnet_id=subnet_id,
            ip_addr=a["ip"],
            mac=a.get("mac", ""),
            organization=organization,
        )
        if prev:
            updated += 1
        else:
            created += 1

    for ip in existing:
        if ip.get("auto_collect") is True and ip.get("ip_addr") not in alive_addrs:
            _mark_offline(ip["_id"])
            offline += 1

    _writeback_subnet_utilization([subnet_id])
    return {"created": created, "updated": updated, "offline": offline}


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
    summary = {"created": 0, "updated": 0, "offline": 0}
    for subnet_id in subnet_ids:
        result = apply_discovery_result(subnet_id, alive_by_subnet.get(str(subnet_id), []))
        for key in summary:
            summary[key] += int(result.get(key, 0))
    return summary
