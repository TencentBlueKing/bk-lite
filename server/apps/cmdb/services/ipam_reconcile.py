# -- coding: utf-8 --
"""IPAM 与 CMDB 自动对账。规格 §5。"""
from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.utils.ipam_cidr import parse_subnet, ip_in_subnet


# ---------------------------------------------------------------------------
# 纯逻辑：无 DB/IO 依赖
# ---------------------------------------------------------------------------

def match_subnet_for_ip(ip: str, subnets: list):
    """返回唯一包含该 IP 的子网（子网两两不重叠，故至多一个）。无则 None。"""
    for sn in subnets:
        addr, mask = sn.get("subnet_address"), sn.get("subnet_mask")
        if not addr or mask in (None, ""):
            continue
        if ip_in_subnet(ip, parse_subnet(addr, mask)):
            return sn
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
        "subnet_id": subnet_id,
        "ip_status": [ip_status],
        "auto_collect": auto_collect,
        "organization": organization or [],
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
    """为 ip 实例创建关联：ip --组成(group)--> subnet，ip --关联(connect)--> CI。
    group/connect 均为已注册的内置关联类型（use 未注册会被静默拒绝）。
    已存在的关联（instance_association_repetition）静默跳过。
    """
    from apps.cmdb.services.instance import InstanceManage
    from apps.core.exceptions.base_app_exception import BaseAppException

    # (src_model, src_id, dst_model, dst_id, asst_id)
    pairs = [("ip", ip_id, "subnet", subnet_id, "group")]
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
        except BaseAppException:
            # 重复关联或约束冲突：幂等跳过
            pass


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
        # 手工保护：auto_collect=False 的记录只读，跳过
        if prev and prev.get("auto_collect") is False:
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
        affected_subnets.add(int(subnet_id))
        if prev:
            updated += 1
        else:
            created += 1

    _writeback_subnet_utilization(affected_subnets)
    return {
        "created": created,
        "updated": updated,
        "skipped_manual": skipped_manual,
        "conflicts": conflicts,
    }
