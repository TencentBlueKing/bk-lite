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


def validate_subnet_no_overlap(instance_info: dict, exclude_inst_id=None, *, batch_state: dict | None = None) -> None:
    """新/改子网与已有子网地址范围重叠则抛 BaseAppException。地址或掩码缺失时跳过。

    batch_state 只在同一次批量创建内复用：第一次真正校验时查询已有子网，并记住已经成功解析的网段。
    不传 batch_state 时，单条创建和更新仍各自查询。这里不做跨请求缓存。
    """
    address = instance_info.get("subnet_address")
    mask = instance_info.get("subnet_mask")
    if not address or mask in (None, ""):
        return
    new_net = parse_subnet(address, mask)
    rows, parsed = _existing_subnet_rows(batch_state)
    for index, row in enumerate(rows):
        if exclude_inst_id is not None and str(row.get("_id")) == str(exclude_inst_id):
            continue
        r_addr, r_mask = row.get("subnet_address"), row.get("subnet_mask")
        if not r_addr or r_mask in (None, ""):
            continue
        existing_net = _parsed_existing_subnet(parsed, index, r_addr, r_mask)
        if subnets_overlap(new_net, existing_net):
            raise BaseAppException(
                f"网段 {address}/{mask} 与已有子网 {row.get('inst_name')} 地址范围重叠，不允许录入"
            )


def _existing_subnet_rows(batch_state: dict | None) -> tuple[list, dict | None]:
    if batch_state is None:
        return _query_subnet_instances(), None
    if "rows" not in batch_state:
        batch_state["rows"] = _query_subnet_instances()
        batch_state["parsed"] = {}
    return batch_state["rows"], batch_state["parsed"]


def _parsed_existing_subnet(parsed: dict | None, index: int, address, mask):
    if parsed is not None and index in parsed:
        return parsed[index]
    # 按原列表顺序解析。非法网段在走到该行时抛出，不提前解析后面的行。
    network = parse_subnet(address, mask)
    if parsed is not None:
        parsed[index] = network
    return network


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
