"""
SSRFValidator 三层防护策略测试

测试三种验证模式：
1. validate() - 严格模式：阻断云元数据 + 私有IP + localhost
2. validate_callback() - 回调模式：阻断云元数据 + localhost，允许私有IP
3. validate_llm_endpoint() - LLM端点模式：仅阻断云元数据，允许私有IP和localhost

安全审计编号: BK-LITE-002
"""

import ipaddress
from unittest.mock import patch

import pytest

from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator

# ===========================================================================
# validate() 严格模式测试
# ===========================================================================


class TestSSRFValidatorStrictMode:
    """严格模式测试 - 用于用户输入的URL（Fetch Tool, WebsiteLoader）"""

    # -------------------------------------------------------------------------
    # 云元数据阻断测试
    # -------------------------------------------------------------------------

    def test_blocks_aws_metadata_ip(self):
        """阻断 AWS 元数据 IP"""
        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate("http://169.254.169.254/latest/meta-data/")

    def test_blocks_aws_ecs_metadata_ip(self):
        """阻断 AWS ECS 元数据 IP"""
        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate("http://169.254.170.2/v2/credentials/")

    def test_blocks_gcp_metadata_hostname(self):
        """阻断 GCP 元数据主机名"""
        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate("http://metadata.google.internal/computeMetadata/v1/")

    def test_blocks_gcp_metadata_alt_hostname(self):
        """阻断 GCP 元数据备用主机名"""
        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate("http://metadata.goog/computeMetadata/v1/")

    # -------------------------------------------------------------------------
    # 私有IP阻断测试
    # -------------------------------------------------------------------------

    @patch("socket.getaddrinfo")
    def test_blocks_private_ip_10_x(self, mock_getaddrinfo):
        """阻断 10.x.x.x 私有IP"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.1", 80))]
        with pytest.raises(SSRFError, match="禁止的网段"):
            SSRFValidator.validate("http://internal.example.com/api")

    @patch("socket.getaddrinfo")
    def test_blocks_private_ip_172_16(self, mock_getaddrinfo):
        """阻断 172.16.x.x 私有IP"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("172.16.0.1", 80))]
        with pytest.raises(SSRFError, match="禁止的网段"):
            SSRFValidator.validate("http://internal.example.com/api")

    @patch("socket.getaddrinfo")
    def test_blocks_private_ip_192_168(self, mock_getaddrinfo):
        """阻断 192.168.x.x 私有IP"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.100", 80))]
        with pytest.raises(SSRFError, match="禁止的网段"):
            SSRFValidator.validate("http://internal.example.com/api")

    # -------------------------------------------------------------------------
    # Localhost阻断测试
    # -------------------------------------------------------------------------

    def test_blocks_localhost_hostname(self):
        """阻断 localhost 主机名"""
        with pytest.raises(SSRFError, match="禁止的网段"):
            SSRFValidator.validate("http://localhost:8080/admin")

    def test_blocks_127_0_0_1(self):
        """阻断 127.0.0.1"""
        with pytest.raises(SSRFError, match="禁止的网段"):
            SSRFValidator.validate("http://127.0.0.1:3000/api")

    @patch("socket.getaddrinfo")
    def test_blocks_ipv6_loopback(self, mock_getaddrinfo):
        """阻断 IPv6 回环地址"""
        mock_getaddrinfo.return_value = [(10, 1, 6, "", ("::1", 80, 0, 0))]
        with pytest.raises(SSRFError, match="禁止的网段"):
            SSRFValidator.validate("http://ipv6host.example.com/")

    # -------------------------------------------------------------------------
    # 协议阻断测试
    # -------------------------------------------------------------------------

    def test_blocks_file_protocol(self):
        """阻断 file:// 协议"""
        with pytest.raises(SSRFError, match="不允许的协议"):
            SSRFValidator.validate("file:///etc/passwd")

    def test_blocks_ftp_protocol(self):
        """阻断 ftp:// 协议"""
        with pytest.raises(SSRFError, match="不允许的协议"):
            SSRFValidator.validate("ftp://ftp.example.com/file")

    def test_blocks_gopher_protocol(self):
        """阻断 gopher:// 协议"""
        with pytest.raises(SSRFError, match="不允许的协议"):
            SSRFValidator.validate("gopher://evil.com/")

    # -------------------------------------------------------------------------
    # 公网URL允许测试
    # -------------------------------------------------------------------------

    @patch("socket.getaddrinfo")
    def test_allows_public_ip(self, mock_getaddrinfo):
        """允许公网IP"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        result = SSRFValidator.validate("https://example.com/api")
        assert "example.com" in result

    @patch("socket.getaddrinfo")
    def test_allows_https_protocol(self, mock_getaddrinfo):
        """允许 https:// 协议"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        result = SSRFValidator.validate("https://example.com/")
        assert result.startswith("https://")

    # -------------------------------------------------------------------------
    # 边界情况测试
    # -------------------------------------------------------------------------

    def test_rejects_empty_url(self):
        """拒绝空URL"""
        with pytest.raises(SSRFError, match="不能为空"):
            SSRFValidator.validate("")

    def test_rejects_none_url(self):
        """拒绝None URL"""
        with pytest.raises(SSRFError, match="不能为空"):
            SSRFValidator.validate(None)

    def test_rejects_url_without_host(self):
        """拒绝无主机名的URL"""
        with pytest.raises(SSRFError, match="有效主机名"):
            SSRFValidator.validate("http:///path")


