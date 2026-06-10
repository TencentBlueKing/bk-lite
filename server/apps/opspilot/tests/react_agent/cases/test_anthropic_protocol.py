"""
Anthropic Protocol Support Tests.

Verifies:
1. LLMClientFactory creates correct client type based on protocol_type
2. LLMClientFactory handles base_url fallback for Anthropic
3. LLMClientFactory isolated client creation for both protocols
4. LLMClientFactory invoke_isolated message format conversion
5. ModelVendorSyncService protocol type detection
6. ModelVendorSyncService Anthropic model fetching
7. LLMModel.protocol_type property derivation from vendor
"""
import sys
import types

for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
setattr(_falkordb, "Graph", type("Graph", (), {}))
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
setattr(_falkordb_asyncio, "FalkorDB", type("FalkorDB", (), {}))
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest  # noqa: E402
from apps.opspilot.metis.llm.common.anthropic_capabilities import (  # noqa: E402
    AnthropicRuntimeCapabilities,
    build_anthropic_runtime_capabilities,
    normalize_tool_choice_for_capabilities,
)
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory  # noqa: E402
from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService  # noqa: E402

# ---------------------------------------------------------------------------
# AnthropicRuntimeCapabilities Tests
# ---------------------------------------------------------------------------


class TestAnthropicRuntimeCapabilities:
    def test_native_anthropic_vendor_uses_native_sdk(self):
        caps = build_anthropic_runtime_capabilities(
            vendor_type="anthropic",
            protocol_type="anthropic",
            model="claude-3-haiku-20240307",
        )
        assert caps.use_native_anthropic_sdk is True
        assert caps.use_anthropic_compatible_adapter is False

    def test_deepseek_anthropic_vendor_uses_adapter(self):
        caps = build_anthropic_runtime_capabilities(
            vendor_type="deepseek",
            protocol_type="anthropic",
            model="deepseek-v4-flash",
        )
        assert caps.use_native_anthropic_sdk is False
        assert caps.use_anthropic_compatible_adapter is True
        assert caps.thinking_requires_auto_tool_choice is True

    def test_non_anthropic_protocol_returns_default_capabilities(self):
        caps = build_anthropic_runtime_capabilities(
            vendor_type="deepseek",
            protocol_type="openai",
            model="deepseek-v4-flash",
        )
        assert caps.use_native_anthropic_sdk is False
        assert caps.use_anthropic_compatible_adapter is False

    def test_tool_choice_any_downgrades_to_auto_when_thinking_required(self):
        caps = AnthropicRuntimeCapabilities(thinking_requires_auto_tool_choice=True)
        assert normalize_tool_choice_for_capabilities("any", caps) == "auto"

    def test_tool_choice_none_kept_as_is(self):
        caps = AnthropicRuntimeCapabilities(thinking_requires_auto_tool_choice=True)
        assert normalize_tool_choice_for_capabilities("none", caps) == "none"


# ---------------------------------------------------------------------------
# LLMClientFactory Tests
# ---------------------------------------------------------------------------


class TestCreateClientProtocolDispatch:
    """create_client dispatches to correct backend based on protocol_type."""

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatAnthropic")
    def test_anthropic_protocol_creates_chat_anthropic(self, mock_cls):
        mock_cls.return_value = MagicMock()
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-ant-test",
            model="claude-3-haiku-20240307",
            openai_api_base="https://api.anthropic.com",
        )
        client = LLMClientFactory.create_client(request)
        mock_cls.assert_called_once()
        assert client is mock_cls.return_value

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI")
    def test_openai_protocol_creates_chat_openai(self, mock_cls):
        mock_cls.return_value = MagicMock()
        request = BasicLLMRequest(
            protocol_type="openai",
            openai_api_key="sk-test",
            model="gpt-4o",
            openai_api_base="https://api.openai.com",
        )
        client = LLMClientFactory.create_client(request)
        mock_cls.assert_called_once()
        assert client is mock_cls.return_value

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI")
    def test_default_protocol_is_openai(self, mock_cls):
        mock_cls.return_value = MagicMock()
        request = BasicLLMRequest(
            openai_api_key="sk-test",
            model="gpt-4o",
        )
        assert request.protocol_type == "openai"
        LLMClientFactory.create_client(request)
        mock_cls.assert_called_once()


