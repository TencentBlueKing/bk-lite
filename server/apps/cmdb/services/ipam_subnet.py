# -- coding: utf-8 --
"""子网录入重叠校验（subnet 专属，非通用校验框架）。规格 §3。"""
from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.utils.ipam_cidr import parse_subnet, subnets_overlap
from apps.core.exceptions.base_app_exception import BaseAppException

SUBNET_MODEL_ID = "subnet"


def _query_subnet_instances() -> list:
    with GraphClient() as ag:
        rows, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": SUBNET_MODEL_ID}])
    return rows or []


def validate_subnet_no_overlap(instance_info: dict, exclude_inst_id=None) -> None:
    """新/改子网与已有子网地址范围重叠则抛 BaseAppException。地址或掩码缺失时跳过。"""
    address = instance_info.get("subnet_address")
    mask = instance_info.get("subnet_mask")
    if not address or mask in (None, ""):
        return
    new_net = parse_subnet(address, mask)
    for row in _query_subnet_instances():
        if exclude_inst_id is not None and str(row.get("_id")) == str(exclude_inst_id):
            continue
        r_addr, r_mask = row.get("subnet_address"), row.get("subnet_mask")
        if not r_addr or r_mask in (None, ""):
            continue
        if subnets_overlap(new_net, parse_subnet(r_addr, r_mask)):
            raise BaseAppException(
                f"网段 {address}/{mask} 与已有子网 {row.get('inst_name')} 地址范围重叠，不允许录入"
            )


def find_batch_subnet_overlap_index(instances: list[dict]) -> int | None:
    """返回首个与本批前序子网重叠的索引；无冲突时返回 None。"""
    parsed_subnets = []
    for index, instance in enumerate(instances):
        address = instance.get("subnet_address")
        mask = instance.get("subnet_mask")
        if not address or mask in (None, ""):
            continue
        current = parse_subnet(address, mask)
        if any(subnets_overlap(current, previous) for previous in parsed_subnets):
            return index
        parsed_subnets.append(current)
    return None
