from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from django.conf import settings
from django.core import signing

from apps.workflow_orchestration.services.definitions import DefinitionValidationError
from apps.workflow_orchestration.services.nats_triggers import MAX_NATS_INPUT_BYTES, validate_nats_event
from nats_client.clients import get_nc_client

NATS_TEST_TIMEOUT_SECONDS = 30
NATS_TEST_TOKEN_MAX_AGE_SECONDS = 60
NATS_TEST_TOKEN_SALT = "workflow-orchestration-nats-test"


class NatsTestSessionError(ValueError):
    pass


class NatsTestTimeout(NatsTestSessionError):
    pass


def create_nats_test_session(*, team_id: int, workflow_id: int, node_key: str) -> dict[str, Any]:
    namespace = str(getattr(settings, "NATS_NAMESPACE", "bklite") or "bklite").strip(".")
    nonce = uuid.uuid4().hex
    subject = f"{namespace}.workflow.test.{workflow_id}.{node_key}.{nonce}"
    payload = {
        "team_id": team_id,
        "workflow_id": workflow_id,
        "node_key": node_key,
        "subject": subject,
    }
    return {
        "token": signing.dumps(payload, salt=NATS_TEST_TOKEN_SALT, compress=True),
        "subject": subject,
        "timeout_seconds": NATS_TEST_TIMEOUT_SECONDS,
    }


def read_nats_test_session(token: str, *, max_age: int = NATS_TEST_TOKEN_MAX_AGE_SECONDS) -> dict[str, Any]:
    try:
        payload = signing.loads(token, salt=NATS_TEST_TOKEN_SALT, max_age=max_age)
    except signing.SignatureExpired as error:
        raise NatsTestSessionError("NATS 测试会话已过期，请重新监听") from error
    except signing.BadSignature as error:
        raise NatsTestSessionError("NATS 测试会话非法") from error
    if not isinstance(payload, dict) or not all(key in payload for key in ("team_id", "workflow_id", "node_key", "subject")):
        raise NatsTestSessionError("NATS 测试会话非法")
    return payload


async def _wait_for_nats_test_event(subject: str, timeout_seconds: int) -> dict[str, Any]:
    connection = await get_nc_client()
    subscription = None
    loop = asyncio.get_running_loop()
    received = loop.create_future()

    async def callback(message):
        if not received.done():
            received.set_result(bytes(message.data))

    try:
        subscription = await connection.subscribe(subject, cb=callback)
        await connection.flush()
        try:
            raw = await asyncio.wait_for(received, timeout=timeout_seconds)
        except asyncio.TimeoutError as error:
            raise NatsTestTimeout("等待 NATS 测试事件超时，请重新监听") from error
        if len(raw) > MAX_NATS_INPUT_BYTES + 4096:
            raise NatsTestSessionError("NATS 测试事件最大 1 MiB")
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NatsTestSessionError("NATS 测试事件必须是合法 JSON") from error
        try:
            normalized_event, _, inputs = validate_nats_event(event)
        except DefinitionValidationError as error:
            raise NatsTestSessionError(str(error)) from error
        return {"event": normalized_event, "inputs": inputs}
    finally:
        if subscription is not None:
            await subscription.unsubscribe()
        await connection.close()


def wait_for_nats_test_event(subject: str, *, timeout_seconds: int = NATS_TEST_TIMEOUT_SECONDS) -> dict[str, Any]:
    bounded_timeout = max(1, min(int(timeout_seconds), NATS_TEST_TIMEOUT_SECONDS))
    return asyncio.run(_wait_for_nats_test_event(subject, bounded_timeout))
