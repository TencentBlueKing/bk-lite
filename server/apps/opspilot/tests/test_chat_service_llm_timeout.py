"""
测试 invoke_chat future.result() 超时保护（Issue #3718）

验证点：
- future.result() 携带 LLM_INVOKE_TIMEOUT 秒的超时
- LLM 卡死时 TimeoutError 被捕获并返回结构化错误响应（不永久阻塞）
- 超时时间可通过环境变量 LLM_INVOKE_TIMEOUT 配置
- LLMClientFactory 不再使用 timeout=3000（50分钟无效超时）

注：这些测试使用源码级别检查（Source-level verification），无需 Django 环境启动，
    因为修复的核心逻辑（timeout 参数和 TimeoutError 处理块）直接体现在源码结构中。
    revert 修复后，以下测试均应失败，从而证明测试覆盖了修复点。
"""

import os
import re
from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory

# ---------------------------------------------------------------------------
# Lazy imports of the target modules to avoid Django bootstrap at collection time
# ---------------------------------------------------------------------------


def _load_chat_service_source():
    path = os.path.join(os.path.dirname(__file__), "..", "services", "chat_service.py")
    with open(os.path.normpath(path), encoding="utf-8") as f:
        return f.read()


def _load_llm_client_factory_source():
    # Resolve relative to this file
    base = os.path.dirname(__file__)  # .../apps/opspilot/tests/
    factory_path = os.path.normpath(os.path.join(base, "..", "metis", "llm", "common", "llm_client_factory.py"))
    with open(factory_path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChatServiceFutureTimeout:
    """
    验证 chat_service.py 中 future.result() 的超时保护（Issue #3718）。

    判断标准（revert 修复后这些测试均应失败）：
    - revert future.result(timeout=...) → test_future_result_has_timeout 失败
    - revert TimeoutError handler → test_timeout_error_is_explicitly_caught 失败
    - revert LLM_INVOKE_TIMEOUT env var → test_llm_invoke_timeout_env_var_referenced 失败
    """

    @pytest.fixture(scope="class")
    def chat_service_src(self):
        return _load_chat_service_source()

    def test_future_result_has_timeout(self, chat_service_src):
        """
        future.result() 必须携带 timeout 参数。

        revert 修复（还原为 `future.result()`）后，此测试应失败。
        """
        match = re.search(r"future\.result\s*\(([^)]*)\)", chat_service_src)
        assert match, "chat_service.py 中未找到 future.result() 调用"
        args = match.group(1).strip()
        assert "timeout" in args, f"future.result() 缺少 timeout 参数，当前参数为：({args})。" "没有 timeout 参数时，LLM 卡死会导致 worker 线程永久阻塞（Issue #3718）。"

    def test_llm_invoke_timeout_env_var_referenced(self, chat_service_src):
        """
        超时值应通过 LLM_INVOKE_TIMEOUT 环境变量读取，支持运维侧调整。

        revert 后（移除 os.getenv("LLM_INVOKE_TIMEOUT", ...)）此测试失败。
        """
        assert "LLM_INVOKE_TIMEOUT" in chat_service_src, "chat_service.py 中未引用 LLM_INVOKE_TIMEOUT 环境变量。" "超时值应可通过环境变量配置。"

    def test_timeout_error_is_explicitly_caught(self, chat_service_src):
        """
        concurrent.futures.TimeoutError 应被单独捕获并返回清晰错误响应。

        revert（移除 except concurrent.futures.TimeoutError 块）后此测试失败。
        """
        assert "except concurrent.futures.TimeoutError" in chat_service_src, (
            "chat_service.py 未专门处理 concurrent.futures.TimeoutError。" "未处理的 TimeoutError 会向上传播为 500 错误，缺少明确提示。"
        )

    def test_timeout_error_handler_returns_error_type_field(self, chat_service_src):
        """
        TimeoutError 处理块应返回 error_type='TimeoutError'，便于前端区分超时与其他错误。
        """
        # Find the TimeoutError handler block
        idx = chat_service_src.find("except concurrent.futures.TimeoutError")
        assert idx != -1, "未找到 TimeoutError 处理块"
        # Check the next 500 chars for the error_type field
        handler_snippet = chat_service_src[idx : idx + 600]
        assert '"TimeoutError"' in handler_snippet or "'TimeoutError'" in handler_snippet, "TimeoutError 处理块应设置 error_type='TimeoutError'"
        assert "False" in handler_snippet, "TimeoutError 处理块应设置 success=False"

    def test_os_is_imported(self, chat_service_src):
        """os 模块必须被 import，用于 os.getenv('LLM_INVOKE_TIMEOUT', ...)"""
        assert "import os" in chat_service_src, "chat_service.py 缺少 import os，无法调用 os.getenv()"


class TestLLMClientFactoryTimeout:
    """
    验证 llm_client_factory.py 中 timeout=3000（50分钟）已被替换（Issue #3718）。

    revert 修复（还原为 timeout=3000）后，test_no_hardcoded_timeout_3000 失败。
    """

    @pytest.fixture(scope="class")
    def factory_src(self):
        return _load_llm_client_factory_source()

    def test_no_hardcoded_timeout_3000(self, factory_src):
        """
        llm_client_factory.py 中不应再出现 timeout=3000（即 3000 秒/50分钟）。

        revert 修复后，此测试应失败——证明测试覆盖了修复点。
        """
        count = factory_src.count("timeout=3000")
        assert count == 0, f"llm_client_factory.py 中仍存在 {count} 处 timeout=3000（50分钟无效超时）。" "应改为使用 LLM_INVOKE_TIMEOUT 环境变量。"

    def test_llm_invoke_timeout_env_var_in_factory(self, factory_src):
        """
        llm_client_factory.py 也应通过 LLM_INVOKE_TIMEOUT 统一控制客户端超时。
        """
        assert "LLM_INVOKE_TIMEOUT" in factory_src, (
            "llm_client_factory.py 未使用 LLM_INVOKE_TIMEOUT 环境变量。" "client-level timeout 应与 future.result() 超时保持一致。"
        )

    def test_llm_client_factory_default_timeout_is_300_seconds(self, factory_src):
        """未显式传入 timeout 时，LLM client 底座默认超时应为 300 秒。"""
        assert 'os.getenv("LLM_INVOKE_TIMEOUT", "300")' in factory_src
        assert "timeout=15" not in factory_src

    def test_os_is_imported_in_factory(self, factory_src):
        """os 模块必须被 import，用于 os.getenv()"""
        assert "import os" in factory_src, "llm_client_factory.py 缺少 import os，无法调用 os.getenv()"

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.OpenAI")
    def test_isolated_openai_uses_request_timeout(self, mock_openai, monkeypatch):
        """
        知识库构建使用 invoke_isolated，isolated OpenAI 客户端也必须支持按请求覆盖 timeout。

        revert 后（仍固定 timeout=60.0）此测试失败。
        """
        mock_openai.return_value = MagicMock()
        monkeypatch.setenv("LLM_INVOKE_TIMEOUT", "61")
        request = BasicLLMRequest(
            protocol_type="openai",
            openai_api_key="sk-key",
            openai_api_base="https://api.openai.com",
            extra_config={"timeout": 240},
        )

        LLMClientFactory.create_isolated_client(request)

        assert mock_openai.call_args[1]["timeout"] == 240.0

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.anthropic.Anthropic")
    def test_isolated_anthropic_uses_env_timeout(self, mock_anthropic, monkeypatch):
        """
        Anthropic isolated 客户端未显式传 request timeout 时，应回退 LLM_INVOKE_TIMEOUT。

        revert 后（仍固定 timeout=60.0）此测试失败。
        """
        mock_anthropic.return_value = MagicMock()
        monkeypatch.setenv("LLM_INVOKE_TIMEOUT", "180")
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-key",
            openai_api_base="https://api.anthropic.com",
        )

        LLMClientFactory.create_isolated_client(request)

        assert mock_anthropic.call_args[1]["timeout"] == 180.0
