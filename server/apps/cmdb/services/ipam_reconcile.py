# -- coding: utf-8 --
"""IPAM 与 CMDB 自动对账。规格 §5。"""
from datetime import datetime
from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.utils.ipam_cidr import parse_subnet, ip_in_subnet
from apps.core.logger import cmdb_logger as logger


# ---------------------------------------------------------------------------
# 纯逻辑：无 DB/IO 依赖
# ---------------------------------------------------------------------------

def match_subnet_for_ip(ip: str, subnets: list):
    """返回唯一包含该 IP 的子网（子网两两不重叠，故至多一个）。无则 None。

    DEFECT D fix: malformed (non-empty but syntactically invalid) subnet records
    no longer abort the whole reconcile — they are silently skipped so that the
    remaining valid subnets are still checked.
    """
    from apps.core.exceptions.base_app_exception import BaseAppException
    for sn in subnets:
        addr, mask = sn.get("subnet_address"), sn.get("subnet_mask")
        if not addr or mask in (None, ""):
            continue
        try:
            if ip_in_subnet(ip, parse_subnet(addr, mask)):
                return sn
        except (BaseAppException, ValueError):
            continue
    return None


def decide_ip_status(occupant_keys: list) -> str:
    """按占用者数量定现网状态：>1 冲突，==1 在线，0 离线。"""
    n = len({str(k) for k in occupant_keys})
    if n > 1:
        return "conflict"
    if n == 1:
        return "online"
    return "offline"


# ---------------------------------------------------------------------------
# IO helpers（单测时被 monkeypatch 替换）
# ---------------------------------------------------------------------------

def _load_sources() -> list:
    from apps.cmdb.models.ipam_models import IPAMReconcileSource
    return list(IPAMReconcileSource.objects.filter(enabled=True).values("model_id", "ip_attr_id"))


def _load_subnets() -> list:
    with GraphClient() as ag:
        rows, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": "subnet"}])
    return rows or []


def _load_ci_with_ip(model_id: str, ip_attr_id: str) -> list:
    with GraphClient() as ag:
        rows, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])
    out = []
    for r in rows or []:
        ip = r.get(ip_attr_id)
        if ip:
            out.append({"_id": r["_id"], "model_id": model_id, "ip_addr": ip, "inst_name": r.get("inst_name")})
    return out


def _load_existing_ips() -> list:
    with GraphClient() as ag:
        rows, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": "ip"}])
    return rows or []


