"""Elasticsearch URL 出站校验。

放行公网与 RFC1918/私网地址，硬拦截云元数据、回环、链路本地和其他危险目标。
不走 REST 的白名单放行，也不像 MySQL 那样跳过 HTTP 目标校验。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import unquote, urlparse

from apps.core.utils.ssrf_validator import SSRFValidator
from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.user_messages import oa_message

_RFC1918 = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_ULA = ipaddress.ip_network("fc00::/7")
# NAT64 把 IPv4 编进 IPv6。Python 3.12 把 64:ff9b::/96 标成 is_global。
# 与 SSRFValidator.BLOCKED_NETWORKS 里的翻译前缀对齐，整段拒绝。
_IPV4_TRANSLATION_NETWORKS = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
)
# CGNAT 里的云元数据。SSRFValidator 的 169.254.169.254 拦不住这段。
_EXTRA_METADATA_IPS = frozenset({ipaddress.ip_address("100.100.100.200")})
_EXTRA_METADATA_HOSTS = frozenset({"100.100.100.200", "metadata.aliyun.com"})


def _fail(message_key: str, default: str, *, code: str, **params) -> ConnectorError:
    return ConnectorError(oa_message(message_key, default, **params), code=code, status_code=400)


def _ip_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip in _EXTRA_METADATA_IPS:
        return False
    hard, _reason = SSRFValidator._is_hard_blocked_ip(ip)
    if hard:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _ip_allowed(ip.ipv4_mapped)
    if isinstance(ip, ipaddress.IPv6Address) and any(ip in network for network in _IPV4_TRANSLATION_NETWORKS):
        return False
    if any(ip in network for network in _RFC1918):
        return True
    if ip in _CGNAT or ip in _ULA:
        return True
    return bool(ip.is_global)


def _literal_ip(hostname: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    return SSRFValidator._parse_ip_literal(hostname)


def validate_elasticsearch_url(url: str, *, resolve_dns: bool = True) -> str:
    """校验单个 http/https URL。resolve_dns 为真时，域名的每个解析地址都必须可放行。"""
    if not isinstance(url, str) or not url.strip():
        raise _fail("messages.es_url_required", "Elasticsearch URL 不能为空", code="elasticsearch_url_invalid")

    raw = url.strip()
    if "\\" in raw or "," in raw:
        raise _fail("messages.es_url_invalid", "Elasticsearch URL 无效", code="elasticsearch_url_invalid")

    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise _fail("messages.es_url_scheme", "Elasticsearch URL 必须是 http 或 https", code="elasticsearch_url_invalid")
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise _fail("messages.es_url_userinfo", "Elasticsearch URL 不能包含用户名或密码", code="elasticsearch_url_invalid")
    if parsed.query or parsed.fragment:
        raise _fail("messages.es_url_invalid", "Elasticsearch URL 无效", code="elasticsearch_url_invalid")
    if not parsed.hostname:
        raise _fail("messages.es_url_invalid", "Elasticsearch URL 无效", code="elasticsearch_url_invalid")

    hostname = parsed.hostname.lower()
    if unquote(hostname) != hostname:
        raise _fail("messages.es_url_invalid", "Elasticsearch URL 无效", code="elasticsearch_url_invalid")
    if hostname in SSRFValidator.CLOUD_METADATA_HOSTS or hostname in SSRFValidator.DANGEROUS_HOSTNAMES or hostname in _EXTRA_METADATA_HOSTS:
        raise _fail("messages.es_url_forbidden", "Elasticsearch 地址被禁止", code="elasticsearch_target_forbidden")

    path = parsed.path or ""
    if path not in {"", "/"} and (".." in path or path.startswith("//")):
        raise _fail("messages.es_url_invalid", "Elasticsearch URL 无效", code="elasticsearch_url_invalid")

    literal = _literal_ip(hostname)
    if literal is not None:
        if not _ip_allowed(literal):
            raise _fail("messages.es_url_forbidden", "Elasticsearch 地址被禁止", code="elasticsearch_target_forbidden")
        return raw

    if not resolve_dns:
        return raw

    port = parsed.port or (443 if scheme == "https" else 80)
    try:
        addr_infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise _fail(
            "messages.es_url_unresolved",
            "Elasticsearch 主机名无法解析",
            code="elasticsearch_url_unresolved",
        ) from exc
    if not addr_infos:
        raise _fail("messages.es_url_unresolved", "Elasticsearch 主机名无法解析", code="elasticsearch_url_unresolved")

    checked = 0
    for info in addr_infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        checked += 1
        if not _ip_allowed(ip):
            raise _fail("messages.es_url_forbidden", "Elasticsearch 地址被禁止", code="elasticsearch_target_forbidden")
    if checked == 0:
        raise _fail("messages.es_url_unresolved", "Elasticsearch 主机名无法解析", code="elasticsearch_url_unresolved")
    return raw


def pinned_connect_target(url: str) -> tuple[str, int, bool, str | None]:
    """返回 (连接主机, 端口, use_ssl, TLS 主机名)。

    字面量 IP 直接连接。域名在连接前再次解析，任一地址被禁止则拒绝，
    并用第一个解析结果建连，避免校验后被重新解析到元数据地址。
    """
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    use_ssl = parsed.scheme.lower() == "https"
    port = parsed.port or (443 if use_ssl else 80)
    if _literal_ip(hostname) is not None:
        return hostname, port, use_ssl, None

    try:
        addr_infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise _fail("messages.es_url_unresolved", "Elasticsearch 主机名无法解析", code="elasticsearch_url_unresolved") from exc
    pinned = ""
    for info in addr_infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if not _ip_allowed(ip):
            raise _fail("messages.es_url_forbidden", "Elasticsearch 地址被禁止", code="elasticsearch_target_forbidden")
        if not pinned:
            pinned = str(ip)
    if not pinned:
        raise _fail("messages.es_url_unresolved", "Elasticsearch 主机名无法解析", code="elasticsearch_url_unresolved")
    return pinned, port, use_ssl, hostname
