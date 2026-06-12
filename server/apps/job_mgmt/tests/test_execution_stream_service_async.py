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
