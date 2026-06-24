# -- coding: utf-8 --
"""IP 发现采集 server 端：选子网范围推导、NATS 下发 payload、回调回写。规格 §13。"""
import ipaddress
from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient

DEFAULT_PORTS = [22, 80, 443, 3389]

# ---------------------------------------------------------------------------
# 选子网 IP 发现任务路由（§13 工作项 2）
# ---------------------------------------------------------------------------
# task 中用于存储子网参数的字段：
#   instances = {"subnet_ids": [...], "scan_method": "icmp", "ports": [...]}
# 之所以复用 instances 字段（JSONField），是因为：
#   - 它已存在、无需迁移
#   - 对于 ip+subnet 任务而言，instances 本身没有其他含义
# task_type 仍写 "ip"（CollectPluginTypes.IP）；input_method 写 CollectInputMethod.SUBNET(2)


def extract_subnet_discovery_params(task) -> tuple:
    """从采集任务 model 实例或 dict 中提取 (subnet_ids, scan_method, ports)。

    存储约定（见 instances 字段注释）：
        instances = {"subnet_ids": [1, 2, ...], "scan_method": "icmp", "ports": [22, 80, ...]}

    返回 (subnet_ids: list, scan_method: str, ports: list | None)。
    subnet_ids 缺失时返回空列表；scan_method 缺失时默认 "icmp"；ports 缺失时返回 None（由
    build_scan_payload 填充 DEFAULT_PORTS）。
    """
    if hasattr(task, "instances"):
        raw_instances = task.instances
    else:
        raw_instances = task.get("instances", {})

    if not isinstance(raw_instances, dict):
        raw_instances = {}

    subnet_ids = raw_instances.get("subnet_ids", [])
    if not isinstance(subnet_ids, list):
        subnet_ids = list(subnet_ids) if subnet_ids else []

    scan_method = raw_instances.get("scan_method", "icmp") or "icmp"
    ports = raw_instances.get("ports", None)
    if ports is not None and not isinstance(ports, list):
        ports = list(ports)

    return subnet_ids, scan_method, ports


def maybe_dispatch_ip_discovery(task) -> bool:
    """检测采集任务是否为「选子网 IP 发现」任务，是则下发扫描并返回 True，否则返回 False。

    「选子网 IP 发现」任务的判定条件：
        task_type == "ip"  AND  input_method == CollectInputMethod.SUBNET (2)

    扫描结果由 Stargazer 异步回推到 NATS subject "receive_ip_discovery_result"，
    由 apps.cmdb.nats.nats.receive_ip_discovery_result 落库（fire-and-forget）。

    返回 True 时调用方（sync_collect_task）应跳过常规 ProtocolCollect/JobCollect 路径。

    TODO(2.7): 若未来支持多接入点（access_point），需从 task.access_point 推导
    Stargazer instance_id，而非固定使用默认 "stargazer"。
    """
    from apps.cmdb.constants.constants import CollectPluginTypes, CollectInputMethod
    from apps.rpc.stargazer import Stargazer

    if hasattr(task, "task_type"):
        task_type = task.task_type
        input_method = task.input_method
    else:
        task_type = task.get("task_type", "")
        input_method = task.get("input_method", CollectInputMethod.AUTO)

    if task_type != CollectPluginTypes.IP:
        return False
    if int(input_method) != CollectInputMethod.SUBNET:
        return False

    subnet_ids, scan_method, ports = extract_subnet_discovery_params(task)
    if not subnet_ids:
        return False

    # TODO(2.7): 从 task.access_point 推导 instance_id 支持多接入点
    stargazer = Stargazer()
    stargazer.dispatch_ip_discovery(subnet_ids=subnet_ids, scan_method=scan_method, ports=ports)
    return True


def _derive_targets(address: str, mask: str, gateway: str = "") -> list:
    try:
        net = ipaddress.ip_network(f"{str(address).strip()}/{str(mask).strip()}", strict=False)
    except (ValueError, TypeError):
        return []
    hosts = [str(ip) for ip in net.hosts()]
    gw = str(gateway or "").strip()
    if gw in hosts:
        hosts.remove(gw)
    return hosts


def _load_subnets_by_ids(subnet_ids: list) -> list:
    ids = [int(i) for i in subnet_ids]
    with GraphClient() as ag:
        rows, _ = ag.query_entity(INSTANCE, [
            {"field": "model_id", "type": "str=", "value": "subnet"},
            {"field": "id", "type": "id[]", "value": ids}])
    return rows or []


def build_scan_payload(subnet_id, scan_method: str = "icmp", ports=None) -> dict:
    """为单个子网构造扫描 payload。

    每个子网独立下发，payload 携带 subnet_id，Stargazer 回调时原样回传，
    以便 receive_ip_discovery_result 能路由到正确的子网台账。
    """
    rows = _load_subnets_by_ids([subnet_id])
    targets = []
    for sn in rows:
        targets.extend(_derive_targets(sn.get("subnet_address"), sn.get("subnet_mask"), sn.get("gateway")))
    return {
        "model_id": "ip",
        "subnet_id": subnet_id,
        "scan_method": (scan_method or "icmp").lower(),
        "ports": list(ports) if ports else DEFAULT_PORTS,
        "targets": targets,
        "callback_subject": "receive_ip_discovery_result",
    }


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
    """
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
