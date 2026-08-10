"""
SSRF URL 安全校验器

基于 OWASP SSRF Prevention Cheat Sheet 和 Drawbridge 库最佳实践：
- 完整 IP 黑名单（IPv4 + IPv6）
- DNS 解析后校验
- 重定向目标校验
- 云元数据地址特别处理

防护能力：
1. 协议限制（仅 http/https）
2. 私网/特殊地址阻断（CIDR 例外 + 域名白名单内网例外）
3. DNS rebinding 防护（每次校验重新解析，任一 IP 不合格即拒）
4. 云元数据地址硬挡（白名单不可覆盖）
5. 纯 IP 字面量必须命中 CIDR 白名单
"""

import ipaddress
import socket
from typing import Optional
from urllib.parse import unquote, urlparse

from apps.core.logger import logger


class SSRFError(ValueError):
    """SSRF 校验失败异常"""

    def __init__(self, message: str, code: str = "CONNECTION_TARGET_FORBIDDEN"):
        super().__init__(message)
        self.code = code


class SSRFValidator:
    """统一 SSRF URL 校验器"""

    ALLOWED_SCHEMES = frozenset({"http", "https"})

    # 完整 IP 黑名单（基于 OWASP + RFC）
    BLOCKED_NETWORKS = [
        # IPv4 特殊地址
        ipaddress.ip_network("0.0.0.0/8"),  # This network (RFC 1122)
        ipaddress.ip_network("10.0.0.0/8"),  # Private-Use (RFC 1918)
        ipaddress.ip_network("100.64.0.0/10"),  # Shared Address Space (RFC 6598)
        ipaddress.ip_network("127.0.0.0/8"),  # Loopback (RFC 1122)
        ipaddress.ip_network("169.254.0.0/16"),  # Link-Local + Cloud Metadata (RFC 3927)
        ipaddress.ip_network("172.16.0.0/12"),  # Private-Use (RFC 1918)
        ipaddress.ip_network("192.0.0.0/24"),  # IETF Protocol Assignments (RFC 6890)
        ipaddress.ip_network("192.0.2.0/24"),  # Documentation TEST-NET-1 (RFC 5737)
        ipaddress.ip_network("192.88.99.0/24"),  # 6to4 Relay Anycast (RFC 3068)
        ipaddress.ip_network("192.168.0.0/16"),  # Private-Use (RFC 1918)
        ipaddress.ip_network("192.175.48.0/24"),  # AS112-v4 (RFC 7535)
        ipaddress.ip_network("198.18.0.0/15"),  # Benchmarking (RFC 2544)
        ipaddress.ip_network("198.51.100.0/24"),  # Documentation TEST-NET-2 (RFC 5737)
        ipaddress.ip_network("203.0.113.0/24"),  # Documentation TEST-NET-3 (RFC 5737)
        ipaddress.ip_network("224.0.0.0/4"),  # Multicast (RFC 5771)
        ipaddress.ip_network("240.0.0.0/4"),  # Reserved (RFC 1112)
        ipaddress.ip_network("255.255.255.255/32"),  # Limited Broadcast (RFC 919)
        # IPv6 特殊地址
        ipaddress.ip_network("::1/128"),  # Loopback (RFC 4291)
        ipaddress.ip_network("::/128"),  # Unspecified (RFC 4291)
        ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped (RFC 4291)
        ipaddress.ip_network("64:ff9b::/96"),  # IPv4/IPv6 Translation (RFC 6052)
        ipaddress.ip_network("64:ff9b:1::/48"),  # IPv4/IPv6 Translation (RFC 8215)
        ipaddress.ip_network("100::/64"),  # Discard-Only (RFC 6666)
        ipaddress.ip_network("2001::/32"),  # Teredo (RFC 4380)
        ipaddress.ip_network("2001:10::/28"),  # ORCHID (RFC 4843)
        ipaddress.ip_network("2001:20::/28"),  # ORCHIDv2 (RFC 7343)
        ipaddress.ip_network("2001:db8::/32"),  # Documentation (RFC 3849)
        ipaddress.ip_network("2002::/16"),  # 6to4 (RFC 3056)
        ipaddress.ip_network("fc00::/7"),  # Unique-Local (RFC 4193)
        ipaddress.ip_network("fe80::/10"),  # Link-Local (RFC 4291)
        ipaddress.ip_network("ff00::/8"),  # Multicast (RFC 4291)
    ]

    # 云元数据地址（特别标注，高优先级阻断；含部分主机名）
    CLOUD_METADATA_HOSTS = frozenset(
        {
            "169.254.169.254",  # AWS/GCP/Azure/DigitalOcean/Oracle
            "169.254.170.2",  # AWS ECS Task Metadata
            "metadata.google.internal",  # GCP
            "metadata.goog",  # GCP alternative
            "fd00:ec2::254",  # AWS IPv6
        }
    )

    # 固定危险主机名（不解析即拒；云 metadata 主机名见 CLOUD_METADATA_HOSTS）
    DANGEROUS_HOSTNAMES = frozenset(
        {
            "localhost",
            "localhost.",
        }
    )

    # 云元数据 IP 网段（用于 DNS 解析后校验；白名单不可覆盖）
    CLOUD_METADATA_NETWORKS = [
        ipaddress.ip_network("169.254.169.254/32"),  # AWS/GCP/Azure 元数据
        ipaddress.ip_network("169.254.170.2/32"),  # AWS ECS Task Metadata
    ]

    # 回调宽松模式阻断列表（云元数据 + localhost）
    CALLBACK_BLOCKED_NETWORKS = [
        ipaddress.ip_network("169.254.169.254/32"),  # AWS/GCP/Azure 元数据
        ipaddress.ip_network("169.254.170.2/32"),  # AWS ECS Task Metadata
        ipaddress.ip_network("127.0.0.0/8"),  # Loopback IPv4
        ipaddress.ip_network("::1/128"),  # Loopback IPv6
    ]

    @classmethod
    def _get_allowed_networks(cls) -> list:
        """读取白名单 CIDR 并解析为 ip_network 列表（延迟导入 + fail-closed）。"""
        try:
            from apps.system_mgmt.utils.network_whitelist_cache import get_network_whitelist_cidrs

            networks = []
            for cidr in get_network_whitelist_cidrs():
                try:
                    networks.append(ipaddress.ip_network(cidr, strict=False))
                except ValueError:
                    continue
            return networks
        except Exception as e:
            logger.warning("[SSRF] 白名单 CIDR 读取失败，回退严格模式: %s", e)
            return []

    @classmethod
    def _get_allowed_domains(cls) -> set[str]:
        """读取域名白名单（小写全等或 ``*.suffix`` 通配例外集）。fail-closed。"""
        try:
            from apps.system_mgmt.utils.network_whitelist_cache import get_network_whitelist_domains

            return {d.strip().lower() for d in get_network_whitelist_domains() if d and str(d).strip()}
        except Exception as e:
            logger.warning("[SSRF] 白名单域名读取失败，回退空集: %s", e)
            return set()

    @classmethod
    def _parse_ip_literal(cls, hostname: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        """若 hostname 为 IP 字面量（含十进制整型变形）则返回 IP，否则 None。"""
        raw = (hostname or "").strip().lower()
        if not raw:
            return None
        if raw.startswith("[") and raw.endswith("]"):
            raw = raw[1:-1]
        try:
            return ipaddress.ip_address(raw)
        except ValueError:
            pass
        if raw.isdigit():
            try:
                return ipaddress.IPv4Address(int(raw))
            except (ValueError, OverflowError):
                return None
        return None

    @classmethod
    def _is_hard_blocked_ip(cls, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> tuple[bool, str]:
        """云元数据硬挡（白名单不可覆盖）。"""
        ip_str = str(ip)
        if ip_str in cls.CLOUD_METADATA_HOSTS:
            return True, f"云元数据地址 {ip_str}"
        for network in cls.CLOUD_METADATA_NETWORKS:
            try:
                if ip in network:
                    return True, f"云元数据地址 {ip_str}"
            except TypeError:
                continue
        return False, ""

    @classmethod
    def _ip_in_networks(cls, ip: ipaddress.IPv4Address | ipaddress.IPv6Address, networks: list) -> bool:
        for network in networks:
            try:
                if ip in network:
                    return True
            except TypeError:
                continue
        return False

    @classmethod
    def _is_in_blocked_networks(cls, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> tuple[bool, str]:
        for network in cls.BLOCKED_NETWORKS:
            try:
                if ip in network:
                    return True, f"禁止的网段 {network}"
            except TypeError:
                continue
        return False, ""

    @classmethod
    def _assert_literal_ip_allowed(
        cls,
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
        allowed_networks: list,
        url: str,
    ) -> None:
        """纯 IP：必须命中 CIDR；硬黑名单不可覆盖。"""
        hard, reason = cls._is_hard_blocked_ip(ip)
        if hard:
            logger.warning("[SSRF] 阻断纯 IP 云元数据: url=%s, ip=%s", url, ip)
            raise SSRFError(f"禁止访问云元数据地址: {reason}", code="CONNECTION_TARGET_FORBIDDEN")

        if not cls._ip_in_networks(ip, allowed_networks):
            logger.warning("[SSRF] 纯 IP 未命中白名单: url=%s, ip=%s", url, ip)
            raise SSRFError(
                f"目标 IP 不在白名单: {ip}",
                code="NETWORK_WHITELIST_REQUIRED",
            )

    @classmethod
    def hostname_matches_domain_patterns(cls, hostname: str, patterns: set[str] | list[str]) -> bool:
        """域名白名单匹配：全等，或 ``*.example.com``（后缀匹配，含多级子域）。

        ``*.example.com`` 命中 ``a.example.com`` / ``a.b.example.com``，不命中 apex ``example.com``。
        """
        host = (hostname or "").strip().lower()
        if not host:
            return False
        for pattern in patterns:
            p = (pattern or "").strip().lower()
            if not p:
                continue
            if p.startswith("*."):
                suffix = p[1:]  # ".example.com"
                if host.endswith(suffix) and len(host) > len(suffix):
                    return True
            elif host == p:
                return True
        return False

    @classmethod
    def _assert_resolved_ip_allowed(
        cls,
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
        hostname: str,
        allowed_networks: list,
        allowed_domains: set[str],
        url: str,
    ) -> None:
        """域名解析 IP：硬挡 → 黑名单网段需域名例外或 CIDR → 公网放行。"""
        hard, reason = cls._is_hard_blocked_ip(ip)
        if hard:
            logger.warning("[SSRF] 阻断请求: url=%s, ip=%s, reason=%s", url, ip, reason)
            raise SSRFError(f"目标地址被禁止: {reason}", code="CONNECTION_TARGET_FORBIDDEN")

        blocked, reason = cls._is_in_blocked_networks(ip)
        if not blocked:
            return

        if cls.hostname_matches_domain_patterns(hostname, allowed_domains):
            return
        if cls._ip_in_networks(ip, allowed_networks):
            return

        logger.warning(
            "[SSRF] 阻断请求: url=%s, hostname=%s, ip=%s, reason=%s",
            url,
            hostname,
            ip,
            reason,
        )
        raise SSRFError(f"目标地址被禁止: {reason}", code="NETWORK_WHITELIST_REQUIRED")

    @classmethod
    def validate(
        cls,
        url: str,
        allowlist: Optional[set[str]] = None,
    ) -> str:
        """
        校验 URL 是否安全

        Args:
            url: 待校验的 URL
            allowlist: 可选的额外域名限制（若提供，主机名必须在此集合内）。
                与系统 NetworkWhiteList 域名例外表无关。

        Returns:
            规范化后的 URL

        Raises:
            SSRFError: URL 不安全
        """
        if not url or not url.strip():
            raise SSRFError("URL 不能为空")

        url = url.strip()
        if "\\" in url:
            logger.warning("[SSRF] 阻断含反斜杠 URL: url=%s", url)
            raise SSRFError("URL 格式非法")

        parsed = urlparse(url)

        # 1. 协议校验
        scheme = parsed.scheme.lower()
        if scheme not in cls.ALLOWED_SCHEMES:
            logger.warning(f"[SSRF] 阻断非法协议: url={url}, scheme={scheme}")
            raise SSRFError(f"不允许的协议: {scheme}，仅支持 http/https")

        # 2. 主机校验
        if not parsed.netloc or not parsed.hostname:
            raise SSRFError("URL 必须包含有效主机名")

        if "@" in (parsed.netloc or ""):
            logger.warning("[SSRF] 阻断含 userinfo URL: url=%s", url)
            raise SSRFError("URL 不允许包含用户信息")

        hostname = parsed.hostname.lower()
        decoded = unquote(hostname).lower()
        if decoded != hostname:
            raise SSRFError("主机名包含非法编码")

        # 3. 固定危险 / 云元数据主机名
        if hostname in cls.CLOUD_METADATA_HOSTS:
            logger.warning(f"[SSRF] 阻断云元数据主机: url={url}")
            raise SSRFError(f"禁止访问云元数据地址: {hostname}", code="CONNECTION_TARGET_FORBIDDEN")
        if hostname in cls.DANGEROUS_HOSTNAMES:
            logger.warning(f"[SSRF] 阻断危险主机: url={url}")
            raise SSRFError(f"禁止访问危险主机名: {hostname}", code="CONNECTION_TARGET_FORBIDDEN")

        # 4. 调用方额外域名限制（旧 allowlist 参数语义）
        if allowlist is not None and hostname not in {h.lower() for h in allowlist}:
            logger.warning(f"[SSRF] 主机不在允许列表: url={url}, allowlist={allowlist}")
            raise SSRFError(f"主机 {hostname} 不在允许列表中")

        allowed_networks = cls._get_allowed_networks()
        allowed_domains = cls._get_allowed_domains()

        # 5. 纯 IP 字面量：必须命中 CIDR（硬黑名单除外）
        literal_ip = cls._parse_ip_literal(hostname)
        if literal_ip is not None:
            cls._assert_literal_ip_allowed(literal_ip, allowed_networks, url)
            return url

        # 6. 域名：DNS 解析后按 IP 判定
        try:
            addr_infos = socket.getaddrinfo(hostname, parsed.port or (443 if scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        except socket.gaierror as e:
            raise SSRFError(f"无法解析主机名 {hostname}: {e}")

        if not addr_infos:
            raise SSRFError(f"主机名 {hostname} 无法解析")

        resolved_ips: list[str] = []
        checked = 0
        for info in addr_infos:
            ip_str = info[4][0]
            resolved_ips.append(ip_str)
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            checked += 1
            cls._assert_resolved_ip_allowed(ip, hostname, allowed_networks, allowed_domains, url)

        if checked == 0:
            raise SSRFError(f"主机名 {hostname} 未返回可解析 IP")

        logger.debug("[SSRF] 放行: url=%s, hostname=%s, resolved_ips=%s", url, hostname, resolved_ips)
        return url

    # LLM 端点宽松模式阻断列表（仅云元数据）
    LLM_ENDPOINT_BLOCKED_NETWORKS = [
        ipaddress.ip_network("169.254.169.254/32"),  # AWS/GCP/Azure 元数据
        ipaddress.ip_network("169.254.170.2/32"),  # AWS ECS Task Metadata
    ]

    @classmethod
    def validate_llm_endpoint(cls, url: str) -> str:
        """
        校验 LLM API 端点 URL（宽松模式，仅阻断云元数据）

        适用于 LLM api_base 配置场景，允许内网和 localhost 地址。
        这是因为企业常在内网部署 vLLM/Ollama/LocalAI 等本地 LLM 服务。

        阻断：云元数据地址（169.254.169.254、169.254.170.2）
        允许：私网地址（10.x, 172.16.x, 192.168.x）、localhost（127.x）

        Args:
            url: LLM API 端点 URL

        Returns:
            校验通过的 URL

        Raises:
            SSRFError: URL 指向云元数据地址
        """
        if not url or not url.strip():
            raise SSRFError("URL 不能为空")

        url = url.strip()
        parsed = urlparse(url)

        # 1. 协议校验
        scheme = parsed.scheme.lower()
        if scheme not in cls.ALLOWED_SCHEMES:
            logger.warning(f"[SSRF-llm] 阻断非法协议: url={url}, scheme={scheme}")
            raise SSRFError(f"不允许的协议: {scheme}，仅支持 http/https")

        # 2. 主机校验
        if not parsed.netloc or not parsed.hostname:
            raise SSRFError("URL 必须包含有效主机名")

        hostname = parsed.hostname.lower()

        # 3. 云元数据主机名直接阻断
        if hostname in cls.CLOUD_METADATA_HOSTS:
            logger.warning(f"[SSRF-llm] 阻断云元数据主机: url={url}")
            raise SSRFError(f"禁止访问云元数据地址: {hostname}")

        # 4. DNS 解析并校验云元数据 IP
        try:
            addr_infos = socket.getaddrinfo(hostname, parsed.port or (443 if scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        except socket.gaierror as e:
            raise SSRFError(f"无法解析主机名 {hostname}: {e}")

        if not addr_infos:
            raise SSRFError(f"主机名 {hostname} 无法解析")

        # 仅检查云元数据地址
        for info in addr_infos:
            ip_str = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            for network in cls.LLM_ENDPOINT_BLOCKED_NETWORKS:
                try:
                    if ip in network:
                        logger.warning(f"[SSRF-llm] 阻断云元数据 IP: url={url}, ip={ip_str}")
                        raise SSRFError(f"禁止访问云元数据地址: {ip_str}")
                except TypeError:
                    continue

        return url

    @classmethod
    def validate_callback(cls, callback_url: str | None) -> str | None:
        """
        校验回调 URL（宽松模式，阻断云元数据和 localhost）

        适用于内部系统间回调场景，允许内网地址访问。
        阻断：云元数据地址（169.254.169.254 等）、localhost（127.0.0.0/8）
        允许：其他私网地址（10.x, 172.16.x, 192.168.x）

        Args:
            callback_url: 回调 URL，可为 None

        Returns:
            校验通过的 URL 或 None

        Raises:
            SSRFError: URL 指向云元数据或 localhost
        """
        if not callback_url:
            return None

        url = callback_url.strip()
        if not url:
            return None

        parsed = urlparse(url)

        # 1. 协议校验
        scheme = parsed.scheme.lower()
        if scheme not in cls.ALLOWED_SCHEMES:
            logger.warning(f"[SSRF-callback] 阻断非法协议: url={url}, scheme={scheme}")
            raise SSRFError(f"不允许的协议: {scheme}，仅支持 http/https")

        # 2. 主机校验
        if not parsed.netloc or not parsed.hostname:
            raise SSRFError("URL 必须包含有效主机名")

        hostname = parsed.hostname.lower()

        # 3. 云元数据主机名直接阻断
        if hostname in cls.CLOUD_METADATA_HOSTS:
            logger.warning(f"[SSRF-callback] 阻断云元数据主机: url={url}")
            raise SSRFError(f"禁止访问云元数据地址: {hostname}")

        # 4. DNS 解析并校验阻断列表
        try:
            addr_infos = socket.getaddrinfo(hostname, parsed.port or (443 if scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        except socket.gaierror as e:
            raise SSRFError(f"无法解析主机名 {hostname}: {e}")

        if not addr_infos:
            raise SSRFError(f"主机名 {hostname} 无法解析")

        # 检查云元数据和 localhost
        for info in addr_infos:
            ip_str = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            for network in cls.CALLBACK_BLOCKED_NETWORKS:
                try:
                    if ip in network:
                        if network == ipaddress.ip_network("127.0.0.0/8") or network == ipaddress.ip_network("::1/128"):
                            logger.warning(f"[SSRF-callback] 阻断 localhost: url={url}, ip={ip_str}")
                            raise SSRFError(f"禁止访问 localhost: {ip_str}")
                        else:
                            logger.warning(f"[SSRF-callback] 阻断云元数据 IP: url={url}, ip={ip_str}")
                            raise SSRFError(f"禁止访问云元数据地址: {ip_str}")
                except TypeError:
                    continue

        return url
