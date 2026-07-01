# -- coding: utf-8 --
"""IPAM 纯 CIDR/利用率工具：解析、重叠、容量、归属、利用率。无 DB/IO，可纯测。"""
import ipaddress
from apps.core.exceptions.base_app_exception import BaseAppException


def parse_subnet(address: str, mask: str) -> ipaddress.IPv4Network:
    """address+mask -> 归一化网段。mask 支持点分十进制(255.255.255.0)或前缀位数(24)。"""
    try:
        return ipaddress.ip_network(f"{str(address).strip()}/{str(mask).strip()}", strict=False)
    except (ValueError, TypeError) as e:
        raise BaseAppException(f"非法网段地址/掩码: {address}/{mask} ({e})")


def subnets_overlap(a: ipaddress.IPv4Network, b: ipaddress.IPv4Network) -> bool:
    """两网段地址范围是否有任何交集（含相同/包含/部分交叉）。"""
    return a.overlaps(b)


def subnet_capacity(net: ipaddress.IPv4Network, exclude_edges: bool = True) -> int:
    """网段可用地址数。默认扣除网络号+广播；扣后 <=0（如 /31、/32）则回退 num_addresses。"""
    total = net.num_addresses
    if exclude_edges and total > 2:
        return total - 2
    return total


def ip_in_subnet(ip: str, net: ipaddress.IPv4Network) -> bool:
    try:
        return ipaddress.ip_address(str(ip).strip()) in net
    except (ValueError, TypeError):
        return False


def compute_utilization(size: int, used: int) -> dict:
    """利用率口径：available=size-used，ratio=used/size（size<=0 时 ratio=0）。"""
    size = int(size or 0)
    used = int(used or 0)
    available = size - used
    ratio = round(used / size, 4) if size > 0 else 0
    return {"size": size, "used": used, "available": available, "ratio": ratio}
