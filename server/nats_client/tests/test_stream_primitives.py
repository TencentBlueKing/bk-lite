# server/nats_client/tests/test_stream_primitives.py
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nats_client import clients

pytestmark = pytest.mark.unit


def test_publish_raw_sync_publishes_plain_json_to_subject():
    nc = MagicMock()
    nc.publish = AsyncMock()
    nc.flush = AsyncMock()
    nc.close = AsyncMock()

    async def _fake_get(*_a, **_k):
        return nc

    with patch.object(clients, "get_nc_client", _fake_get):
        clients.publish_raw_sync("job.stream.1.a", {"type": "done", "status": "success"})

    nc.publish.assert_awaited_once()
    subject, data = nc.publish.await_args.args
    assert subject == "job.stream.1.a"
    assert json.loads(data.decode()) == {"type": "done", "status": "success"}
    nc.close.assert_awaited_once()


def test_ensure_stream_sync_adds_stream_when_absent():
    js = MagicMock()
    js.add_stream = AsyncMock()
    nc = MagicMock()
    nc.jetstream = MagicMock(return_value=js)
    nc.close = AsyncMock()

    async def _fake_get(*_a, **_k):
        return nc

    with patch.object(clients, "get_nc_client", _fake_get):
        clients.ensure_stream_sync("JOB_LOG_STREAM", ["job.stream.>"], 3600, 1024)

    js.add_stream.assert_awaited_once()
    nc.close.assert_awaited_once()


def test_ensure_stream_sync_updates_stream_when_already_exists():
    js = MagicMock()
    js.add_stream = AsyncMock(side_effect=Exception("stream name already in use"))
    js.update_stream = AsyncMock()
    nc = MagicMock()
    nc.jetstream = MagicMock(return_value=js)
    nc.close = AsyncMock()

    async def _fake_get(*_a, **_k):
        return nc

    with patch.object(clients, "get_nc_client", _fake_get):
        clients.ensure_stream_sync("JOB_LOG_STREAM", ["job.stream.>"], 3600, 1024)

    js.update_stream.assert_awaited_once()
    nc.close.assert_awaited_once()
