# server/apps/job_mgmt/tests/test_execution_stream_service_async.py
import asyncio
import json
from unittest.mock import patch

import pytest

from apps.job_mgmt.services import execution_stream_service as svc

pytestmark = pytest.mark.unit


def _collect(async_gen):
    async def _run():
        return [chunk async for chunk in async_gen]
    return asyncio.run(_run())


def _payloads(chunks):
    return [json.loads(c[len("data: "):].strip()) for c in chunks if c.startswith("data: ") and "[DONE]" not in c]


def test_publish_done_sentinel_publishes_expected_payload():
    with patch.object(svc, "publish_raw_sync") as mock_pub:
        svc.publish_done_sentinel(7, "node-x", "success")
    mock_pub.assert_called_once()
    subject, payload = mock_pub.call_args.args
    assert subject == "job.stream.7.node-x"
    assert payload == {"execution_id": "7", "target_key": "node-x", "type": "done", "status": "success"}


def test_snapshot_sse_from_results_emits_stdout_stderr_then_done():
    results = [
        {"target_key": "a", "stdout": "out-a", "stderr": ""},
        {"target_key": "b", "stdout": "out-b", "stderr": "err-b"},
    ]
    chunks = _collect(svc.snapshot_sse_from_results(results))
    assert chunks[-1] == "data: [DONE]\n\n"
    payloads = _payloads(chunks)
    # a: 仅 stdout；b: stdout + stderr
    assert {"target_key": "a", "stream": "stdout", "line": "out-a", "type": "history"} in payloads
    assert {"target_key": "b", "stream": "stderr", "line": "err-b", "type": "history"} in payloads
    assert sum(1 for p in payloads if p["target_key"] == "a") == 1


async def _fake_source(items):
    for it in items:
        yield it


def test_stream_events_replays_then_live_then_stops_on_all_done():
    source = _fake_source([
        {"target_key": "a", "stream": "stdout", "line": "hist-1"},
        {"target_key": "a", "stream": "stdout", "line": "live-1"},
        {"target_key": "a", "type": svc.DONE_TYPE, "status": "success"},
        {"target_key": "a", "stream": "stdout", "line": "SHOULD-NOT-APPEAR"},
    ])
    gen = svc.stream_execution_events(1, ["a"], message_source=source)
    chunks = _collect(gen)

    assert chunks[-1] == "data: [DONE]\n\n"
    payloads = _payloads(chunks)
    lines = [p.get("line") for p in payloads if "line" in p]
    assert lines == ["hist-1", "live-1"]  # done 之后的行不再转发
    assert any(p.get("type") == svc.DONE_TYPE for p in payloads)


def test_stream_events_emits_done_when_source_exhausts_without_sentinel():
    # 例如高危拦截/异常路径未发 done：source 自然结束也要收尾 [DONE]
    source = _fake_source([{"target_key": "a", "stream": "stdout", "line": "x"}])
    gen = svc.stream_execution_events(1, ["a", "b"], message_source=source)
    chunks = _collect(gen)
    assert chunks[-1] == "data: [DONE]\n\n"


def test_stream_events_handles_source_error_gracefully():
    async def _boom():
        yield {"target_key": "a", "line": "ok"}
        raise RuntimeError("nats down")

    gen = svc.stream_execution_events(1, ["a"], message_source=_boom())
    chunks = _collect(gen)
    payloads = _payloads(chunks)
    assert any(p.get("type") == "error" for p in payloads)
    assert chunks[-1] == "data: [DONE]\n\n"


def test_stream_events_uses_default_source_when_none(monkeypatch):
    async def _fake_default(execution_id):
        yield {"target_key": "a", "type": svc.DONE_TYPE, "status": "success"}

    monkeypatch.setattr(svc, "_default_message_source", _fake_default)
    chunks = _collect(svc.stream_execution_events(1, ["a"]))
    assert chunks[-1] == "data: [DONE]\n\n"
