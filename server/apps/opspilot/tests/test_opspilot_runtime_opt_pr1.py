"""OpsPilot runtime optimization PR1: cleanup + SSE accumulation filter."""

from __future__ import annotations

import importlib

import pytest

from apps.opspilot.utils.chat_flow_utils.engine.sse_responder import (
    parse_sse_chunk_for_accumulation,
    should_accumulate_sse_payload,
)


class TestShouldAccumulateSsePayload:
    def test_text_message_content_is_accumulated(self):
        assert should_accumulate_sse_payload({"type": "TEXT_MESSAGE_CONTENT", "delta": "hi"}) is True

    def test_tool_call_start_is_skipped(self):
        assert should_accumulate_sse_payload({"type": "TOOL_CALL_START", "toolCallId": "1"}) is False

    def test_browser_step_custom_is_accumulated(self):
        payload = {"type": "CUSTOM", "name": "browser_step_progress", "value": {"step_number": 1}}
        assert should_accumulate_sse_payload(payload) is True

    def test_openai_chunk_is_accumulated(self):
        payload = {
            "object": "chat.completion.chunk",
            "choices": [{"delta": {"content": "x"}, "index": 0}],
        }
        assert should_accumulate_sse_payload(payload) is True

    def test_non_dict_is_skipped(self):
        assert should_accumulate_sse_payload([]) is False


class TestParseSseChunkForAccumulation:
    def test_parses_relevant_chunk(self):
        chunk = 'data: {"type": "TEXT_MESSAGE_CONTENT", "delta": "hello"}\n\n'
        assert parse_sse_chunk_for_accumulation(chunk) == {"type": "TEXT_MESSAGE_CONTENT", "delta": "hello"}

    def test_skips_tool_event_without_returning(self):
        chunk = 'data: {"type": "TOOL_CALL_ARGS", "delta": "{}"}\n\n'
        assert parse_sse_chunk_for_accumulation(chunk) is None

    def test_skips_done_marker(self):
        assert parse_sse_chunk_for_accumulation("data: [DONE]\n\n") is None

    def test_skips_non_data_prefix(self):
        assert parse_sse_chunk_for_accumulation(": keepalive\n\n") is None


class TestDeepAgentNoDebugResidual:
    def test_deep_agent_module_has_no_debug_dg(self):
        from pathlib import Path

        from apps.opspilot.metis.llm.agent import deep_agent as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "DEBUG_DG" not in source


class TestToolsLoaderLogger:
    def test_tools_loader_uses_opspilot_logger(self):
        from apps.opspilot.metis.llm.tools import tools_loader

        importlib.reload(tools_loader)
        assert tools_loader.logger.name == "opspilot"
