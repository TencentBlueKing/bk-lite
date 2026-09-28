import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.workflow_orchestration.services.nats_test_sessions import (
    NatsTestSessionError,
    NatsTestTimeout,
    create_nats_test_session,
    read_nats_test_session,
    wait_for_nats_test_event,
)

pytestmark = pytest.mark.unit


def test_nats_test_session_is_short_lived_and_team_scoped(settings):
    settings.NATS_NAMESPACE = "bklite"
    session = create_nats_test_session(team_id=7, workflow_id=42, node_key="trigger_nats")

    assert session["subject"].startswith("bklite.workflow.test.42.trigger_nats.")
    decoded = read_nats_test_session(session["token"], max_age=60)
    assert decoded["team_id"] == 7
    assert decoded["workflow_id"] == 42
    assert decoded["node_key"] == "trigger_nats"
    assert decoded["subject"] == session["subject"]


def test_wait_for_nats_test_event_returns_real_payload_and_closes_connection(mocker):
    event = {
        "event_id": "evt-test-1",
        "occurred_at": "2026-09-18T10:00:00Z",
        "producer": "job-platform",
        "payload": {"status": "SUCCESS", "target": "10.10.90.120"},
    }
    subscription = MagicMock()
    subscription.unsubscribe = AsyncMock()
    connection = MagicMock()
    connection.flush = AsyncMock()
    connection.close = AsyncMock()

    async def subscribe(_subject, cb):
        asyncio.get_running_loop().call_soon(asyncio.create_task, cb(MagicMock(data=json.dumps(event).encode())))
        return subscription

    connection.subscribe = AsyncMock(side_effect=subscribe)

    async def get_connection():
        return connection

    mocker.patch("apps.workflow_orchestration.services.nats_test_sessions.get_nc_client", get_connection)

    result = wait_for_nats_test_event("bklite.workflow.test.42.trigger_nats.token", timeout_seconds=1)

    assert result == {"event": event, "inputs": event["payload"]}
    subscription.unsubscribe.assert_awaited_once()
    connection.close.assert_awaited_once()


def test_wait_for_nats_test_event_rejects_invalid_envelope_and_still_closes(mocker):
    subscription = MagicMock()
    subscription.unsubscribe = AsyncMock()
    connection = MagicMock()
    connection.flush = AsyncMock()
    connection.close = AsyncMock()

    async def subscribe(_subject, cb):
        asyncio.get_running_loop().call_soon(asyncio.create_task, cb(MagicMock(data=b'{"payload":{}}')))
        return subscription

    connection.subscribe = AsyncMock(side_effect=subscribe)

    async def get_connection():
        return connection

    mocker.patch("apps.workflow_orchestration.services.nats_test_sessions.get_nc_client", get_connection)

    with pytest.raises(NatsTestSessionError, match="event_id"):
        wait_for_nats_test_event("bklite.workflow.test.42.trigger_nats.token", timeout_seconds=1)

    subscription.unsubscribe.assert_awaited_once()
    connection.close.assert_awaited_once()


def test_wait_for_nats_test_event_times_out_and_still_closes(mocker):
    subscription = MagicMock()
    subscription.unsubscribe = AsyncMock()
    connection = MagicMock()
    connection.subscribe = AsyncMock(return_value=subscription)
    connection.flush = AsyncMock()
    connection.close = AsyncMock()

    async def get_connection():
        return connection

    mocker.patch("apps.workflow_orchestration.services.nats_test_sessions.get_nc_client", get_connection)

    with pytest.raises(NatsTestTimeout, match="超时"):
        wait_for_nats_test_event("bklite.workflow.test.42.trigger_nats.token", timeout_seconds=1)

    subscription.unsubscribe.assert_awaited_once()
    connection.close.assert_awaited_once()
