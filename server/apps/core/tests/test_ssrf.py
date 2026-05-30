"""SSRF 防护回归测试。

覆盖 apps.core.utils.ssrf.validate_url 对内网/回环/云元数据/保留地址及
非 http(s) 协议的拦截，以及对正常公网地址的放行。

这些用例只依赖标准库与 ssrf 模块（不依赖 DB / Django ORM），
公网域名的 DNS 解析通过 mock 打桩，保证离线可跑。
"""

from unittest import mock

import pytest

from apps.core.utils.ssrf import SSRFValidationError, validate_url

# 直接以 IP 字面量给出的目标会走「字面量直判」分支，无需 DNS 解析
BLOCKED_LITERAL_URLS = [
    "http://169.254.169.254/latest/meta-data/",  # 云元数据接口
    "http://127.0.0.1/",  # 回环
    "http://10.0.0.1/",  # 私网 A
    "http://192.168.1.1/",  # 私网 C
    "http://172.16.0.1/",  # 私网 B
    "http://100.64.1.1/",  # CGNAT 共享地址段
    "http://0.0.0.0/",  # 未指定地址
    "http://[::1]/",  # IPv6 回环
    "http://[::ffff:127.0.0.1]/",  # IPv4-mapped IPv6 回环
]

# 非 http/https 协议应被直接拒绝
BLOCKED_SCHEME_URLS = [
    "file:///etc/passwd",
    "ftp://example.com/",
    "gopher://127.0.0.1:6379/_INFO",
]


@pytest.mark.parametrize("url", BLOCKED_LITERAL_URLS)
def test_validate_url_blocks_internal_ip_literals(url):
    """内网/回环/保留/云元数据等 IP 字面量必须被拦截。"""
    with pytest.raises(SSRFValidationError):
        validate_url(url)


@pytest.mark.parametrize("url", BLOCKED_SCHEME_URLS)
def test_validate_url_blocks_dangerous_schemes(url):
    """非 http/https 协议必须被拦截。"""
    with pytest.raises(SSRFValidationError):
        validate_url(url)


def test_validate_url_blocks_localhost_hostname():
    """localhost 经解析后指向回环地址，必须被拦截。"""
    with mock.patch(
        "apps.core.utils.ssrf.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("127.0.0.1", 0))],
    ):
        with pytest.raises(SSRFValidationError):
            validate_url("http://localhost/")


def test_validate_url_blocks_dns_rebinding_to_private():
    """域名解析到私网地址（DNS rebinding）必须被拦截。"""
    with mock.patch(
        "apps.core.utils.ssrf.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("10.1.2.3", 0))],
    ):
        with pytest.raises(SSRFValidationError):
            validate_url("http://evil.example.com/")


def test_validate_url_blocks_when_any_resolved_ip_is_private():
    """只要解析出的任一 IP 命中内网即拦截（多 A 记录绕过防护）。"""
    with mock.patch(
        "apps.core.utils.ssrf.socket.getaddrinfo",
        return_value=[
            (None, None, None, None, ("93.184.216.34", 0)),  # 公网
            (None, None, None, None, ("127.0.0.1", 0)),  # 回环
        ],
    ):
        with pytest.raises(SSRFValidationError):
            validate_url("http://mixed.example.com/")


def test_validate_url_empty_is_rejected():
    """空 URL 必须被拒绝。"""
    with pytest.raises(SSRFValidationError):
        validate_url("")
    with pytest.raises(SSRFValidationError):
        validate_url(None)


def test_validate_url_allows_public_https():
    """正常公网 https 地址应放行并原样返回。"""
    with mock.patch(
        "apps.core.utils.ssrf.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("93.184.216.34", 0))],
    ):
        assert validate_url("https://example.com") == "https://example.com"
        assert validate_url("http://example.com/path?x=1") == "http://example.com/path?x=1"


def test_validate_url_can_skip_resolution():
    """resolve=False 时只做协议/主机名校验，不做 DNS 解析。"""
    # 公网域名在不解析时也应通过（不触发网络）
    assert validate_url("https://example.com", resolve=False) == "https://example.com"
    # 但协议非法仍应拦截
    with pytest.raises(SSRFValidationError):
        validate_url("file:///etc/passwd", resolve=False)
