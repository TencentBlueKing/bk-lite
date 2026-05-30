"""统一 SSRF 防护工具。

历史上多处「服务端按用户可控 URL 发起请求」的场景（OpsPilot ChatFlow HTTP
Action / Fetch 工具、Job NATS 回调等）未对目标地址做校验，可被用于探测/访问
内网服务、云元数据接口（169.254.169.254）等，构成 SSRF（详见 2026-05 安全审计）。

本模块提供统一入口：

- :func:`validate_url`：校验单个 URL（仅允许 http/https，解析 DNS 后阻断
  loopback / link-local / 私网 / 保留 / 组播 / 未指定 等危险地址，含 IPv6 与
  IPv4-mapped IPv6）。
- :func:`safe_request`：在 :mod:`requests` 之上做「先校验、禁用自动跳转、逐跳
  重新校验」的安全请求，防止重定向绕过。

业务代码不应再直接对用户可控 URL 调用 ``requests.*`` / ``urlopen``。
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

DEFAULT_ALLOWED_SCHEMES = ("http", "https")


class SSRFValidationError(ValueError):
    """目标 URL 未通过 SSRF 安全校验。"""


def _ip_is_blocked(ip: ipaddress._BaseAddress) -> bool:
    """判断解析得到的 IP 是否属于应拦截的危险网段。"""
    # IPv4-mapped / 兼容 IPv6（如 ::ffff:127.0.0.1）需还原为 IPv4 再判断
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    # CGNAT 共享地址段 100.64.0.0/10（ipaddress 不归类为 private，但属内网范畴）
    if ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
        return True

    # IPv6 唯一本地地址 fc00::/7（部分版本 is_private 已覆盖，这里兜底）
    if ip.version == 6 and ip in ipaddress.ip_network("fc00::/7"):
        return True

    return False


def _resolve_host_ips(host: str) -> list[str]:
    """解析主机名为全部 IP（含 A/AAAA）。host 本身是 IP 字面量时直接返回。"""
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFValidationError(f"无法解析目标主机: {host}") from exc
    return list({info[4][0] for info in infos})


def validate_url(
    url: Optional[str],
    *,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    resolve: bool = True,
) -> str:
    """校验用户可控 URL，阻断指向内网/保留地址的 SSRF。

    Args:
        url: 待校验的目标 URL。
        allowed_schemes: 允许的协议（默认仅 http/https）。
        resolve: 是否做 DNS 解析并校验解析出的所有 IP（默认开启）。

    Returns:
        原样返回校验通过的 URL（便于链式使用）。

    Raises:
        SSRFValidationError: 协议不允许、缺少主机、解析失败或命中危险地址。
    """
    if not url or not isinstance(url, str):
        raise SSRFValidationError("目标 URL 不能为空")

    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in {s.lower() for s in allowed_schemes}:
        raise SSRFValidationError(f"不允许的 URL 协议: {scheme or '(空)'}，仅支持 {', '.join(allowed_schemes)}")

    host = parsed.hostname
    if not host:
        raise SSRFValidationError("目标 URL 缺少主机名")

    if resolve:
        for ip_str in _resolve_host_ips(host):
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                raise SSRFValidationError(f"目标主机解析出非法地址: {ip_str}")
            if _ip_is_blocked(ip):
                raise SSRFValidationError(f"目标地址指向受限网段（内网/回环/保留地址），已拒绝: {host} -> {ip}")

    return url


def safe_request(
    method: str,
    url: str,
    *,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    max_redirects: int = 3,
    **kwargs,
):
    """在 SSRF 校验保护下发起 HTTP 请求。

    - 请求前校验目标 URL；
    - 禁用 :mod:`requests` 的自动重定向，手动逐跳重新校验 ``Location``，
      防止「先返回合法地址再 302 到内网」的绕过；
    - 其余参数透传给 :func:`requests.request`。

    Raises:
        SSRFValidationError: 任一跳目标未通过校验，或超过最大重定向次数。
    """
    import requests

    kwargs.pop("allow_redirects", None)
    current = validate_url(url, allowed_schemes=allowed_schemes)

    for _ in range(max_redirects + 1):
        response = requests.request(method, current, allow_redirects=False, **kwargs)
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            if not location:
                return response
            current = validate_url(urljoin(current, location), allowed_schemes=allowed_schemes)
            continue
        return response

    raise SSRFValidationError("重定向次数过多，疑似 SSRF 跳转链，已拒绝")
