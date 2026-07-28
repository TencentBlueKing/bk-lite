import ipaddress
import re


DOMAIN_PATTERN = re.compile(
    r"^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)
CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x20\x7f]")


def normalize_proxy_address(value: str, *, allow_blank: bool = False) -> str:
    """校验并规范化代理 IP/域名；IPv6 统一保存为 URL 安全的方括号形式。"""
    candidate = (value or "").strip()
    if not candidate:
        if allow_blank:
            return ""
        raise ValueError("请输入有效的 IP 或域名")
    if (
        "://" in candidate
        or CONTROL_CHARACTER_PATTERN.search(candidate)
        or candidate.startswith("[") != candidate.endswith("]")
    ):
        raise ValueError("请输入有效的 IP 或域名")

    address_candidate = candidate[1:-1] if candidate.startswith("[") else candidate
    try:
        address = ipaddress.ip_address(address_candidate)
    except ValueError:
        if not DOMAIN_PATTERN.fullmatch(candidate):
            raise ValueError("请输入有效的 IP 或域名")
        return candidate.lower()

    if address.version == 6:
        return f"[{address.compressed}]"
    return address.compressed
