"""opspilot-core 切片: metis/llm/common/structured_output_parser 同步 helper 真实测试。

只测同步逻辑：_configure_thinking_mode（按模型名匹配禁用 thinking 注入 extra_body）
与 _get_openai_client（从 ChatOpenAI 风格实例提取 key/base_url 构造原生 client，
SecretStr 解密、缺 key 抛错、client 缓存）。OpenAI 构造器是唯一外部边界，mock 之。
跳过 async parse_with_structured_output（走真实 LLM 调用）。
"""

import pydantic.root_model  # noqa

from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.metis.llm.common.structured_output_parser import StructuredOutputParser

pytestmark = pytest.mark.unit

MOD = "apps.opspilot.metis.llm.common.structured_output_parser"


class _SecretStr:
    def __init__(self, v):
        self._v = v

    def get_secret_value(self):
        return self._v


class _FakeLLM:
    """模拟 langchain ChatOpenAI 实例形态。"""

    def __init__(self, model_name="gpt-4o", api_key="sk-x", base_url="http://llm.local/v1"):
        self.model_name = model_name
        self.openai_api_key = _SecretStr(api_key) if api_key is not None else None
        self.openai_api_base = base_url
        self.temperature = 0.5
        self.extra_body = None


class TestConfigureThinkingMode:
    def test_qwen_model_disables_thinking(self):
        llm = _FakeLLM(model_name="Qwen2.5-72B")
        p = StructuredOutputParser(llm)
        # Qwen 命中禁用列表，写入 extra_body
        assert p.llm.extra_body == {"enable_thinking": False}

    def test_non_qwen_model_untouched(self):
        llm = _FakeLLM(model_name="gpt-4o")
        StructuredOutputParser(llm)
        # 非禁用模型不注入 extra_body
        assert llm.extra_body is None

    def test_case_insensitive_match(self):
        llm = _FakeLLM(model_name="my-qwen-finetune")
        StructuredOutputParser(llm)
        assert llm.extra_body == {"enable_thinking": False}

    def test_existing_extra_body_preserved_with_thinking_flag(self):
        llm = _FakeLLM(model_name="Qwen")
        llm.extra_body = {"foo": "bar"}
        StructuredOutputParser(llm)
        assert llm.extra_body == {"foo": "bar", "enable_thinking": False}


class TestGetOpenAIClient:
    def test_builds_client_from_secret_and_base_url(self):
        llm = _FakeLLM(api_key="sk-secret", base_url="http://custom/v1")
        p = StructuredOutputParser(llm)
        with patch(f"{MOD}.OpenAI") as OpenAICls:
            OpenAICls.return_value = MagicMock(name="client")
            client = p._get_openai_client()
        kwargs = OpenAICls.call_args.kwargs
        # SecretStr 解密后传入
        assert kwargs["api_key"] == "sk-secret"
        assert kwargs["base_url"] == "http://custom/v1"
        assert kwargs["timeout"] == 60.0
        assert client is OpenAICls.return_value

    def test_client_is_cached(self):
        llm = _FakeLLM()
        p = StructuredOutputParser(llm)
        with patch(f"{MOD}.OpenAI") as OpenAICls:
            OpenAICls.return_value = MagicMock()
            c1 = p._get_openai_client()
            c2 = p._get_openai_client()
        # 第二次复用缓存，不再构造
        assert c1 is c2
        assert OpenAICls.call_count == 1

    def test_no_base_url_omits_kwarg(self):
        llm = _FakeLLM(base_url=None)
        p = StructuredOutputParser(llm)
        with patch(f"{MOD}.OpenAI") as OpenAICls:
            OpenAICls.return_value = MagicMock()
            p._get_openai_client()
        assert "base_url" not in OpenAICls.call_args.kwargs

    def test_missing_api_key_raises(self):
        llm = _FakeLLM(api_key=None)
        p = StructuredOutputParser(llm)
        with pytest.raises(ValueError, match="API key"):
            p._get_openai_client()