# ===========================================================================
# validate_llm_endpoint() LLM端点模式测试
# ===========================================================================


class TestSSRFValidatorLLMEndpointMode:
    """LLM端点模式测试 - 用于LLM/Rerank服务端点（允许内网部署）"""

    # -------------------------------------------------------------------------
    # 云元数据阻断测试（必须阻断）
    # -------------------------------------------------------------------------

    def test_blocks_aws_metadata(self):
        """阻断 AWS 元数据"""
        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_llm_endpoint("http://169.254.169.254/latest/meta-data/")

    def test_blocks_aws_ecs_metadata(self):
        """阻断 AWS ECS 元数据"""
        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_llm_endpoint("http://169.254.170.2/v2/credentials/")

    def test_blocks_gcp_metadata_hostname(self):
        """阻断 GCP 元数据主机名"""
        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_llm_endpoint("http://metadata.google.internal/")

    # -------------------------------------------------------------------------
    # 私有IP允许测试（内网vLLM/Ollama场景）
    # -------------------------------------------------------------------------

    @patch("socket.getaddrinfo")
    def test_allows_private_ip_10_x(self, mock_getaddrinfo):
        """允许 10.x.x.x 私有IP（内网vLLM）"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.1", 8000))]
        result = SSRFValidator.validate_llm_endpoint("http://vllm.internal:8000/v1")
        assert result is not None

    @patch("socket.getaddrinfo")
    def test_allows_private_ip_172_16(self, mock_getaddrinfo):
        """允许 172.16.x.x 私有IP"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("172.16.0.1", 8000))]
        result = SSRFValidator.validate_llm_endpoint("http://llm.internal:8000/v1")
        assert result is not None

    @patch("socket.getaddrinfo")
    def test_allows_private_ip_192_168(self, mock_getaddrinfo):
        """允许 192.168.x.x 私有IP（本地Ollama）"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.100", 11434))]
        result = SSRFValidator.validate_llm_endpoint("http://ollama.local:11434/api")
        assert result is not None

    # -------------------------------------------------------------------------
    # Localhost允许测试（本地LLM服务）
    # -------------------------------------------------------------------------

    def test_allows_localhost(self):
        """允许 localhost（本地Ollama）"""
        result = SSRFValidator.validate_llm_endpoint("http://localhost:11434/api")
        assert "localhost" in result

    def test_allows_127_0_0_1(self):
        """允许 127.0.0.1"""
        result = SSRFValidator.validate_llm_endpoint("http://127.0.0.1:8000/v1")
        assert "127.0.0.1" in result

    # -------------------------------------------------------------------------
    # 协议测试
    # -------------------------------------------------------------------------

    def test_blocks_file_protocol(self):
        """阻断 file:// 协议"""
        with pytest.raises(SSRFError, match="不允许的协议"):
            SSRFValidator.validate_llm_endpoint("file:///etc/passwd")

    @patch("socket.getaddrinfo")
    def test_allows_https(self, mock_getaddrinfo):
        """允许 https:// 协议"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        result = SSRFValidator.validate_llm_endpoint("https://api.openai.com/v1")
        assert result.startswith("https://")


# ===========================================================================
# validate_callback() 回调模式测试
# ===========================================================================


class TestSSRFValidatorCallbackMode:
    """回调模式测试 - 用于Job回调URL（允许内网但阻断localhost）"""

    # -------------------------------------------------------------------------
    # 云元数据阻断测试
    # -------------------------------------------------------------------------

    def test_blocks_aws_metadata(self):
        """阻断 AWS 元数据"""
        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_callback("http://169.254.169.254/latest/meta-data/")

    def test_blocks_aws_ecs_metadata(self):
        """阻断 AWS ECS 元数据"""
        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_callback("http://169.254.170.2/v2/credentials/")

    def test_blocks_gcp_metadata_hostname(self):
        """阻断 GCP 元数据主机名"""
        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_callback("http://metadata.google.internal/")

    # -------------------------------------------------------------------------
    # Localhost阻断测试
    # -------------------------------------------------------------------------

    def test_blocks_localhost(self):
        """阻断 localhost"""
        with pytest.raises(SSRFError, match="localhost"):
            SSRFValidator.validate_callback("http://localhost:8080/callback")

    def test_blocks_127_0_0_1(self):
        """阻断 127.0.0.1"""
        with pytest.raises(SSRFError, match="localhost"):
            SSRFValidator.validate_callback("http://127.0.0.1:3000/callback")

    @patch("socket.getaddrinfo")
    def test_blocks_ipv6_loopback(self, mock_getaddrinfo):
        """阻断 IPv6 回环地址"""
        mock_getaddrinfo.return_value = [(10, 1, 6, "", ("::1", 80, 0, 0))]
        with pytest.raises(SSRFError, match="localhost"):
            SSRFValidator.validate_callback("http://ipv6host.example.com/callback")

    # -------------------------------------------------------------------------
    # 私有IP允许测试（内网回调场景）
    # -------------------------------------------------------------------------

    @patch("socket.getaddrinfo")
    def test_allows_private_ip_10_x(self, mock_getaddrinfo):
        """允许 10.x.x.x 私有IP（内网回调）"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.1", 80))]
        result = SSRFValidator.validate_callback("http://callback.internal/webhook")
        assert result is not None

    @patch("socket.getaddrinfo")
    def test_allows_private_ip_172_16(self, mock_getaddrinfo):
        """允许 172.16.x.x 私有IP"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("172.16.0.1", 80))]
        result = SSRFValidator.validate_callback("http://callback.internal/webhook")
        assert result is not None

    @patch("socket.getaddrinfo")
    def test_allows_private_ip_192_168(self, mock_getaddrinfo):
        """允许 192.168.x.x 私有IP"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.100", 80))]
        result = SSRFValidator.validate_callback("http://callback.internal/webhook")
        assert result is not None

    # -------------------------------------------------------------------------
    # 空值处理测试
    # -------------------------------------------------------------------------

    def test_returns_none_for_none_input(self):
        """None输入返回None"""
        result = SSRFValidator.validate_callback(None)
        assert result is None

    def test_returns_none_for_empty_string(self):
        """空字符串返回None"""
        result = SSRFValidator.validate_callback("")
        assert result is None

    def test_returns_none_for_whitespace(self):
        """空白字符串返回None"""
        result = SSRFValidator.validate_callback("   ")
        assert result is None