def _upsert_ip_instance(existing_id=None, subnet_id=None, ip_addr=None, ip_status=None,
                        auto_collect=True, occupants=None, organization=None) -> dict:
    from apps.cmdb.services.instance import InstanceManage
    payload = {
        "ip_addr": ip_addr,
        "inst_name": ip_addr,
        # 以字符串存储 subnet_id：视图/利用率回写均以 str= 查询该属性，存 int 会查不到
        "subnet_id": str(subnet_id),
        "ip_status": [ip_status],
        "auto_collect": auto_collect,
        "organization": organization or [],
        "collect_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if existing_id:
        InstanceManage.instance_update(
            [], [], existing_id, payload, "system",
            skip_permission_check=True, record_change=False,
        )
        ip_id = existing_id
    else:
        res = InstanceManage.instance_create("ip", payload, "system", record_change=False)
        ip_id = res["_id"]
    _ensure_associations(ip_id, subnet_id, occupants or [])
    return {"_id": ip_id}


def _ensure_associations(ip_id, subnet_id, occupants):
    """为 ip 实例创建关联：subnet --组成(group)--> ip，ip --关联(connect)--> CI。
    方向必须与已注册模型关联一致：组成关联是 subnet→ip（model_asst_id=subnet_group_ip），
    方向写反会被图层判为「association not found」。group/connect 均为已注册内置类型。
    仅「重复关联」属于幂等可忽略；其它异常记录告警，避免静默丢失。
    """
    from apps.cmdb.services.instance import InstanceManage
    from apps.core.exceptions.base_app_exception import BaseAppException

    # (src_model, src_id, dst_model, dst_id, asst_id)
    pairs = [("subnet", subnet_id, "ip", ip_id, "group")]
    for occ in occupants:
        model_id, cid = occ.split(":", 1)
        pairs.append(("ip", ip_id, model_id, int(cid), "connect"))

    for src_model, src_id, dst_model, dst_id, asst_id in pairs:
        data = {
            "src_inst_id": src_id,
            "dst_inst_id": dst_id,
            "asst_id": asst_id,
            "src_model_id": src_model,
            "dst_model_id": dst_model,
            "model_asst_id": f"{src_model}_{asst_id}_{dst_model}",
        }
        try:
            InstanceManage.instance_association_create(data, "system")
        except BaseAppException as e:
            message = getattr(e, "message", "") or str(e)
            if "repetition" not in message:
                logger.warning("[IPAM] 创建关联 %s 失败: %s", data["model_asst_id"], message)


def _mark_offline(ip_id):
    """把 ip 实例现网状态置为 offline（auto_collect 记录本轮无 CI 命中时）。"""
    from apps.cmdb.services.instance import InstanceManage
    InstanceManage.instance_update(
        [], [], ip_id, {"ip_status": ["offline"]}, "system",
        skip_permission_check=True, record_change=False,
    )


def _writeback_subnet_utilization(subnet_ids):
    from apps.cmdb.services.instance import InstanceManage
    from apps.cmdb.utils.ipam_cidr import parse_subnet, subnet_capacity
    for sid in subnet_ids:
        subnet = InstanceManage.query_entity_by_id(int(sid))
        if not subnet:
            continue
        with GraphClient() as ag:
            ips, _ = ag.query_entity(INSTANCE, [
                {"field": "model_id", "type": "str=", "value": "ip"},
                {"field": "subnet_id", "type": "str=", "value": str(sid)},
            ])
        net = parse_subnet(subnet["subnet_address"], subnet["subnet_mask"])
        size = subnet_capacity(net)
        used = len(ips or [])
        InstanceManage.instance_update(
            [], [], int(sid),
            {"subnet_size": size, "subnet_used_size": used, "subnet_available_size": size - used},
            "system", skip_permission_check=True, record_change=False,
        )


# ---------------------------------------------------------------------------
# 编排入口
# ---------------------------------------------------------------------------

def run_reconciliation() -> dict:
    """执行一次完整对账，返回统计字典：created/updated/skipped_manual/conflicts。"""
    sources = _load_sources()
    subnets = _load_subnets()
    existing = _load_existing_ips()

    # key: (str(subnet_id), ip_addr)
    existing_map = {(str(i.get("subnet_id")), i.get("ip_addr")): i for i in existing}

    # 归集每个 (subnet, ip) 的占用者列表
    occupants: dict = {}
    for src in sources:
        for ci in _load_ci_with_ip(src["model_id"], src["ip_attr_id"]):
            sn = match_subnet_for_ip(ci["ip_addr"], subnets)
            if not sn:
                continue
            key = (str(sn["_id"]), ci["ip_addr"])
            occupants.setdefault(key, {"subnet": sn, "ips": []})["ips"].append(
                f'{ci["model_id"]}:{ci["_id"]}'
            )

    created = updated = skipped_manual = conflicts = 0
    affected_subnets: set = set()

    for (subnet_id, ip_addr), info in occupants.items():
        prev = existing_map.get((subnet_id, ip_addr))
        # DEFECT C fix: always record the subnet as affected so utilization is
        # recomputed even when the only matched IP is a manual-protected record.
        affected_subnets.add(int(subnet_id))
        # 手工保护：只有对账自己创建的记录(auto_collect is True)才可写；
        # 其余(False/None/缺失，含手工经通用表单创建的)一律视为非自动记录，跳过不覆盖。
        if prev and prev.get("auto_collect") is not True:
            skipped_manual += 1
            continue
        status = decide_ip_status(info["ips"])
        if status == "conflict":
            conflicts += 1
        _upsert_ip_instance(
            existing_id=(prev or {}).get("_id"),
            subnet_id=int(subnet_id),
            ip_addr=ip_addr,
            ip_status=status,
            auto_collect=True,
            occupants=info["ips"],
            organization=info["subnet"].get("organization"),
        )
        if prev:
            updated += 1
        else:
            created += 1

    # 台账跟随 CI 变更（§2.4）：auto_collect=True 但本轮无任何 CI 命中的 IP 置离线。
    # 手工记录(auto_collect 非 True)一律不动。
    occupied_keys = set(occupants.keys())
    offline = 0
    for ip in existing:
        if ip.get("auto_collect") is not True:
            continue
        key = (str(ip.get("subnet_id")), ip.get("ip_addr"))
        if key in occupied_keys:
            continue
        _mark_offline(ip["_id"])
        offline += 1

    _writeback_subnet_utilization(affected_subnets)
    return {
        "created": created,
        "updated": updated,
        "skipped_manual": skipped_manual,
        "conflicts": conflicts,
        "offline": offline,
    }
