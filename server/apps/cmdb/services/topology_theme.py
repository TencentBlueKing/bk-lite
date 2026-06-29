# -- coding: utf-8 --
"""CMDB 实例详情拓扑主题判定。

主题判定与「模型 -> 主题」映射集中在此，便于未来扩展其它模型的拓扑主题。
network 主题：模型拥有 interface --belong--> <model> 的模型关联即视为网络设备。
"""
from apps.cmdb.constants.constants import (
    TOPO_THEME_NETWORK,
    TOPO_THEME_IPAM,
    NETWORK_INTERFACE_MODEL,
    NETWORK_INTERFACE_BELONG_ASST,
)
from apps.cmdb.services.model import ModelManage


def is_network_device_model(model_id: str) -> bool:
    """模型是否为网络设备：是否存在 interface --belong--> model_id 的模型关联。"""
    if not model_id:
        return False
    associations = ModelManage.model_association_search(model_id) or []
    for assoc in associations:
        if (
            assoc.get("src_model_id") == NETWORK_INTERFACE_MODEL
            and assoc.get("dst_model_id") == model_id
            and assoc.get("asst_id") == NETWORK_INTERFACE_BELONG_ASST
        ):
            return True
    return False


def get_topo_themes(model_id: str) -> list:
    """返回模型可用的拓扑主题列表，空列表表示仅有通用 列表/拓扑。"""
    themes = []
    if is_network_device_model(model_id):
        themes.append(TOPO_THEME_NETWORK)
    if model_id == "subnet":
        themes.append(TOPO_THEME_IPAM)
    return themes