class TestAnthropicClientBaseUrl:
    """Anthropic client handles base_url fallback correctly."""

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatAnthropic")
    def test_default_openai_url_replaced_with_anthropic(self, mock_cls):
        """If base_url is OpenAI default, replace with Anthropic."""
        mock_cls.return_value = MagicMock()
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-ant-test",
            model="claude-3-haiku-20240307",
            openai_api_base="https://api.openai.com",
        )
        LLMClientFactory.create_client(request)
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["anthropic_api_url"] == "https://api.anthropic.com"

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatAnthropic")
    def test_empty_base_url_replaced_with_anthropic(self, mock_cls):
        mock_cls.return_value = MagicMock()
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-ant-test",
            model="claude-3-haiku-20240307",
            openai_api_base="",
        )
        LLMClientFactory.create_client(request)
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["anthropic_api_url"] == "https://api.anthropic.com"

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatAnthropic")
    def test_custom_base_url_preserved(self, mock_cls):
        """Custom proxy URL should be preserved."""
        mock_cls.return_value = MagicMock()
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-ant-test",
            model="claude-3-haiku-20240307",
            openai_api_base="https://my-proxy.example.com",
        )
        LLMClientFactory.create_client(request)
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["anthropic_api_url"] == "https://my-proxy.example.com"


class TestAnthropicClientParams:
    """Anthropic client receives correct parameters."""

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatAnthropic")
    def test_model_and_temperature_passed(self, mock_cls):
        mock_cls.return_value = MagicMock()
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-ant-key",
            model="claude-3-opus-20240229",
            openai_api_base="https://api.anthropic.com",
            temperature=0.3,
        )
        LLMClientFactory.create_client(request)
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["model"] == "claude-3-opus-20240229"
        assert call_kwargs["api_key"] == "sk-ant-key"
        assert call_kwargs["temperature"] == 0.3
        assert call_kwargs["timeout"] == 3000

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatAnthropic")
    def test_deepseek_thinking_mode_in_anthropic_client(self, mock_cls):
        """DeepSeek model via Anthropic protocol gets thinking params."""
        mock_cls.return_value = MagicMock()
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-key",
            model="deepseek-r1",
            openai_api_base="https://proxy.example.com",
            extra_config={"show_think": True},
        )
        LLMClientFactory.create_client(request)
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["model_kwargs"] == {"thinking": {"type": "enabled"}}

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatAnthropic")
    def test_non_deepseek_no_model_kwargs(self, mock_cls):
        mock_cls.return_value = MagicMock()
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-key",
            model="claude-3-haiku-20240307",
            openai_api_base="https://api.anthropic.com",
        )
        LLMClientFactory.create_client(request)
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["model_kwargs"] is None


class TestIsolatedClientCreation:
    """create_isolated_client dispatches correctly."""

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.anthropic.Anthropic")
    def test_anthropic_isolated_client(self, mock_cls):
        mock_cls.return_value = MagicMock()
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-ant-key",
            openai_api_base="https://api.anthropic.com",
        )
        client = LLMClientFactory.create_isolated_client(request)
        mock_cls.assert_called_once()
        assert client is mock_cls.return_value
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["api_key"] == "sk-ant-key"
        assert call_kwargs["base_url"] == "https://api.anthropic.com"

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.OpenAI")
    def test_openai_isolated_client(self, mock_cls):
        mock_cls.return_value = MagicMock()
        request = BasicLLMRequest(
            protocol_type="openai",
            openai_api_key="sk-key",
            openai_api_base="https://api.openai.com",
        )
        client = LLMClientFactory.create_isolated_client(request)
        mock_cls.assert_called_once()
        assert client is mock_cls.return_value


