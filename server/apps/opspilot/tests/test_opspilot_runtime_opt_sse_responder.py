"""OpsPilot runtime optimization: sse_responder accumulation helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


class TestSseStreamResponseWrapper:
    def test_create_sse_stream_response_delegates_to_stream_common(self, monkeypatch):
        from apps.opspilot.utils.chat_flow_utils.engine.sse_responder import SSEResponderMixin

        sentinel = object()
        monkeypatch.setattr(
            "apps.opspilot.utils.stream_common.make_sse_response",
            lambda stream, extra_headers=None: sentinel,
        )

        class _Host(SSEResponderMixin):
            execution_id = "exec-1"

        def _stream():
            yield "data: ok\n\n"

        assert _Host()._create_sse_stream_response(_stream) is sentinel

    def test_create_error_response_keeps_legacy_envelope(self):
        import asyncio

        from apps.opspilot.utils.chat_flow_utils.engine.sse_responder import SSEResponderMixin

        class _Host(SSEResponderMixin):
            execution_id = "exec-2"

        response = _Host()._create_error_response("bad")

        async def _collect():
            chunks = []
            async for chunk in response.streaming_content:
                chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
            return b"".join(chunks)

        body = asyncio.run(_collect())
        assert b"bad" in body
        assert b"[DONE]" in body
        assert response["Content-Type"] == "text/event-stream"
