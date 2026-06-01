"""
Webhook URL Validation Security Tests

Tests for is_valid_webhook_url() function that validates webhook URLs
against a domain whitelist to prevent SSRF attacks.

Security Requirements:
1. Only allow official webhook domains (企业微信, 飞书, 钉钉)
2. Block all other domains including internal/private IPs
3. Prevent URL parsing bypass attacks (backslash, userinfo, encoding)
"""

from apps.system_mgmt.utils.channel_utils import WEBHOOK_ALLOWED_DOMAINS, is_valid_webhook_url


class TestWebhookAllowedDomains:
    """Test that the whitelist contains expected official domains"""

    def test_wechat_domain_in_whitelist(self):
        """企业微信域名在白名单中"""
        assert "qyapi.weixin.qq.com" in WEBHOOK_ALLOWED_DOMAINS

    def test_feishu_domain_in_whitelist(self):
        """飞书域名在白名单中"""
        assert "open.feishu.cn" in WEBHOOK_ALLOWED_DOMAINS

    def test_lark_domain_in_whitelist(self):
        """Lark (国际版飞书) 域名在白名单中"""
        assert "open.larksuite.com" in WEBHOOK_ALLOWED_DOMAINS

    def test_dingtalk_domain_in_whitelist(self):
        """钉钉域名在白名单中"""
        assert "oapi.dingtalk.com" in WEBHOOK_ALLOWED_DOMAINS

    def test_whitelist_size(self):
        """白名单只包含预期的4个域名"""
        assert len(WEBHOOK_ALLOWED_DOMAINS) == 4


class TestWebhookValidURLs:
    """Test that valid webhook URLs are accepted"""

    def test_wechat_webhook_https(self):
        """企业微信 HTTPS webhook URL 有效"""
        url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
        assert is_valid_webhook_url(url) is True

    def test_wechat_webhook_http(self):
        """企业微信 HTTP webhook URL 有效"""
        url = "http://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
        assert is_valid_webhook_url(url) is True

    def test_feishu_webhook(self):
        """飞书 webhook URL 有效"""
        url = "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
        assert is_valid_webhook_url(url) is True

    def test_lark_webhook(self):
        """Lark webhook URL 有效"""
        url = "https://open.larksuite.com/open-apis/bot/v2/hook/xxx"
        assert is_valid_webhook_url(url) is True

    def test_dingtalk_webhook(self):
        """钉钉 webhook URL 有效"""
        url = "https://oapi.dingtalk.com/robot/send?access_token=xxx"
        assert is_valid_webhook_url(url) is True

    def test_url_with_path_and_query(self):
        """带路径和查询参数的 URL 有效"""
        url = "https://qyapi.weixin.qq.com/path/to/api?key=value&foo=bar"
        assert is_valid_webhook_url(url) is True

    def test_url_with_port(self):
        """带端口的白名单域名 URL 有效"""
        url = "https://qyapi.weixin.qq.com:443/webhook"
        assert is_valid_webhook_url(url) is True


class TestWebhookBlockedDomains:
    """Test that non-whitelisted domains are blocked"""

    def test_blocks_arbitrary_domain(self):
        """阻止任意域名"""
        url = "https://evil.com/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_localhost(self):
        """阻止 localhost"""
        url = "http://localhost/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_127_0_0_1(self):
        """阻止 127.0.0.1"""
        url = "http://127.0.0.1/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_private_ip_10_x(self):
        """阻止 10.x.x.x 私有 IP"""
        url = "http://10.0.0.1/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_private_ip_172_16(self):
        """阻止 172.16.x.x 私有 IP"""
        url = "http://172.16.0.1/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_private_ip_192_168(self):
        """阻止 192.168.x.x 私有 IP"""
        url = "http://192.168.1.1/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_aws_metadata(self):
        """阻止 AWS 元数据服务"""
        url = "http://169.254.169.254/latest/meta-data/"
        assert is_valid_webhook_url(url) is False

    def test_blocks_gcp_metadata(self):
        """阻止 GCP 元数据服务"""
        url = "http://metadata.google.internal/computeMetadata/v1/"
        assert is_valid_webhook_url(url) is False

    def test_blocks_similar_domain(self):
        """阻止相似但不在白名单的域名"""
        url = "https://qyapi.weixin.qq.com.evil.com/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_subdomain_of_allowed(self):
        """阻止白名单域名的子域名"""
        url = "https://sub.qyapi.weixin.qq.com/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_parent_domain(self):
        """阻止白名单域名的父域名"""
        url = "https://weixin.qq.com/webhook"
        assert is_valid_webhook_url(url) is False