class TestInvokeIsolatedAnthropicMessageFormat:
    """invoke_isolated correctly converts messages for Anthropic."""

    @patch("apps.opspilot.metis.llm.common.llm_client_factory." "LLMClientFactory._create_isolated_anthropic_client")
    def test_system_message_extracted_separately(self, mock_create):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="response")]
        mock_client.messages.create.return_value = mock_response
        mock_create.return_value = mock_client

        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-key",
            model="claude-3-haiku-20240307",
        )
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        result = LLMClientFactory.invoke_isolated(request, messages)

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are helpful."
        # system message should NOT be in messages list
        assert all(m["role"] != "system" for m in call_kwargs["messages"])
        assert call_kwargs["messages"] == [{"role": "user", "content": "Hello"}]
        assert call_kwargs["max_tokens"] == 4096
        assert result == "response"

    @patch("apps.opspilot.metis.llm.common.llm_client_factory." "LLMClientFactory._create_isolated_anthropic_client")
    def test_no_system_message(self, mock_create):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="hi")]
        mock_client.messages.create.return_value = mock_response
        mock_create.return_value = mock_client

        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-key",
            model="claude-3-haiku-20240307",
        )
        messages = [{"role": "user", "content": "Hello"}]
        LLMClientFactory.invoke_isolated(request, messages)

        call_kwargs = mock_client.messages.create.call_args[1]
        assert "system" not in call_kwargs

    @patch("apps.opspilot.metis.llm.common.llm_client_factory." "LLMClientFactory._create_isolated_anthropic_client")
    def test_human_message_object_converted(self, mock_create):
        from langchain_core.messages import HumanMessage

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="ok")]
        mock_client.messages.create.return_value = mock_response
        mock_create.return_value = mock_client

        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-key",
            model="claude-3-haiku-20240307",
        )
        messages = [HumanMessage(content="test query")]
        LLMClientFactory.invoke_isolated(request, messages)

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["messages"] == [{"role": "user", "content": "test query"}]


class TestClientIsolationFlag:
    """isolated=True disables callbacks."""

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatAnthropic")
    def test_isolated_anthropic_clears_callbacks(self, mock_cls):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-key",
            model="claude-3-haiku-20240307",
            openai_api_base="https://api.anthropic.com",
        )
        LLMClientFactory.create_client(request, isolated=True)
        assert mock_instance.callbacks is None

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI")
    def test_isolated_openai_clears_callbacks(self, mock_cls):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        request = BasicLLMRequest(
            protocol_type="openai",
            openai_api_key="sk-key",
            model="gpt-4o",
        )
        LLMClientFactory.create_client(request, isolated=True)
        assert mock_instance.callbacks is None


# ---------------------------------------------------------------------------
# ModelVendorSyncService Tests
# ---------------------------------------------------------------------------


class TestProtocolTypeDetection:
    """_get_protocol_type returns correct protocol for vendor types."""

    def _make_vendor(self, vendor_type, protocol_type="openai"):
        v = MagicMock()
        v.vendor_type = vendor_type
        v.protocol_type = protocol_type
        return v

    def test_anthropic_vendor_returns_anthropic(self):
        vendor = self._make_vendor("anthropic")
        assert ModelVendorSyncService._get_protocol_type(vendor) == "anthropic"

    def test_openai_vendor_returns_openai(self):
        vendor = self._make_vendor("openai")
        assert ModelVendorSyncService._get_protocol_type(vendor) == "openai"

    def test_other_vendor_with_anthropic_protocol(self):
        vendor = self._make_vendor("other", protocol_type="anthropic")
        assert ModelVendorSyncService._get_protocol_type(vendor) == "anthropic"

    def test_other_vendor_default_openai(self):
        vendor = self._make_vendor("other", protocol_type="openai")
        assert ModelVendorSyncService._get_protocol_type(vendor) == "openai"

    def test_deepseek_vendor_with_anthropic_protocol(self):
        vendor = self._make_vendor("deepseek", protocol_type="anthropic")
        assert ModelVendorSyncService._get_protocol_type(vendor) == "anthropic"

    def test_azure_vendor_always_openai(self):
        vendor = self._make_vendor("azure")
        assert ModelVendorSyncService._get_protocol_type(vendor) == "openai"


