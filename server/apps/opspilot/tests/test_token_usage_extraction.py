"""Token usage 提取与 OpenAI 客户端创建回归。"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from openai import omit

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator, extract_token_usage

pytestmark = pytest.mark.unit


def test_extract_usage_metadata_langchain_keys():
    usage = extract_token_usage(SimpleNamespace(usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}))
    assert usage.reported is True
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (10, 2, 12)


def test_extract_usage_metadata_openai_keys_like_minimax():
    """部分兼容网关把 prompt/completion 塞进 usage_metadata。"""
    usage = extract_token_usage(
        SimpleNamespace(
            usage_metadata={"prompt_tokens": 100, "completion_tokens": 20},
            response_metadata={},
        )
    )
    assert usage.reported is True
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (100, 20, 120)


def test_extract_response_metadata_usage_alias():
    usage = extract_token_usage(
        SimpleNamespace(
            usage_metadata=None,
            response_metadata={"usage": {"prompt_tokens": 7, "completion_tokens": 3}},
        )
    )
    assert usage.reported is True
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (7, 3, 10)


def test_extract_empty_usage_metadata_is_not_reported():
    """流式未带 include_usage 时常见空 usage_metadata,不应记成 reported=True 的全 0。"""
    usage = extract_token_usage(SimpleNamespace(usage_metadata={}, response_metadata={}))
    assert usage.reported is False
    assert usage.total_tokens == 0


def test_extract_all_zero_usage_metadata_is_not_reported():
    """兼容网关塞全 0 usage_metadata 时视为未上报。"""
    usage = extract_token_usage(
        SimpleNamespace(
            usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            response_metadata={},
        )
    )
    assert usage.reported is False


def test_accumulator_sums_openai_style_usage_metadata():
    acc = TokenUsageAccumulator()
    added, reported = acc.add(
        "run-1",
        SimpleNamespace(usage_metadata={"prompt_tokens": 11, "completion_tokens": 5}),
    )
    assert added and reported
    assert acc.as_openai_usage() == {
        "prompt_tokens": 11,
        "completion_tokens": 5,
        "total_tokens": 16,
    }


def test_restore_usage_on_dumped_stream_chunk():
    """流式 model_dump 把 usage 变成全 0 时，用原始 chunk.usage 回填。"""
    from apps.opspilot.metis.llm.chain.lc_patches import restore_usage_on_dumped_chunk, usage_payload_from_raw

    raw = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=41, completion_tokens=9, total_tokens=50))
    dumped = {"id": "chunk-1", "choices": [], "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}
    restored = restore_usage_on_dumped_chunk(raw, dumped)
    assert usage_payload_from_raw(restored["usage"]) == {
        "prompt_tokens": 41,
        "completion_tokens": 9,
        "total_tokens": 50,
    }


def test_openai_client_does_not_force_stream_usage():
    """不强制 stream_usage：部分兼容网关会因 stream_options 直接报错。"""
    created = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            created.update(kwargs)
            self.extra_body = None

    request = BasicLLMRequest(
        model="MiniMax-M2.5",
        openai_api_base="https://api.minimax.chat/v1",
        openai_api_key="test-key",
        temperature=0.2,
    )
    with patch(
        "apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI",
        _FakeChatOpenAI,
    ), patch(
        "apps.opspilot.metis.llm.common.llm_client_factory.SSRFValidator.validate_llm_endpoint",
    ):
        LLMClientFactory._create_openai_client(request, disable_stream=False)

    assert "stream_usage" not in created
    assert created.get("disable_streaming") is False


def test_openai_client_keeps_streaming_for_custom_base():
    created = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            created.update(kwargs)
            self.extra_body = None

    request = BasicLLMRequest(
        model="qwen-plus",
        openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        openai_api_key="test-key",
        temperature=0.2,
        extra_config={"show_think": False},
    )
    with patch(
        "apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI",
        _FakeChatOpenAI,
    ), patch(
        "apps.opspilot.metis.llm.common.llm_client_factory.SSRFValidator.validate_llm_endpoint",
    ):
        LLMClientFactory._create_openai_client(request, disable_stream=False)

    assert "stream_usage" not in created
    assert created.get("disable_streaming") is False


def test_openai_client_uses_curl_like_user_agent_and_drops_sdk_fingerprint():
    created = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            created.update(kwargs)
            self.extra_body = None
            ua = kwargs["default_headers"]["User-Agent"]
            self.root_client = SimpleNamespace(_custom_headers={"User-Agent": ua})
            self.root_async_client = SimpleNamespace(_custom_headers={"User-Agent": ua})

    request = BasicLLMRequest(
        model="auto",
        openai_api_base="https://route.example/v1",
        openai_api_key="test-key",
        temperature=0.2,
    )
    with patch(
        "apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI",
        _FakeChatOpenAI,
    ), patch(
        "apps.opspilot.metis.llm.common.llm_client_factory.SSRFValidator.validate_llm_endpoint",
    ):
        llm = LLMClientFactory._create_openai_client(request, disable_stream=False)

    assert created["default_headers"]["User-Agent"].startswith("curl/")
    assert llm.root_client._custom_headers["X-Stainless-Lang"] is omit
    assert llm.root_async_client._custom_headers["User-Agent"].startswith("curl/")


def test_isolated_openai_client_uses_curl_like_headers():
    captured = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    request = BasicLLMRequest(
        model="auto",
        openai_api_base="https://route.example/v1",
        openai_api_key="test-key",
    )
    with patch(
        "apps.opspilot.metis.llm.common.llm_client_factory.OpenAI",
        _FakeOpenAI,
    ), patch(
        "apps.opspilot.metis.llm.common.llm_client_factory.SSRFValidator.validate_llm_endpoint",
    ):
        LLMClientFactory._create_isolated_openai_client(request)

    assert captured["default_headers"]["User-Agent"].startswith("curl/")
    assert captured["default_headers"]["X-Stainless-Lang"] is omit
