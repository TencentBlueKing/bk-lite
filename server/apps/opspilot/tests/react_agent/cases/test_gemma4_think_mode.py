"""
Gemma-4 Think Mode Support Tests.

Covers the two changes introduced to support Gemma-4's thinking/reasoning mode:

1. LLMClientFactory — request-side: Gemma models receive
   ``extra_body.chat_template_kwargs.enable_thinking`` reflecting show_think.

2. BasicGraph._handle_chat_model_stream_content — response-side: when a
   streaming chunk carries reasoning content in
   ``additional_kwargs["reasoning_content"]`` (normalised by lc_patches.py),
   the graph emits ThinkingTextMessageContent events so the frontend can
   display them.

Both behaviours are tested in isolation via lightweight stubs so the tests
run without a live database or LLM connection.
"""

import sys
import types
import uuid
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

# ---------------------------------------------------------------------------
# Minimal module stubs required for importing llm_client_factory without a
# full Django / LangChain environment.
# ---------------------------------------------------------------------------

for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
setattr(_falkordb, "Graph", type("Graph", (), {}))
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
setattr(_falkordb_asyncio, "FalkorDB", type("FalkorDB", (), {}))
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest  # noqa: E402
from apps.opspilot.metis.llm.common import llm_client_factory as llm_client_factory_module  # noqa: E402
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory  # noqa: E402

# ---------------------------------------------------------------------------
# Shared SSRF bypass fixture (avoids network validation in tests)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def bypass_ssrf_validation():
    with patch.object(llm_client_factory_module.SSRFValidator, "validate_llm_endpoint"):
        yield


# ===========================================================================
# Part 1 – LLMClientFactory: Gemma request-side think params
# ===========================================================================


class TestGemmaOpenAIClientThinkMode:
    """_create_openai_client sets chat_template_kwargs.enable_thinking for Gemma models."""

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI")
    def test_gemma_show_think_true_sets_enable_thinking_true(self, mock_cls):
        """show_think=True → extra_body.chat_template_kwargs.enable_thinking == True."""
        mock_llm = MagicMock()
        mock_llm.extra_body = None
        mock_cls.return_value = mock_llm

        request = BasicLLMRequest(
            model="google/gemma-4-31B-it",
            openai_api_key="sk-test",
            openai_api_base="http://localhost:8000/v1",
            extra_config={"show_think": True},
        )
        LLMClientFactory._create_openai_client(request, disable_stream=False)

        assert mock_llm.extra_body["chat_template_kwargs"] == {"enable_thinking": True}

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI")
    def test_gemma_show_think_false_sets_enable_thinking_false(self, mock_cls):
        """show_think=False → extra_body.chat_template_kwargs.enable_thinking == False."""
        mock_llm = MagicMock()
        mock_llm.extra_body = None
        mock_cls.return_value = mock_llm

        request = BasicLLMRequest(
            model="google/gemma-4-12B-it",
            openai_api_key="sk-test",
            openai_api_base="http://localhost:8000/v1",
            extra_config={"show_think": False},
        )
        LLMClientFactory._create_openai_client(request, disable_stream=False)

        assert mock_llm.extra_body["chat_template_kwargs"] == {"enable_thinking": False}

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI")
    def test_gemma_default_show_think_enables_thinking(self, mock_cls):
        """show_think defaults to True when absent → thinking enabled."""
        mock_llm = MagicMock()
        mock_llm.extra_body = None
        mock_cls.return_value = mock_llm

        request = BasicLLMRequest(
            model="gemma-4-e2b-it",
            openai_api_key="sk-test",
            extra_config={},  # no show_think key
        )
        LLMClientFactory._create_openai_client(request, disable_stream=False)

        assert mock_llm.extra_body["chat_template_kwargs"]["enable_thinking"] is True

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI")
    def test_non_gemma_model_does_not_set_chat_template_kwargs(self, mock_cls):
        """Non-Gemma models must NOT receive chat_template_kwargs."""
        mock_llm = MagicMock()
        mock_llm.extra_body = None
        mock_cls.return_value = mock_llm

        request = BasicLLMRequest(
            model="gpt-4o",
            openai_api_key="sk-test",
            extra_config={"show_think": True},
        )
        LLMClientFactory._create_openai_client(request, disable_stream=False)

        assert "chat_template_kwargs" not in (mock_llm.extra_body or {})

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI")
    def test_qwen_model_still_uses_enable_thinking_not_chat_template_kwargs(self, mock_cls):
        """Qwen must keep using extra_body.enable_thinking (not chat_template_kwargs)."""
        mock_llm = MagicMock()
        mock_llm.extra_body = None
        mock_cls.return_value = mock_llm

        request = BasicLLMRequest(
            model="qwen3-235b-a22b",
            openai_api_key="sk-test",
            extra_config={"show_think": True},
        )
        LLMClientFactory._create_openai_client(request, disable_stream=False)

        assert mock_llm.extra_body.get("enable_thinking") is True
        assert "chat_template_kwargs" not in mock_llm.extra_body


class TestGemmaIsolatedCallDisablesThinking:
    """_invoke_isolated_openai passes chat_template_kwargs.enable_thinking=False for Gemma."""

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.OpenAI")
    def test_gemma_isolated_call_disables_thinking(self, mock_openai_cls):
        """Internal (isolated) calls must disable Gemma thinking to avoid extra tokens."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        request = BasicLLMRequest(
            model="google/gemma-4-31B-it",
            openai_api_key="sk-test",
            openai_api_base="http://localhost:8000/v1",
        )
        LLMClientFactory._invoke_isolated_openai(request, [HumanMessage(content="hi")])

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.OpenAI")
    def test_non_gemma_isolated_call_does_not_set_chat_template_kwargs(self, mock_openai_cls):
        """Non-Gemma isolated calls must not receive chat_template_kwargs."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        request = BasicLLMRequest(
            model="gpt-4o",
            openai_api_key="sk-test",
            openai_api_base="https://api.openai.com",
        )
        LLMClientFactory._invoke_isolated_openai(request, [HumanMessage(content="hi")])

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert "extra_body" not in call_kwargs or "chat_template_kwargs" not in (call_kwargs.get("extra_body") or {})