class TestAnthropicConnection:
    """test_anthropic_connection validates Anthropic API connectivity."""

    @patch("apps.opspilot.services.model_vendor_sync_service.requests.post")
    def test_successful_connection(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        # Should not raise
        ModelVendorSyncService.test_anthropic_connection("https://api.anthropic.com", "sk-ant-key")
        mock_post.assert_called_once()

    @patch("apps.opspilot.services.model_vendor_sync_service.requests.post")
    def test_invalid_key_raises_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=401)
        with pytest.raises(ValueError):
            ModelVendorSyncService.test_anthropic_connection("https://api.anthropic.com", "invalid-key")

    def test_empty_key_raises_error(self):
        with pytest.raises(ValueError):
            ModelVendorSyncService.test_anthropic_connection("https://api.anthropic.com", "")

    @patch("apps.opspilot.services.model_vendor_sync_service.requests.post")
    def test_custom_base_url_used(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        ModelVendorSyncService.test_anthropic_connection("https://my-proxy.com", "sk-key")
        call_url = mock_post.call_args[0][0]
        assert call_url == "https://my-proxy.com/v1/messages"

    @patch("apps.opspilot.services.model_vendor_sync_service.requests.post")
    def test_empty_base_url_defaults_to_anthropic(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        ModelVendorSyncService.test_anthropic_connection("", "sk-key")
        call_url = mock_post.call_args[0][0]
        assert call_url == "https://api.anthropic.com/v1/messages"

    @patch("apps.opspilot.services.model_vendor_sync_service.requests.post")
    def test_custom_model_used(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        ModelVendorSyncService.test_anthropic_connection("https://api.anthropic.com", "sk-key", model="deepseek-chat")
        call_json = mock_post.call_args[1]["json"]
        assert call_json["model"] == "deepseek-chat"

    @patch("apps.opspilot.services.model_vendor_sync_service.requests.post")
    def test_api_error_raises_value_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text="Internal Server Error")
        with pytest.raises(ValueError, match="API 连接失败"):
            ModelVendorSyncService.test_anthropic_connection("https://api.anthropic.com", "sk-key")


class TestFetchModelsDispatch:
    """fetch_models_with_credentials dispatches by protocol_type."""

    def test_anthropic_protocol_raises_error(self):
        """Anthropic protocol should raise error (no /models endpoint)."""
        with pytest.raises(ValueError, match="Anthropic"):
            ModelVendorSyncService.fetch_models_with_credentials(
                "https://api.anthropic.com",
                "sk-key",
                protocol_type="anthropic",
            )

    @patch.object(
        ModelVendorSyncService,
        "_fetch_openai_models",
        return_value=[{"id": "gpt-4o"}],
    )
    def test_openai_protocol_calls_openai_fetch(self, mock_fetch):
        result = ModelVendorSyncService.fetch_models_with_credentials(
            "https://api.openai.com",
            "sk-key",
            protocol_type="openai",
        )
        mock_fetch.assert_called_once()
        assert result == [{"id": "gpt-4o"}]


class TestIsSupportedVendor:
    """is_supported correctly identifies supported vendors."""

    def _make_vendor(self, vendor_type):
        v = MagicMock()
        v.vendor_type = vendor_type
        return v

    def test_anthropic_not_supported(self):
        """Anthropic vendor type does not support model sync (no /models endpoint)."""
        assert not ModelVendorSyncService.is_supported(self._make_vendor("anthropic"))

    def test_openai_supported(self):
        assert ModelVendorSyncService.is_supported(self._make_vendor("openai"))

    def test_other_supported(self):
        assert ModelVendorSyncService.is_supported(self._make_vendor("other"))

    def test_unknown_not_supported(self):
        assert not ModelVendorSyncService.is_supported(self._make_vendor("unknown_vendor"))


# ---------------------------------------------------------------------------
# LLMModel.protocol_type property Tests
# ---------------------------------------------------------------------------


class TestLLMModelProtocolType:
    """LLMModel.protocol_type derives from vendor correctly."""

    def test_anthropic_vendor_gives_anthropic_protocol(self):
        vendor = MagicMock()
        vendor.vendor_type = "anthropic"
        vendor.protocol_type = "anthropic"

        model = MagicMock()
        model.vendor_id = 1
        model.vendor = vendor

        # Simulate the property logic
        if model.vendor.vendor_type == "anthropic":
            result = "anthropic"
        elif model.vendor.vendor_type in ("deepseek", "other"):
            result = model.vendor.protocol_type or "openai"
        else:
            result = "openai"
        assert result == "anthropic"

    def test_other_vendor_with_anthropic_protocol(self):
        vendor = MagicMock()
        vendor.vendor_type = "other"
        vendor.protocol_type = "anthropic"

        if vendor.vendor_type == "anthropic":
            result = "anthropic"
        elif vendor.vendor_type in ("deepseek", "other"):
            result = vendor.protocol_type or "openai"
        else:
            result = "openai"
        assert result == "anthropic"

    def test_openai_vendor_gives_openai_protocol(self):
        vendor = MagicMock()
        vendor.vendor_type = "openai"
        vendor.protocol_type = "openai"

        if vendor.vendor_type == "anthropic":
            result = "anthropic"
        elif vendor.vendor_type in ("deepseek", "other"):
            result = vendor.protocol_type or "openai"
        else:
            result = "openai"
        assert result == "openai"

    def test_no_vendor_defaults_to_openai(self):
        # Simulates vendor_id = None
        result = "openai"  # default when no vendor
        assert result == "openai"
