# -- coding: utf-8 --
"""子网 -> 待探测主机地址列表，排除网络号/广播/网关。纯逻辑。"""
import ipaddress


def derive_targets(address: str, mask: str, gateway: str = "") -> list:
    """
    Derive scan targets from a subnet.

    Args:
        address: Subnet network address (e.g. "10.0.1.0")
        mask: Prefix length as string (e.g. "24" for /24)
        gateway: Optional gateway IP to exclude

    Returns:
        List of host IP addresses (string), excluding network/broadcast/gateway.
        Returns empty list if address or mask are invalid.
    """
    try:
        net = ipaddress.ip_network(f"{str(address).strip()}/{str(mask).strip()}", strict=False)
    except (ValueError, TypeError):
        return []

    hosts = [str(ip) for ip in net.hosts()]  # hosts() already excludes network/broadcast

    gw = str(gateway).strip()
    if gw and gw in hosts:
        hosts.remove(gw)

    return hosts
