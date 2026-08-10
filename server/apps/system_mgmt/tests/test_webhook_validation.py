"""
Webhook URL Validation — 对齐 SSRFValidator 统一语义

公网域名默认通；内网需 CIDR 或域名白名单例外；纯 IP 必须 CIDR；
云 metadata 硬挡。DNS 在测试中 mock。
"""

from unittest import mock

import pytest

from apps.core.utils.ssrf_validator import SSRFValidator
from apps.system_mgmt.models import NetworkWhiteList
from apps.system_mgmt.utils.channel_utils import is_valid_webhook_url, send_by_custom_webhook
from apps.system_mgmt.viewset.network_white_list_viewset import NetworkWhiteListViewSet

PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 443))]
PRIVATE_ADDRINFO = [(2, 1, 6, "", ("10.1.2.3", 443))]
MULTI_PRIVATE_ADDRINFO = [
    (2, 1, 6, "", ("10.1.2.3", 443)),
    (2, 1, 6, "", ("10.1.2.4", 443)),
]
METADATA_ADDRINFO = [(2, 1, 6, "", ("169.254.169.254", 80))]


@pytest.fixture(autouse=True)
def empty_whitelist_and_public_dns():
    """默认：空白名单 + 公网解析（公有云 IM 域名可通）。"""
    with (
        mock.patch("socket.getaddrinfo", return_value=PUBLIC_ADDRINFO),
        mock.patch.object(SSRFValidator, "_get_allowed_networks", return_value=[]),
        mock.patch.object(SSRFValidator, "_get_allowed_domains", return_value=set()),
    ):
        yield


class TestWebhookPublicDomains:
    def test_official_im_domains_allowed_without_whitelist(self):
        assert is_valid_webhook_url("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx") is True
        assert is_valid_webhook_url("https://open.feishu.cn/open-apis/bot/v2/hook/xxx") is True
        assert is_valid_webhook_url("https://open.larksuite.com/open-apis/bot/v2/hook/xxx") is True
        assert is_valid_webhook_url("https://oapi.dingtalk.com/robot/send?access_token=xxx") is True

    def test_arbitrary_public_domain_allowed(self):
        assert is_valid_webhook_url("https://hooks.example.com/webhook") is True


class TestWebhookPrivateDomainExceptions:
    def test_private_domain_blocked_without_exception(self):
        with mock.patch("socket.getaddrinfo", return_value=PRIVATE_ADDRINFO):
            assert is_valid_webhook_url("https://corp-wecom.example.com/hook") is False

    def test_private_domain_allowed_via_domain_whitelist(self):
        with (
            mock.patch("socket.getaddrinfo", return_value=MULTI_PRIVATE_ADDRINFO),
            mock.patch.object(SSRFValidator, "_get_allowed_domains", return_value={"corp-wecom.example.com"}),
        ):
            assert is_valid_webhook_url("https://corp-wecom.example.com/hook") is True

    def test_private_domain_allowed_via_cidr(self):
        import ipaddress

        with (
            mock.patch("socket.getaddrinfo", return_value=PRIVATE_ADDRINFO),
            mock.patch.object(
                SSRFValidator,
                "_get_allowed_networks",
                return_value=[ipaddress.ip_network("10.1.2.0/24")],
            ),
        ):
            assert is_valid_webhook_url("https://corp-wecom.example.com/hook") is True

    def test_exact_domain_does_not_match_subdomain(self):
        with (
            mock.patch("socket.getaddrinfo", return_value=PRIVATE_ADDRINFO),
            mock.patch.object(SSRFValidator, "_get_allowed_domains", return_value={"example.com"}),
        ):
            assert is_valid_webhook_url("https://api.example.com/hook") is False

    def test_wildcard_domain_matches_subdomains(self):
        with (
            mock.patch("socket.getaddrinfo", return_value=PRIVATE_ADDRINFO),
            mock.patch.object(SSRFValidator, "_get_allowed_domains", return_value={"*.example.com"}),
        ):
            assert is_valid_webhook_url("https://api.example.com/hook") is True
            assert is_valid_webhook_url("https://a.b.example.com/hook") is True

    def test_wildcard_domain_does_not_match_apex(self):
        with (
            mock.patch("socket.getaddrinfo", return_value=PRIVATE_ADDRINFO),
            mock.patch.object(SSRFValidator, "_get_allowed_domains", return_value={"*.example.com"}),
        ):
            assert is_valid_webhook_url("https://example.com/hook") is False


class TestWebhookLiteralIp:
    def test_public_literal_ip_requires_cidr(self):
        assert is_valid_webhook_url("https://93.184.216.34/hook") is False

    def test_public_literal_ip_with_cidr(self):
        import ipaddress

        with mock.patch.object(
            SSRFValidator,
            "_get_allowed_networks",
            return_value=[ipaddress.ip_network("93.184.216.34/32")],
        ):
            assert is_valid_webhook_url("https://93.184.216.34/hook") is True

    def test_private_literal_ip_requires_cidr(self):
        assert is_valid_webhook_url("https://10.1.2.3/hook") is False


class TestWebhookBypassAndInvalid:
    def test_backslash_rejected(self):
        assert is_valid_webhook_url("https://qyapi.weixin.qq.com\\@evil.com/hook") is False

    def test_userinfo_rejected(self):
        assert is_valid_webhook_url("https://user@qyapi.weixin.qq.com/hook") is False

    def test_non_http_rejected(self):
        assert is_valid_webhook_url("ftp://qyapi.weixin.qq.com/hook") is False
        assert is_valid_webhook_url("file:///etc/passwd") is False

    def test_empty_rejected(self):
        assert is_valid_webhook_url("") is False
        assert is_valid_webhook_url(None) is False

    def test_metadata_via_dns_blocked_even_with_domain_whitelist(self):
        with (
            mock.patch("socket.getaddrinfo", return_value=METADATA_ADDRINFO),
            mock.patch.object(SSRFValidator, "_get_allowed_domains", return_value={"evil.example.com"}),
        ):
            assert is_valid_webhook_url("http://evil.example.com/api") is False


class TestWebhookBuiltinRowProtection:
    @pytest.mark.django_db
    def test_builtin_rows_still_protected_if_present(self):
        """若仍存在 is_build_in 行，viewset 禁止改删（字段能力保留）。"""
        row = NetworkWhiteList.objects.create(
            domain_name="legacy-builtin.example.com",
            network="",
            is_build_in=True,
            enabled=True,
            created_by="test",
            updated_by="test",
        )
        viewset = NetworkWhiteListViewSet()
        request = mock.Mock()
        with mock.patch.object(viewset, "get_object", return_value=row):
            response = viewset.destroy(request)
        assert response.status_code == 403
        assert NetworkWhiteList.objects.filter(pk=row.pk).exists()


class TestCustomWebhookUsesValidator:
    def test_send_rejects_when_validator_false(self):
        channel = mock.Mock()
        channel.config = {"webhook_url": "https://hooks.example.com/x", "headers": "{}"}
        channel.decrypt_field = mock.Mock()
        with mock.patch(
            "apps.system_mgmt.utils.channel_utils.is_valid_webhook_url",
            return_value=False,
        ):
            result = send_by_custom_webhook(channel, "hi", [])
        assert result["result"] is False
        assert result["code"] == "NETWORK_WHITELIST_REQUIRED"
        assert result["data"]["network_whitelist_url"] == "/system-manager/settings/network-whitelist"
