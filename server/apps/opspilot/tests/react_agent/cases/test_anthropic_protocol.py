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
8. Runtime capability detection for Anthropic vs OpenAI protocols
9. Tool choice normalization coverage for runtime compatibility
"""
import sys
import types
from importlib import util
from pathlib import Path

for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
setattr(_falkordb, "Graph", type("Graph", (), {}))
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
setattr(_falkordb_asyncio, "FalkorDB", type("FalkorDB", (), {}))
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

_django = types.ModuleType("django")
_django_db = types.ModuleType("django.db")
_django_db_models = types.ModuleType("django.db.models")
_django_db_transaction = types.ModuleType("django.db.transaction")


class _Model:
    def __init__(self, *args, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def _field_factory(*args, **kwargs):
    return object()


class _Atomic:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


setattr(_django_db_models, "Model", _Model)
setattr(_django_db_models, "CharField", _field_factory)
setattr(_django_db_models, "BooleanField", _field_factory)
setattr(_django_db_models, "JSONField", _field_factory)
setattr(_django_db_models, "TextField", _field_factory)
setattr(_django_db_models, "ForeignKey", _field_factory)
setattr(_django_db_models, "SET_NULL", object())
setattr(_django_db_models, "CASCADE", object())
setattr(_django_db_models, "__getattr__", lambda name: _field_factory if name.endswith("Field") else object())
setattr(_django_db_transaction, "atomic", lambda: _Atomic())
_real_django_db = sys.modules.get("django.db")
if _real_django_db is not None:
    _real_django_db.models = _django_db_models
    _real_django_db.transaction = _django_db_transaction
setattr(_django_db, "models", _django_db_models)
setattr(_django_db, "transaction", _django_db_transaction)
sys.modules["django.db.models"] = _django_db_models
sys.modules["django.db.transaction"] = _django_db_transaction

_apps_core_mixinx = types.ModuleType("apps.core.mixinx")


class _EncryptMixin:
    pass


setattr(_apps_core_mixinx, "EncryptMixin", _EncryptMixin)
sys.modules["apps.core.mixinx"] = _apps_core_mixinx

_apps_core_maintainer_info = types.ModuleType("apps.core.models.maintainer_info")
setattr(_apps_core_maintainer_info, "MaintainerInfo", type("MaintainerInfo", (), {}))
sys.modules["apps.core.models.maintainer_info"] = _apps_core_maintainer_info

_apps_core_time_info = types.ModuleType("apps.core.models.time_info")
setattr(_apps_core_time_info, "TimeInfo", type("TimeInfo", (), {}))
sys.modules["apps.core.models.time_info"] = _apps_core_time_info

_opspilot_enum = types.ModuleType("apps.opspilot.enum")
setattr(_opspilot_enum, "SkillTypeChoices", type("SkillTypeChoices", (), {"choices": [], "BASIC_TOOL": 0}))
sys.modules["apps.opspilot.enum"] = _opspilot_enum

_langchain_core = types.ModuleType("langchain_core")
_langchain_core_documents = types.ModuleType("langchain_core.documents")
_langchain_core_messages = types.ModuleType("langchain_core.messages")
_langchain_core_language_models = types.ModuleType("langchain_core.language_models")
_langchain_core_language_models_chat_models = types.ModuleType("langchain_core.language_models.chat_models")


class _HumanMessage:
    def __init__(self, content=None, **kwargs):
        self.content = content
        self.type = kwargs.get("type", "user")


class _BaseChatModel:
    pass


setattr(_langchain_core_documents, "Document", dict)
setattr(_langchain_core_messages, "HumanMessage", _HumanMessage)
setattr(_langchain_core_language_models_chat_models, "BaseChatModel", _BaseChatModel)
setattr(_langchain_core_language_models, "chat_models", _langchain_core_language_models_chat_models)
setattr(_langchain_core, "documents", _langchain_core_documents)
setattr(_langchain_core, "messages", _langchain_core_messages)
setattr(_langchain_core, "language_models", _langchain_core_language_models)
sys.modules["langchain_core"] = _langchain_core
sys.modules["langchain_core.documents"] = _langchain_core_documents
sys.modules["langchain_core.messages"] = _langchain_core_messages
sys.modules["langchain_core.language_models"] = _langchain_core_language_models
sys.modules["langchain_core.language_models.chat_models"] = _langchain_core_language_models_chat_models

_langchain_anthropic = types.ModuleType("langchain_anthropic")
setattr(_langchain_anthropic, "ChatAnthropic", type("ChatAnthropic", (), {}))
sys.modules["langchain_anthropic"] = _langchain_anthropic

_langchain_openai = types.ModuleType("langchain_openai")
setattr(_langchain_openai, "ChatOpenAI", type("ChatOpenAI", (), {}))
sys.modules["langchain_openai"] = _langchain_openai

_anthropic = types.ModuleType("anthropic")
setattr(_anthropic, "Anthropic", type("Anthropic", (), {}))
sys.modules["anthropic"] = _anthropic

_openai = types.ModuleType("openai")
setattr(_openai, "OpenAI", type("OpenAI", (), {}))
sys.modules["openai"] = _openai

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest  # noqa: E402
from apps.opspilot.metis.llm.common.anthropic_capabilities import (  # noqa: E402
    AnthropicRuntimeCapabilities,
    build_anthropic_runtime_capabilities,
    normalize_tool_choice_for_capabilities,
)
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory  # noqa: E402

_model_provider_path = Path(__file__).resolve().parents[3] / "models" / "model_provider_mgmt.py"
_model_provider_spec = util.spec_from_file_location("test_model_provider_mgmt", _model_provider_path)
_model_provider_module = util.module_from_spec(_model_provider_spec)
assert _model_provider_spec and _model_provider_spec.loader
_model_provider_spec.loader.exec_module(_model_provider_module)
LLMModel = _model_provider_module.LLMModel
ModelVendor = _model_provider_module.ModelVendor

_opspilot_models_stub = types.ModuleType("apps.opspilot.models")
_opspilot_models_stub.LLMModel = LLMModel
_opspilot_models_stub.ModelVendor = ModelVendor
_opspilot_models_stub.EmbedProvider = _model_provider_module.EmbedProvider
_opspilot_models_stub.RerankProvider = _model_provider_module.RerankProvider
_opspilot_models_stub.OCRProvider = _model_provider_module.OCRProvider
sys.modules["apps.opspilot.models"] = _opspilot_models_stub

_model_vendor_sync_path = Path(__file__).resolve().parents[3] / "services" / "model_vendor_sync_service.py"
_model_vendor_sync_spec = util.spec_from_file_location("test_model_vendor_sync_service", _model_vendor_sync_path)
_model_vendor_sync_module = util.module_from_spec(_model_vendor_sync_spec)
assert _model_vendor_sync_spec and _model_vendor_sync_spec.loader
_model_vendor_sync_spec.loader.exec_module(_model_vendor_sync_module)
ModelVendorSyncService = _model_vendor_sync_module.ModelVendorSyncService

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
        assert caps.supports_direct_messages_api is False
        assert caps.requires_normalized_base_url is False

    def test_deepseek_anthropic_vendor_uses_adapter(self):
        caps = build_anthropic_runtime_capabilities(
            vendor_type="deepseek",
            protocol_type="anthropic",
            model="deepseek-v4-flash",
        )
        assert caps.use_native_anthropic_sdk is False
        assert caps.use_anthropic_compatible_adapter is True
        assert caps.thinking_requires_auto_tool_choice is True
        assert caps.supports_direct_messages_api is True
        assert caps.requires_normalized_base_url is True

    def test_unknown_anthropic_vendor_uses_compatible_fallback(self):
        caps = build_anthropic_runtime_capabilities(
            vendor_type="unknown-vendor",
            protocol_type="anthropic",
            model="claude-3-haiku-20240307",
        )
        assert caps.use_native_anthropic_sdk is False
        assert caps.use_anthropic_compatible_adapter is True
        assert caps.supports_direct_messages_api is True
        assert caps.requires_normalized_base_url is True

    def test_non_anthropic_protocol_returns_default_capabilities(self):
        caps = build_anthropic_runtime_capabilities(
            vendor_type="deepseek",
            protocol_type="openai",
            model="deepseek-v4-flash",
        )
        assert caps.use_native_anthropic_sdk is False
        assert caps.use_anthropic_compatible_adapter is False
        assert caps.supports_direct_messages_api is False
        assert caps.requires_normalized_base_url is False

    def test_tool_choice_any_downgrades_to_auto_when_thinking_required(self):
        caps = AnthropicRuntimeCapabilities(thinking_requires_auto_tool_choice=True)
        assert normalize_tool_choice_for_capabilities("any", caps) == "auto"

    def test_tool_choice_required_downgrades_to_auto_when_thinking_required(self):
        caps = AnthropicRuntimeCapabilities(thinking_requires_auto_tool_choice=True)
        assert normalize_tool_choice_for_capabilities("required", caps) == "auto"

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

    def _make_model(self, vendor_type=None, protocol_type="openai"):
        model = LLMModel(name="test-model")
        model.vendor_id = None
        if vendor_type is None:
            return model

        model.vendor = ModelVendor(
            name="test-vendor",
            vendor_type=vendor_type,
            protocol_type=protocol_type,
        )
        model.vendor_id = 1
        return model

    def test_anthropic_vendor_gives_anthropic_protocol(self):
        assert self._make_model("anthropic", "anthropic").protocol_type == "anthropic"

    def test_other_vendor_with_anthropic_protocol(self):
        assert self._make_model("other", "anthropic").protocol_type == "anthropic"

    def test_openai_vendor_gives_openai_protocol(self):
        assert self._make_model("openai", "openai").protocol_type == "openai"

    def test_no_vendor_defaults_to_openai(self):
        assert self._make_model().protocol_type == "openai"