class TestWebhookBypassAttempts:
    """Test that URL parsing bypass attempts are blocked"""

    def test_blocks_backslash_bypass(self):
        """阻止反斜杠绕过攻击 (urlparse vs requests 解析不一致)"""
        # 攻击原理: urlparse 将 \\ 视为路径，requests 可能将其视为主机分隔符
        url = "https://qyapi.weixin.qq.com\\@evil.com/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_backslash_in_path(self):
        """阻止路径中的反斜杠"""
        url = "https://qyapi.weixin.qq.com/path\\to\\webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_userinfo_bypass(self):
        """阻止 userinfo (@) 绕过攻击"""
        # 攻击原理: user@host 形式可能被解析为不同的主机
        url = "https://qyapi.weixin.qq.com@evil.com/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_userinfo_with_password(self):
        """阻止带密码的 userinfo 绕过"""
        url = "https://user:pass@qyapi.weixin.qq.com/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_encoded_hostname_percent23(self):
        """阻止 %23 (#) 编码绕过"""
        # 攻击原理: %23 解码后为 #，可能截断 URL
        url = "https://qyapi.weixin.qq.com%23.evil.com/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_encoded_hostname_percent00(self):
        """阻止 %00 (null) 编码绕过"""
        # 攻击原理: null 字节可能导致字符串截断
        url = "https://qyapi.weixin.qq.com%00.evil.com/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_encoded_hostname_percent2f(self):
        """阻止 %2f (/) 编码绕过"""
        url = "https://evil.com%2fqyapi.weixin.qq.com/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_unicode_hostname(self):
        """阻止 Unicode 主机名"""
        # 攻击原理: Unicode 字符可能被规范化为不同的值
        url = "https://qyapi.weixin.qq.cοm/webhook"  # 注意: ο 是希腊字母
        assert is_valid_webhook_url(url) is False

    def test_blocks_ipv6_localhost(self):
        """阻止 IPv6 localhost"""
        url = "http://[::1]/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_ipv6_private(self):
        """阻止 IPv6 私有地址"""
        url = "http://[fd00::1]/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_decimal_ip(self):
        """阻止十进制 IP 表示"""
        # 2130706433 = 127.0.0.1
        url = "http://2130706433/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_octal_ip(self):
        """阻止八进制 IP 表示"""
        # 0177.0.0.1 = 127.0.0.1
        url = "http://0177.0.0.1/webhook"
        assert is_valid_webhook_url(url) is False

    def test_blocks_hex_ip(self):
        """阻止十六进制 IP 表示"""
        # 0x7f.0.0.1 = 127.0.0.1
        url = "http://0x7f.0.0.1/webhook"
        assert is_valid_webhook_url(url) is False


class TestWebhookInvalidInputs:
    """Test handling of invalid inputs"""

    def test_rejects_none(self):
        """拒绝 None 输入"""
        assert is_valid_webhook_url(None) is False

    def test_rejects_empty_string(self):
        """拒绝空字符串"""
        assert is_valid_webhook_url("") is False

    def test_rejects_whitespace(self):
        """拒绝空白字符串"""
        assert is_valid_webhook_url("   ") is False

    def test_rejects_invalid_scheme_ftp(self):
        """拒绝 FTP 协议"""
        url = "ftp://qyapi.weixin.qq.com/webhook"
        assert is_valid_webhook_url(url) is False

    def test_rejects_invalid_scheme_file(self):
        """拒绝 file:// 协议"""
        url = "file:///etc/passwd"
        assert is_valid_webhook_url(url) is False

    def test_rejects_invalid_scheme_javascript(self):
        """拒绝 javascript: 协议"""
        url = "javascript:alert(1)"
        assert is_valid_webhook_url(url) is False

    def test_rejects_invalid_scheme_data(self):
        """拒绝 data: 协议"""
        url = "data:text/html,<script>alert(1)</script>"
        assert is_valid_webhook_url(url) is False

    def test_rejects_no_scheme(self):
        """拒绝无协议的 URL"""
        url = "qyapi.weixin.qq.com/webhook"
        assert is_valid_webhook_url(url) is False

    def test_rejects_scheme_only(self):
        """拒绝只有协议的 URL"""
        url = "https://"
        assert is_valid_webhook_url(url) is False

    def test_rejects_malformed_url(self):
        """拒绝格式错误的 URL"""
        url = "https://[invalid"
        assert is_valid_webhook_url(url) is False


class TestWebhookCaseInsensitivity:
    """Test case handling"""

    def test_uppercase_domain_blocked(self):
        """大写域名被阻止 (白名单是小写)"""
        # 注意: 当前实现会将 hostname 转为小写后比较
        url = "https://QYAPI.WEIXIN.QQ.COM/webhook"
        assert is_valid_webhook_url(url) is True

    def test_mixed_case_domain(self):
        """混合大小写域名"""
        url = "https://QyApi.WeiXin.QQ.Com/webhook"
        assert is_valid_webhook_url(url) is True

    def test_uppercase_scheme_accepted(self):
        """大写协议被接受 (urlparse 会规范化为小写)"""
        url = "HTTPS://qyapi.weixin.qq.com/webhook"
        assert is_valid_webhook_url(url) is True


class TestWebhookEdgeCases:
    """Test edge cases"""

    def test_url_with_fragment(self):
        """带 fragment 的 URL"""
        url = "https://qyapi.weixin.qq.com/webhook#section"
        assert is_valid_webhook_url(url) is True

    def test_url_with_empty_path(self):
        """空路径的 URL"""
        url = "https://qyapi.weixin.qq.com"
        assert is_valid_webhook_url(url) is True

    def test_url_with_trailing_slash(self):
        """带尾部斜杠的 URL"""
        url = "https://qyapi.weixin.qq.com/"
        assert is_valid_webhook_url(url) is True

    def test_url_with_double_slash_in_path(self):
        """路径中有双斜杠"""
        url = "https://qyapi.weixin.qq.com//webhook"
        assert is_valid_webhook_url(url) is True

    def test_very_long_url(self):
        """非常长的 URL"""
        url = "https://qyapi.weixin.qq.com/" + "a" * 10000
        assert is_valid_webhook_url(url) is True

    def test_url_with_special_chars_in_query(self):
        """查询参数中有特殊字符"""
        url = 'https://qyapi.weixin.qq.com/webhook?key=value&special=<>&"'
        assert is_valid_webhook_url(url) is True
