from __future__ import annotations

import hashlib
import time
from typing import Any

from django.core import signing
from django.core.cache import cache

WEBHOOK_TEST_SESSION_TTL_SECONDS = 60
_SIGNING_SALT = "workflow-orchestration-webhook-test"


class WebhookTestSessionError(ValueError):
    pass


class WebhookTestTimeout(WebhookTestSessionError):
    pass


def _cache_key(token: str) -> str:
    return f"workflow:webhook-test:{hashlib.sha256(token.encode('utf-8')).hexdigest()}"


def create_webhook_test_session(*, team_id: int, workflow_id: int, node_key: str) -> dict[str, Any]:
    token = signing.dumps(
        {"team_id": int(team_id), "workflow_id": int(workflow_id), "node_key": node_key},
        salt=_SIGNING_SALT,
        compress=True,
    )
    return {"token": token, "timeout_seconds": WEBHOOK_TEST_SESSION_TTL_SECONDS}


def read_webhook_test_session(token: str) -> dict[str, Any]:
    try:
        payload = signing.loads(token, salt=_SIGNING_SALT, max_age=WEBHOOK_TEST_SESSION_TTL_SECONDS)
    except signing.SignatureExpired as error:
        raise WebhookTestSessionError("Webhook 测试会话已过期") from error
    except signing.BadSignature as error:
        raise WebhookTestSessionError("Webhook 测试会话无效") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("team_id"), int) or not isinstance(payload.get("workflow_id"), int):
        raise WebhookTestSessionError("Webhook 测试会话无效")
    node_key = payload.get("node_key")
    if not isinstance(node_key, str) or not node_key:
        raise WebhookTestSessionError("Webhook 测试会话无效")
    return payload


def capture_webhook_test_event(token: str, body: dict[str, Any], *, team_ids: list[int]) -> None:
    session = read_webhook_test_session(token)
    if session["team_id"] not in team_ids:
        raise WebhookTestSessionError("Webhook 测试会话不属于调用方组织")
    cache.set(_cache_key(token), {"body": body}, timeout=WEBHOOK_TEST_SESSION_TTL_SECONDS)


def wait_for_webhook_test_event(token: str, *, timeout_seconds: float = WEBHOOK_TEST_SESSION_TTL_SECONDS) -> dict[str, Any]:
    read_webhook_test_session(token)
    deadline = time.monotonic() + max(0.01, min(float(timeout_seconds), WEBHOOK_TEST_SESSION_TTL_SECONDS))
    key = _cache_key(token)
    while time.monotonic() < deadline:
        event = cache.get(key)
        if isinstance(event, dict):
            cache.delete(key)
            return event
        time.sleep(0.05)
    raise WebhookTestTimeout("等待 Webhook 测试请求超时")