# ===========================================================================
# 三层防护策略对比测试
# ===========================================================================


class TestSSRFValidatorThreeLayerComparison:
    """三层防护策略对比测试 - 验证不同模式的阻断范围差异"""

    @patch("socket.getaddrinfo")
    def test_private_ip_blocked_in_strict_allowed_in_llm_and_callback(self, mock_getaddrinfo):
        """私有IP：严格模式阻断，LLM和回调模式允许"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.1", 80))]

        # 严格模式阻断
        with pytest.raises(SSRFError):
            SSRFValidator.validate("http://internal.example.com/")

        # LLM模式允许
        result = SSRFValidator.validate_llm_endpoint("http://internal.example.com/")
        assert result is not None

        # 回调模式允许
        result = SSRFValidator.validate_callback("http://internal.example.com/")
        assert result is not None

    def test_localhost_blocked_in_strict_and_callback_allowed_in_llm(self):
        """Localhost：严格和回调模式阻断，LLM模式允许"""
        # 严格模式阻断
        with pytest.raises(SSRFError):
            SSRFValidator.validate("http://localhost:8080/")

        # 回调模式阻断
        with pytest.raises(SSRFError):
            SSRFValidator.validate_callback("http://localhost:8080/")

        # LLM模式允许
        result = SSRFValidator.validate_llm_endpoint("http://localhost:8080/")
        assert result is not None

    def test_cloud_metadata_blocked_in_all_modes(self):
        """云元数据：所有模式都阻断"""
        url = "http://169.254.169.254/latest/meta-data/"

        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate(url)

        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_callback(url)

        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_llm_endpoint(url)

    @patch("socket.getaddrinfo")
    def test_public_ip_allowed_in_all_modes(self, mock_getaddrinfo):
        """公网IP：所有模式都允许"""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]

        result1 = SSRFValidator.validate("https://example.com/")
        assert result1 is not None

        result2 = SSRFValidator.validate_callback("https://example.com/")
        assert result2 is not None

        result3 = SSRFValidator.validate_llm_endpoint("https://example.com/")
        assert result3 is not None


class TestSSRFValidatorWhitelist:
    """白名单放行 + 元数据永封 + 空白名单零回归。"""

    @patch("socket.getaddrinfo")
    def test_whitelisted_private_ip_allowed(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.11.73.15", 8000))]
        with patch.object(SSRFValidator, "_get_allowed_networks", return_value=[ipaddress.ip_network("10.11.73.0/24")]):
            assert SSRFValidator.validate("http://10.11.73.15:8000/sse") == "http://10.11.73.15:8000/sse"

    @patch("socket.getaddrinfo")
    def test_non_whitelisted_private_ip_blocked(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.1", 80))]
        with patch.object(SSRFValidator, "_get_allowed_networks", return_value=[ipaddress.ip_network("10.11.73.0/24")]):
            with pytest.raises(SSRFError, match="禁止的网段"):
                SSRFValidator.validate("http://10.0.0.1/api")

    @patch("socket.getaddrinfo")
    def test_metadata_blocked_even_if_whitelisted(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("169.254.169.254", 80))]
        with patch.object(SSRFValidator, "_get_allowed_networks", return_value=[ipaddress.ip_network("169.254.0.0/16")]):
            with pytest.raises(SSRFError, match="云元数据"):
                SSRFValidator.validate("http://169.254.169.254/latest/meta-data/")

    @patch("socket.getaddrinfo")
    def test_empty_whitelist_keeps_strict(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.1", 80))]
        with patch.object(SSRFValidator, "_get_allowed_networks", return_value=[]):
            with pytest.raises(SSRFError, match="禁止的网段"):
                SSRFValidator.validate("http://10.0.0.1/api")