# ===========================================================================
# Part 2 – BasicGraph: reasoning_content in additional_kwargs → THINKING events
# ===========================================================================


class _FakeChunk:
    """Minimal stand-in for a LangChain AIMessageChunk."""

    def __init__(self, content: str = "", reasoning_content: str = ""):
        self.content = content
        self.additional_kwargs: dict = {}
        if reasoning_content:
            self.additional_kwargs["reasoning_content"] = reasoning_content

    def __bool__(self):
        return True


class _ConcreteGraph:
    """Minimal concrete subclass of BasicGraph for testing helper methods."""

    # Pull just the methods we want to test, without the ABC machinery.
    from apps.opspilot.metis.llm.chain.graph import BasicGraph as _Base

    _extract_content_from_chunk = _Base._extract_content_from_chunk
    _handle_chat_model_stream_content = _Base._handle_chat_model_stream_content


def _make_encoder():
    """Return a minimal encoder that produces JSON-serialisable strings."""
    from ag_ui.encoder import EventEncoder

    return EventEncoder()


class TestGraphReasoningContentFromAdditionalKwargs:
    """_handle_chat_model_stream_content emits THINKING events from additional_kwargs."""

    def _call(self, chunk, show_think: bool):
        from ag_ui.encoder import EventEncoder

        graph = _ConcreteGraph()
        encoder = EventEncoder()
        run_id = str(uuid.uuid4())
        events, _, _, thinking_started = graph._handle_chat_model_stream_content(
            chunk=chunk,
            encoder=encoder,
            run_id=run_id,
            current_message_id=None,
            message_started=False,
            show_think=show_think,
            thinking_started=False,
        )
        return events, thinking_started

    def test_reasoning_content_produces_thinking_events_when_show_think_true(self):
        """reasoning_content in additional_kwargs → ThinkingTextMessageContent event emitted."""
        chunk = _FakeChunk(content="The answer is 42.", reasoning_content="Let me think step by step...")

        events, thinking_started = self._call(chunk, show_think=True)

        event_types = [e for e in events if "THINKING_TEXT_MESSAGE" in e]
        assert len(event_types) >= 1, "Expected at least one THINKING_TEXT_MESSAGE event"
        assert thinking_started is True

    def test_reasoning_content_suppressed_when_show_think_false(self):
        """When show_think=False, reasoning_content must NOT produce THINKING events."""
        chunk = _FakeChunk(content="The answer is 42.", reasoning_content="Let me think step by step...")

        events, thinking_started = self._call(chunk, show_think=False)

        thinking_events = [e for e in events if "THINKING_TEXT_MESSAGE" in e]
        assert thinking_events == [], "THINKING events must not be emitted when show_think=False"
        assert thinking_started is False

    def test_reasoning_only_chunk_emits_thinking_event(self):
        """A chunk with only reasoning_content (empty content) still emits THINKING event."""
        chunk = _FakeChunk(content="", reasoning_content="Still thinking...")

        events, thinking_started = self._call(chunk, show_think=True)

        thinking_events = [e for e in events if "THINKING_TEXT_MESSAGE" in e]
        assert len(thinking_events) >= 1
        assert thinking_started is True

    def test_empty_chunk_produces_no_events(self):
        """A completely empty chunk (no content, no reasoning) must produce nothing."""
        chunk = _FakeChunk(content="", reasoning_content="")

        events, thinking_started = self._call(chunk, show_think=True)

        assert events == []
        assert thinking_started is False

    def test_reasoning_content_does_not_override_anthropic_thinking_blocks(self):
        """If thinking_delta is already extracted from content blocks, additional_kwargs is skipped."""

        class _AnthropicChunk:
            content = [{"type": "thinking", "thinking": "from-block"}, {"type": "text", "text": "answer"}]
            additional_kwargs = {"reasoning_content": "from-additional-kwargs"}

            def __bool__(self):
                return True

        graph = _ConcreteGraph()
        from ag_ui.encoder import EventEncoder

        encoder = EventEncoder()
        run_id = str(uuid.uuid4())

        events, _, _, _ = graph._handle_chat_model_stream_content(
            chunk=_AnthropicChunk(),
            encoder=encoder,
            run_id=run_id,
            current_message_id=None,
            message_started=False,
            show_think=True,
            thinking_started=False,
        )

        # Should contain thinking content from the block (not duplicated from additional_kwargs)
        thinking_events = [e for e in events if "THINKING_TEXT_MESSAGE_CONTENT" in e]
        assert len(thinking_events) == 1
        assert "from-block" in thinking_events[0]
        assert "from-additional-kwargs" not in "".join(thinking_events)

    def test_gemma_multi_chunk_thinking_started_tracks_state(self):
        """thinking_started flag is returned True after first reasoning chunk
        so caller can emit ThinkingTextMessageEnd at the right time."""
        chunk1 = _FakeChunk(content="", reasoning_content="First thought")
        chunk2 = _FakeChunk(content="Final answer", reasoning_content="")

        _, thinking_started_after_1 = self._call(chunk1, show_think=True)
        assert thinking_started_after_1 is True

        # Second chunk (no reasoning) should not affect thinking_started flag
        _, thinking_started_after_2 = self._call(chunk2, show_think=True)
        assert thinking_started_after_2 is False
