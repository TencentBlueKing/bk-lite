"""模型关联的列表快捷筛选开关。

Excel 列 quick_filter 缺省为关。种子里第一批打开的是：
设备属于机柜、机柜属于机房、主机属于应用，以及云对象直接属于云平台。
中间对象（子网属于 VPC、虚拟机属于宿主机、集群属于资源池）保持关闭。
"""

from __future__ import annotations

QUICK_FILTER_FIELD = "quick_filter"

# 机柜 contains 的设备。物理服务器的模型 ID 沿用种子里的拼写。
RACK_DEVICE_MODELS = frozenset(
    {
        "switch",
        "router",
        "firewall",
        "loadbalance",
        "physcial_server",
    }
)

# 各云的根账号或平台。对象直接 belong/group 到这些模型才算「所属云平台」。
CLOUD_PLATFORM_MODELS = frozenset(
    {
        "aliyun_account",
        "qcloud",
        "hwcloud",
        "manageone_cloud",
        "aws",
        "openstack",
        "smartx",
        "fusioninsight",
        "fusioncompute",
        "inspurincloudrail",
        "sangforhci",
        "sangforscp",
        "nutanixhci",
        "h3c_cas",
        "winsphere",
        "vmware_vc",
        "azurelocal",
    }
)

_TRUTHY = {"1", "true", "yes", "y", "是"}
_FALSY = {"0", "false", "no", "n", "否"}


def parse_quick_filter_cell(value) -> bool:
    """单元格有这一列时的取值。空值和无法识别的内容都是关。"""
    if value is None or value == "":
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1, 0.0, 1.0):
        return bool(value)
    text = str(value).strip().lower()
    if text in _TRUTHY:
        return True
    return False


def quick_filter_from_row(row: dict) -> bool | None:
    """列不存在时返回 None，调用方不要覆盖已有关联。"""
    if QUICK_FILTER_FIELD not in row:
        return None
    return parse_quick_filter_cell(row.get(QUICK_FILTER_FIELD))


def stored_quick_filter(value) -> bool | None:
    """图上还没有这个属性时返回 None。"""
    if value is None or value == "":
        return None
    return parse_quick_filter_cell(value)


def quick_filter_ends(src_model_id: str, dst_model_id: str, mapping: str):
    """快捷筛选出现在「多」的一端，下拉选「一」的一端。

    n:n 和 1:1 出现在目标模型，下拉选源模型。返回 (出现下拉的模型, 下拉里的模型)。
    """
    src = str(src_model_id or "").strip()
    dst = str(dst_model_id or "").strip()
    kind = str(mapping or "").strip()
    if not src or not dst:
        return None
    if kind == "n:1":
        return src, dst
    if kind in {"1:n", "n:n", "1:1"}:
        return dst, src
    return None


def seed_quick_filter(src_model_id: str, asst_id: str, dst_model_id: str) -> bool:
    """Model Init 种子里这一行关联是否默认打开快捷筛选。"""
    src = str(src_model_id or "").strip()
    asst = str(asst_id or "").strip()
    dst = str(dst_model_id or "").strip()
    if src == "rack" and asst == "contains" and dst in RACK_DEVICE_MODELS:
        return True
    if src == "server_room" and asst == "run" and dst == "rack":
        return True
    if src == "application" and asst == "run" and dst == "host":
        return True
    if dst in CLOUD_PLATFORM_MODELS and asst in {"belong", "group"} and src and src != dst:
        return True
    return False
