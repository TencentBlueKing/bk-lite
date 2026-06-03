"""回调服务单元测试"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Retry

from apps.core.utils.ssrf_validator import SSRFError


@pytest.mark.unit
class TestSendCallback:
    """测试 send_callback 入口函数"""

    def test_no_callback_url_does_nothing(self):
        from apps.job_mgmt.services.callback_service import send_callback

        execution = MagicMock()
        execution.callback_url = None

        with patch("apps.job_mgmt.services.callback_service.current_app") as mock_app:
            send_callback(execution)
            mock_app.send_task.assert_not_called()

    def test_empty_callback_url_does_nothing(self):
        from apps.job_mgmt.services.callback_service import send_callback

        execution = MagicMock()
        execution.callback_url = ""

        with patch("apps.job_mgmt.services.callback_service.current_app") as mock_app:
            send_callback(execution)
            mock_app.send_task.assert_not_called()

    def test_sends_celery_task_when_url_present(self):
        from apps.job_mgmt.services.callback_service import send_callback

        execution = MagicMock()
        execution.callback_url = "http://example.com/callback"
        execution.id = 1
        execution.status = "success"
        execution.total_count = 3
        execution.success_count = 3
        execution.failed_count = 0
        execution.finished_at = datetime(2026, 4, 30, 10, 0, 0)

        with patch("apps.job_mgmt.services.callback_service.current_app") as mock_app:
            send_callback(execution)
            mock_app.send_task.assert_called_once_with(
                "apps.job_mgmt.tasks.do_callback_task",
                args=[
                    "http://example.com/callback",
                    {
                        "task_id": 1,
                        "status": "success",
                        "total_count": 3,
                        "success_count": 3,
                        "failed_count": 0,
                        "finished_at": "2026-04-30T10:00:00",
                    },
                    1,
                ],
            )


@pytest.mark.unit
class TestDoCallbackTask:
    """测试 do_callback_task Celery 任务的核心逻辑

    autoretry_for=(Exception,) 意味着所有异常都会被 Celery 捕获并触发 retry，
    retry 会抛出 celery.exceptions.Retry。因此错误场景需要 expect Retry。
    """

    @patch("apps.job_mgmt.tasks.SSRFValidator.validate_callback")
    @patch("apps.job_mgmt.tasks.safe_post")
    def test_success_200(self, mock_safe_post, mock_validate):
        from apps.job_mgmt.tasks import do_callback_task

        mock_safe_post.return_value = MagicMock(status_code=200)
        do_callback_task("http://example.com/cb", {"task_id": 1}, 1)
        mock_validate.assert_called_once_with("http://example.com/cb")
        mock_safe_post.assert_called_once()

    @patch("apps.job_mgmt.tasks.SSRFValidator.validate_callback")
    @patch("apps.job_mgmt.tasks.safe_post")
    def test_success_201(self, mock_safe_post, mock_validate):
        from apps.job_mgmt.tasks import do_callback_task

        mock_safe_post.return_value = MagicMock(status_code=201)
        do_callback_task("http://example.com/cb", {"task_id": 1}, 1)
        mock_safe_post.assert_called_once()

    @patch("apps.job_mgmt.tasks.SSRFValidator.validate_callback")
    @patch("apps.job_mgmt.tasks.safe_post")
    def test_raises_on_non_2xx(self, mock_safe_post, mock_validate):
        from apps.job_mgmt.tasks import do_callback_task

        mock_safe_post.return_value = MagicMock(status_code=500)
        with pytest.raises((RuntimeError, Retry)):
            do_callback_task("http://example.com/cb", {"task_id": 1}, 1)

    @patch("apps.job_mgmt.tasks.SSRFValidator.validate_callback")
    @patch("apps.job_mgmt.tasks.safe_post")
    def test_raises_on_400(self, mock_safe_post, mock_validate):
        from apps.job_mgmt.tasks import do_callback_task

        mock_safe_post.return_value = MagicMock(status_code=400)
        with pytest.raises((RuntimeError, Retry)):
            do_callback_task("http://example.com/cb", {"task_id": 1}, 1)

    @patch("apps.job_mgmt.tasks.SSRFValidator.validate_callback")
    @patch("apps.job_mgmt.tasks.safe_post")
    def test_raises_on_network_error(self, mock_safe_post, mock_validate):
        from apps.job_mgmt.tasks import do_callback_task

        mock_safe_post.side_effect = Exception("connection refused")
        with pytest.raises((Exception, Retry)):
            do_callback_task("http://example.com/cb", {"task_id": 1}, 1)


@pytest.mark.unit
class TestDoCallbackTaskSSRF:
    """测试 do_callback_task 的 SSRF 防护（宽松模式：阻断云元数据和 localhost）"""

    @patch("apps.job_mgmt.tasks.SSRFValidator.validate_callback")
    @patch("apps.job_mgmt.tasks.safe_post")
    def test_private_ip_allowed(self, mock_safe_post, mock_validate):
        """测试私网地址允许通过（宽松模式）"""
        from apps.job_mgmt.tasks import do_callback_task

        mock_safe_post.return_value = MagicMock(status_code=200)

        # 宽松模式下私网地址应该通过
        do_callback_task("http://192.168.1.1/callback", {"task_id": 1}, 1)
        mock_validate.assert_called_once_with("http://192.168.1.1/callback")
        mock_safe_post.assert_called_once()

    @patch("apps.job_mgmt.tasks.SSRFValidator.validate_callback")
    @patch("apps.job_mgmt.tasks.safe_post")
    def test_ssrf_cloud_metadata_blocked(self, mock_safe_post, mock_validate):
        """测试云元数据地址被拒绝"""
        from apps.job_mgmt.tasks import do_callback_task

        mock_validate.side_effect = SSRFError("禁止访问云元数据地址: 169.254.169.254")

        # SSRF 校验失败应直接返回，不调用 safe_post
        do_callback_task("http://169.254.169.254/latest/meta-data/", {"task_id": 1}, 1)
        mock_safe_post.assert_not_called()

    @patch("apps.job_mgmt.tasks.SSRFValidator.validate_callback")
    @patch("apps.job_mgmt.tasks.safe_post")
    def test_localhost_blocked(self, mock_safe_post, mock_validate):
        """测试 localhost 被拒绝"""
        from apps.job_mgmt.tasks import do_callback_task

        mock_validate.side_effect = SSRFError("禁止访问 localhost: 127.0.0.1")

        # localhost 应该被阻断
        do_callback_task("http://localhost/admin", {"task_id": 1}, 1)
        mock_safe_post.assert_not_called()

    @patch("apps.job_mgmt.tasks.SSRFValidator.validate_callback")
    @patch("apps.job_mgmt.tasks.safe_post")
    def test_public_url_passes(self, mock_safe_post, mock_validate):
        """测试公网地址通过"""
        from apps.job_mgmt.tasks import do_callback_task

        mock_safe_post.return_value = MagicMock(status_code=200)

        do_callback_task("https://example.com/callback", {"task_id": 1}, 1)
        mock_validate.assert_called_once_with("https://example.com/callback")
        mock_safe_post.assert_called_once()

    @patch("apps.job_mgmt.tasks.SSRFValidator.validate_callback")
    @patch("apps.job_mgmt.tasks.safe_post")
    def test_signed_headers_included(self, mock_safe_post, mock_validate):
        """测试回调请求包含签名头"""
        from apps.job_mgmt.tasks import do_callback_task

        mock_safe_post.return_value = MagicMock(status_code=200)

        do_callback_task("https://example.com/callback", {"task_id": 1}, 1)

        # 验证 safe_post 被调用时包含 headers 参数
        call_kwargs = mock_safe_post.call_args[1]
        assert "headers" in call_kwargs
        headers = call_kwargs["headers"]
        assert "X-BK-Lite-Timestamp" in headers
        assert "X-BK-Lite-Signature" in headers
        assert "X-BK-Lite-Source" in headers
        assert headers["X-BK-Lite-Source"] == "bk-lite-job-mgmt"


@pytest.mark.unit
class TestCallbackSigner:
    """测试回调签名工具"""

    def test_sign_callback_deterministic(self):
        """测试签名是确定性的"""
        from apps.job_mgmt.utils.callback_signer import sign_callback

        payload = {"task_id": 1, "status": "success"}
        timestamp = 1700000000

        sig1 = sign_callback(payload, timestamp)
        sig2 = sign_callback(payload, timestamp)
        assert sig1 == sig2

    def test_sign_callback_different_payload(self):
        """测试不同 payload 产生不同签名"""
        from apps.job_mgmt.utils.callback_signer import sign_callback

        timestamp = 1700000000
        sig1 = sign_callback({"task_id": 1}, timestamp)
        sig2 = sign_callback({"task_id": 2}, timestamp)
        assert sig1 != sig2

    def test_sign_callback_different_timestamp(self):
        """测试不同时间戳产生不同签名"""
        from apps.job_mgmt.utils.callback_signer import sign_callback

        payload = {"task_id": 1}
        sig1 = sign_callback(payload, 1700000000)
        sig2 = sign_callback(payload, 1700000001)
        assert sig1 != sig2

    def test_get_signed_headers_structure(self):
        """测试签名头结构正确"""
        from apps.job_mgmt.utils.callback_signer import get_signed_headers

        headers = get_signed_headers({"task_id": 1})

        assert "X-BK-Lite-Timestamp" in headers
        assert "X-BK-Lite-Signature" in headers
        assert "X-BK-Lite-Source" in headers
        assert "Content-Type" in headers

        # 时间戳应该是数字字符串
        assert headers["X-BK-Lite-Timestamp"].isdigit()
        # 签名应该是 64 字符的十六进制（SHA256）
        assert len(headers["X-BK-Lite-Signature"]) == 64
        assert all(c in "0123456789abcdef" for c in headers["X-BK-Lite-Signature"])

    def test_verify_callback_signature_valid(self):
        """测试有效签名验证通过"""
        from apps.job_mgmt.utils.callback_signer import sign_callback, verify_callback_signature

        payload = {"task_id": 1}
        timestamp = 1700000000
        signature = sign_callback(payload, timestamp)

        # 模拟当前时间在有效期内
        with patch("apps.job_mgmt.utils.callback_signer.time.time", return_value=1700000100):
            assert verify_callback_signature(payload, timestamp, signature) is True

    def test_verify_callback_signature_expired(self):
        """测试过期签名验证失败"""
        from apps.job_mgmt.utils.callback_signer import sign_callback, verify_callback_signature

        payload = {"task_id": 1}
        timestamp = 1700000000
        signature = sign_callback(payload, timestamp)

        # 模拟当前时间超过有效期（默认 300 秒）
        with patch("apps.job_mgmt.utils.callback_signer.time.time", return_value=1700000400):
            assert verify_callback_signature(payload, timestamp, signature) is False

    def test_verify_callback_signature_tampered(self):
        """测试篡改签名验证失败"""
        from apps.job_mgmt.utils.callback_signer import verify_callback_signature

        payload = {"task_id": 1}
        timestamp = 1700000000

        # 篡改签名
        tampered_signature = "a" * 64

        with patch("apps.job_mgmt.utils.callback_signer.time.time", return_value=1700000100):
            assert verify_callback_signature(payload, timestamp, tampered_signature) is False


@pytest.mark.unit
class TestSSRFValidatorCallback:
    """测试 SSRFValidator.validate_callback 宽松模式"""

    def test_public_url_passes(self):
        """测试公网地址通过"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        # 公网地址应该通过
        result = SSRFValidator.validate_callback("https://example.com/callback")
        assert result == "https://example.com/callback"

    def test_none_returns_none(self):
        """测试 None 返回 None"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        assert SSRFValidator.validate_callback(None) is None

    def test_empty_string_returns_none(self):
        """测试空字符串返回 None"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        assert SSRFValidator.validate_callback("") is None
        assert SSRFValidator.validate_callback("   ") is None

    def test_cloud_metadata_hostname_blocked(self):
        """测试云元数据主机名被阻断"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_callback("http://169.254.169.254/latest/meta-data/")

        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_callback("http://metadata.google.internal/computeMetadata/v1/")

    def test_invalid_scheme_blocked(self):
        """测试非法协议被阻断"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        with pytest.raises(SSRFError, match="不允许的协议"):
            SSRFValidator.validate_callback("ftp://example.com/file")

        with pytest.raises(SSRFError, match="不允许的协议"):
            SSRFValidator.validate_callback("file:///etc/passwd")

    def test_missing_hostname_blocked(self):
        """测试缺少主机名被阻断"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        with pytest.raises(SSRFError, match="有效主机名"):
            SSRFValidator.validate_callback("http:///path")

    @patch("apps.core.utils.ssrf_validator.socket.getaddrinfo")
    def test_private_ip_allowed(self, mock_getaddrinfo):
        """测试私网地址允许通过（宽松模式）"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        # 模拟 DNS 解析到私网地址
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("192.168.1.100", 80)),
        ]

        # 宽松模式下私网地址应该通过
        result = SSRFValidator.validate_callback("http://internal-server/callback")
        assert result == "http://internal-server/callback"

    @patch("apps.core.utils.ssrf_validator.socket.getaddrinfo")
    def test_localhost_blocked(self, mock_getaddrinfo):
        """测试 localhost 被阻断"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        # 模拟 DNS 解析到 127.0.0.1
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("127.0.0.1", 80)),
        ]

        # localhost 应该被阻断
        with pytest.raises(SSRFError, match="localhost"):
            SSRFValidator.validate_callback("http://localhost/callback")

    @patch("apps.core.utils.ssrf_validator.socket.getaddrinfo")
    def test_cloud_metadata_ip_blocked(self, mock_getaddrinfo):
        """测试云元数据 IP 被阻断（即使通过 DNS 解析）"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        # 模拟 DNS 解析到云元数据 IP
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("169.254.169.254", 80)),
        ]

        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_callback("http://evil-redirect.com/callback")

    @patch("apps.core.utils.ssrf_validator.socket.getaddrinfo")
    def test_ecs_metadata_ip_blocked(self, mock_getaddrinfo):
        """测试 AWS ECS 元数据 IP 被阻断"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        # 模拟 DNS 解析到 ECS 元数据 IP
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("169.254.170.2", 80)),
        ]

        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_callback("http://ecs-metadata.local/callback")


@pytest.mark.unit
class TestSSRFValidatorLLMEndpoint:
    """测试 SSRFValidator.validate_llm_endpoint 宽松模式（LLM API 端点）

    LLM api_base 场景特点：
    - 允许私网地址（企业内网部署 vLLM/Ollama/LocalAI）
    - 允许 localhost（本地 LLM 服务）
    - 仅阻断云元数据地址（防止凭证泄露）
    """

    def test_public_url_passes(self):
        """测试公网地址通过"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        result = SSRFValidator.validate_llm_endpoint("https://api.openai.com/v1")
        assert result == "https://api.openai.com/v1"

    def test_empty_url_raises(self):
        """测试空 URL 抛出异常"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        with pytest.raises(SSRFError, match="不能为空"):
            SSRFValidator.validate_llm_endpoint("")

        with pytest.raises(SSRFError, match="不能为空"):
            SSRFValidator.validate_llm_endpoint("   ")

        with pytest.raises(SSRFError, match="不能为空"):
            SSRFValidator.validate_llm_endpoint(None)  # type: ignore[arg-type]

    def test_cloud_metadata_hostname_blocked(self):
        """测试云元数据主机名被阻断"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_llm_endpoint("http://169.254.169.254/latest/meta-data/")

        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_llm_endpoint("http://metadata.google.internal/computeMetadata/v1/")

    def test_invalid_scheme_blocked(self):
        """测试非法协议被阻断"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        with pytest.raises(SSRFError, match="不允许的协议"):
            SSRFValidator.validate_llm_endpoint("ftp://llm-server.local/v1")

        with pytest.raises(SSRFError, match="不允许的协议"):
            SSRFValidator.validate_llm_endpoint("file:///etc/passwd")

    def test_missing_hostname_blocked(self):
        """测试缺少主机名被阻断"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        with pytest.raises(SSRFError, match="有效主机名"):
            SSRFValidator.validate_llm_endpoint("http:///v1")

    @patch("apps.core.utils.ssrf_validator.socket.getaddrinfo")
    def test_private_ip_allowed(self, mock_getaddrinfo):
        """测试私网地址允许通过（内网 LLM 服务场景）"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        # 模拟 DNS 解析到私网地址（如内网 vLLM 服务）
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("192.168.1.100", 8000)),
        ]

        result = SSRFValidator.validate_llm_endpoint("http://vllm-server.internal:8000/v1")
        assert result == "http://vllm-server.internal:8000/v1"

    @patch("apps.core.utils.ssrf_validator.socket.getaddrinfo")
    def test_10_network_allowed(self, mock_getaddrinfo):
        """测试 10.x.x.x 私网地址允许通过"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("10.0.0.50", 11434)),
        ]

        result = SSRFValidator.validate_llm_endpoint("http://ollama.internal:11434/v1")
        assert result == "http://ollama.internal:11434/v1"

    @patch("apps.core.utils.ssrf_validator.socket.getaddrinfo")
    def test_172_network_allowed(self, mock_getaddrinfo):
        """测试 172.16.x.x 私网地址允许通过"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("172.16.0.100", 8080)),
        ]

        result = SSRFValidator.validate_llm_endpoint("http://localai.internal:8080/v1")
        assert result == "http://localai.internal:8080/v1"

    @patch("apps.core.utils.ssrf_validator.socket.getaddrinfo")
    def test_localhost_allowed(self, mock_getaddrinfo):
        """测试 localhost 允许通过（本地 Ollama 等场景）"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("127.0.0.1", 11434)),
        ]

        result = SSRFValidator.validate_llm_endpoint("http://localhost:11434/v1")
        assert result == "http://localhost:11434/v1"

    @patch("apps.core.utils.ssrf_validator.socket.getaddrinfo")
    def test_cloud_metadata_ip_blocked(self, mock_getaddrinfo):
        """测试云元数据 IP 被阻断（即使通过 DNS 解析）"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        # 模拟 DNS 解析到云元数据 IP（攻击者可能注册恶意域名）
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("169.254.169.254", 80)),
        ]

        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_llm_endpoint("http://evil-llm-server.com/v1")

    @patch("apps.core.utils.ssrf_validator.socket.getaddrinfo")
    def test_ecs_metadata_ip_blocked(self, mock_getaddrinfo):
        """测试 AWS ECS 元数据 IP 被阻断"""
        from apps.core.utils.ssrf_validator import SSRFValidator

        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("169.254.170.2", 80)),
        ]

        with pytest.raises(SSRFError, match="云元数据"):
            SSRFValidator.validate_llm_endpoint("http://ecs-llm.local/v1")
