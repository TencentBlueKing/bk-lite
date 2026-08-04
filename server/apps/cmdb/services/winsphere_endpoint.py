"""WinSphere 管理端点规范化。"""

from ipaddress import ip_address
import re


_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_winsphere_management_address(value):
    host = str(value or "").strip().lower().rstrip(".")
    if not host:
        raise ValueError("WinSphere 管理地址不能为空")
    if any(character in host for character in (":", "/", "?", "#", "@")):
        raise ValueError("WinSphere 管理地址不能包含协议、端口或路径")
    if any(character.isspace() for character in host):
        raise ValueError("WinSphere 管理地址格式错误")

    try:
        parsed_ip = ip_address(host)
    except ValueError:
        if len(host) > 253 or any(
            not _DNS_LABEL.fullmatch(label)
            for label in host.split(".")
        ):
            raise ValueError("WinSphere 管理地址格式错误")
    else:
        if parsed_ip.version != 4:
            raise ValueError("WinSphere 管理地址暂不支持 IPv6")
        host = str(parsed_ip)
    return host
