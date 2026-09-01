"""OpsPilot runtime optimization PR3: stream_common SSE helpers."""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.unit


class TestMakeSseResponse:
    def test_make_sse_response_sets_standard_headers(self):
        from apps.opspilot.utils.stream_common import make_sse_response

        async def _gen():
            yield b"data: ok\n\n"

        response = make_sse_response(lambda: _gen())
        assert response["Content-Type"] == "text/event-stream"
        assert response["Cache-Control"] == "no-cache, no-store, must-revalidate"
        assert response["X-Accel-Buffering"] == "no"
        assert response["Access-Control-Allow-Origin"] == "*"

    def test_make_sse_error_response_emits_done(self):
        from apps.opspilot.utils.stream_common import make_sse_error_response

        response = make_sse_error_response("boom")

        async def _collect():
            chunks = []
            async for chunk in response.streaming_content:
                chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
            return b"".join(chunks)

        body = asyncio.run(_collect())
        assert b"boom" in body
        assert b"[DONE]" in body