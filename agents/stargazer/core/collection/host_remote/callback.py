import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any, Dict, List

from core.infra.redis_client import get_redis_client
from core.logger import logger

HOST_REMOTE_CALLBACK_HANDLER = "host_remote.callback"
HOST_REMOTE_CALLBACK_PROTOCOL_VERSION = "host_remote.v2"
HOST_REMOTE_CALLBACK_CONTEXT_TTL_SECONDS = int(
    os.getenv("HOST_REMOTE_CALLBACK_CONTEXT_TTL_SECONDS", "3600")
)
HOST_REMOTE_SUBMIT_ACCEPT_TIMEOUT_SECONDS = int(
    os.getenv("HOST_REMOTE_SUBMIT_ACCEPT_TIMEOUT_SECONDS", "300")
)
HOST_REMOTE_CALLBACK_DEADLINE_SECONDS = int(
    os.getenv("HOST_REMOTE_CALLBACK_DEADLINE_SECONDS", "1200")
)
HOST_REMOTE_PROCESSING_STALE_SECONDS = int(
    os.getenv("HOST_REMOTE_PROCESSING_STALE_SECONDS", "300")
)
HOST_REMOTE_SWEEP_INTERVAL_SECONDS = int(
    os.getenv("HOST_REMOTE_SWEEP_INTERVAL_SECONDS", "30")
)
HOST_REMOTE_CALLBACK_LEGACY_MAX_AGE_SECONDS = int(
    os.getenv(
        "HOST_REMOTE_CALLBACK_LEGACY_MAX_AGE_SECONDS",
        str(HOST_REMOTE_CALLBACK_CONTEXT_TTL_SECONDS),
    )
)
_HOST_REMOTE_CALLBACK_CONTEXT_KEY_PREFIX = "host_remote:callback_context"
_HOST_REMOTE_CALLBACK_GENERATION_KEY_PREFIX = "host_remote:current_generation"
_host_remote_callback_pool = None
_HOST_REMOTE_PROCESSING_CLAIM_PREFIX = "host_remote:processing_claim"

_STORE_CALLBACK_CONTEXT_LUA = """
local run_key = KEYS[1]
local generation_key = KEYS[2]
local context_key = KEYS[3]
local expected_owner = ARGV[1]
local expected_fence = tostring(ARGV[2])
local expected_attempt = ARGV[3]
local generation_json = ARGV[4]
local context_json = ARGV[5]
local ttl_seconds = tonumber(ARGV[6])

if redis.call('HGET', run_key, 'owner_id') ~= expected_owner then
    return {0, ''}
end
if redis.call('HGET', run_key, 'fence') ~= expected_fence then
    return {0, ''}
end
if redis.call('HGET', run_key, 'attempt_id') ~= expected_attempt then
    return {0, ''}
end

redis.call('SET', generation_key, generation_json, 'EX', ttl_seconds)
local existing_context = redis.call('GET', context_key)
if existing_context then
    return {2, existing_context}
end
redis.call('SET', context_key, context_json, 'EX', ttl_seconds)
return {1, context_json}
"""
_READ_CALLBACK_GENERATION_LUA = """
local generation_json = redis.call('GET', KEYS[1]) or ''
local run_exists = redis.call('EXISTS', KEYS[2])
local latest_fence = redis.call('HGET', KEYS[3], 'fence') or ''
local latest_attempt = redis.call('HGET', KEYS[3], 'attempt_id') or ''
local latest_owner = redis.call('HGET', KEYS[3], 'owner_id') or ''
if run_exists == 0 then
    return {
        generation_json, '', '', '', 0,
        latest_fence, latest_attempt, latest_owner
    }
end
return {
    generation_json,
    redis.call('HGET', KEYS[2], 'fence') or '',
    redis.call('HGET', KEYS[2], 'attempt_id') or '',
    redis.call('HGET', KEYS[2], 'owner_id') or '',
    1,
    latest_fence,
    latest_attempt,
    latest_owner
}
"""
_RECORD_CALLBACK_PAYLOAD_LUA = """
local context_json = redis.call('GET', KEYS[1])
if not context_json then
    return {0, ''}
end

local expected_owner = ARGV[1]
local expected_fence = tostring(ARGV[2])
local expected_attempt = ARGV[3]
local generation_json = redis.call('GET', KEYS[2])
if not generation_json then
    return {1, ''}
end
local generation = cjson.decode(generation_json)
if tostring(generation['fence'] or '') ~= expected_fence
    or tostring(generation['attempt'] or '') ~= expected_attempt
    or tostring(generation['owner_id'] or '') ~= expected_owner then
    return {1, ''}
end

if tostring(redis.call('HGET', KEYS[4], 'fence') or '') ~= expected_fence
    or tostring(redis.call('HGET', KEYS[4], 'attempt_id') or '') ~= expected_attempt
    or tostring(redis.call('HGET', KEYS[4], 'owner_id') or '') ~= expected_owner then
    return {2, ''}
end

if redis.call('EXISTS', KEYS[3]) == 1 then
    if tostring(redis.call('HGET', KEYS[3], 'fence') or '') ~= expected_fence
        or tostring(redis.call('HGET', KEYS[3], 'attempt_id') or '') ~= expected_attempt
        or tostring(redis.call('HGET', KEYS[3], 'owner_id') or '') ~= expected_owner then
        return {3, ''}
    end
end

local context = cjson.decode(context_json)
if not context['status']
    or context['status']['execution'] ~= 'waiting_callback'
    or (context['raw_callback'] and context['raw_callback'] ~= cjson.null) then
    return {4, context_json}
end

local now_ms = tonumber(ARGV[5])
context['raw_callback'] = cjson.decode(ARGV[4])
context['callback_received_at'] = now_ms
context['updated_at'] = now_ms
context['last_error'] = cjson.null
context['status']['execution'] = 'execution_finished'
if context['ctx'] then
    context['ctx']['token'] = nil
end
local updated_json = cjson.encode(context)
local ttl_seconds = redis.call('TTL', KEYS[1])
if ttl_seconds <= 0 then
    ttl_seconds = tonumber(ARGV[6])
end
redis.call('SET', KEYS[1], updated_json, 'EX', ttl_seconds)
return {5, updated_json}
"""
_MARK_SUBMIT_ACCEPTED_LUA = """
local context_json = redis.call('GET', KEYS[1])
if not context_json then
    return {0, ''}
end
local context = cjson.decode(context_json)
if not context['status']
    or context['status']['execution'] ~= 'waiting_callback'
    or (context['raw_callback'] and context['raw_callback'] ~= cjson.null) then
    return {2, context_json}
end
context['callback_deadline_at'] = tonumber(ARGV[1])
context['updated_at'] = tonumber(ARGV[2])
context['last_error'] = cjson.null
local updated_json = cjson.encode(context)
local ttl_seconds = redis.call('TTL', KEYS[1])
if ttl_seconds <= 0 then
    ttl_seconds = tonumber(ARGV[3])
end
redis.call('SET', KEYS[1], updated_json, 'EX', ttl_seconds)
return {1, updated_json}
"""

_RELEASE_PROCESSING_CLAIM_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""
_RENEW_PROCESSING_CLAIM_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""


def get_stargazer_service_name(instance_id: str | None = None) -> str:
    return f"{instance_id or os.getenv('NATS_INSTANCE_ID', 'default')}_stargazer"


def get_host_remote_callback_subject(service_name: str | None = None) -> str:
    return (
        f"{service_name or get_stargazer_service_name()}.{HOST_REMOTE_CALLBACK_HANDLER}"
    )


def get_host_remote_callback_queue(service_name: str | None = None) -> str:
    return get_host_remote_callback_subject(service_name)


def _normalize_task_id(task_id) -> str:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        raise ValueError("task_id is required for Host Remote callback context")
    return normalized_task_id


def _hash_callback_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_host_remote_callback_v2_enabled() -> bool:
    return str(
        os.getenv("HOST_REMOTE_CALLBACK_V2_ENABLED", "false")
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _derive_host_remote_callback_token(identity: dict) -> str:
    secret = str(os.getenv("HOST_REMOTE_CALLBACK_TOKEN_SECRET") or "")
    if len(secret) < 32:
        raise RuntimeError(
            "HOST_REMOTE_CALLBACK_TOKEN_SECRET must contain at least 32 characters"
        )
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def restore_host_remote_callback_identity(trusted_identity: dict) -> dict:
    binding_fields = (
        "protocol_version",
        "fence",
        "target",
        "collection_task_id",
        "plugin_ref",
        "owner_id",
        "attempt",
        "caller",
    )
    identity = {key: trusted_identity[key] for key in binding_fields}
    identity["token"] = _derive_host_remote_callback_token(identity)
    if not hmac.compare_digest(
        _hash_callback_token(identity["token"]),
        str(trusted_identity.get("token_hash") or ""),
    ):
        raise RuntimeError("Host Remote stored identity token digest mismatch")
    return identity


def _is_legacy_host_remote_callback_context(
    payload: dict, callback_context: dict
) -> bool:
    task_id = str(
        (payload or {}).get("task_id") or (callback_context or {}).get("task_id") or ""
    ).strip()
    trusted = (callback_context or {}).get("ctx") or {}
    return (
        task_id.startswith("remote-")
        and not task_id.startswith("remote-v2-")
        and not trusted.get("protocol_version")
        and not trusted.get("token_hash")
    )


def _validate_legacy_host_remote_callback_context(callback_context: dict) -> None:
    created_at = int((callback_context or {}).get("created_at") or 0)
    max_age_ms = max(0, HOST_REMOTE_CALLBACK_LEGACY_MAX_AGE_SECONDS) * 1000
    if not created_at or not max_age_ms or _now_ms() - created_at > max_age_ms:
        raise RuntimeError("Host Remote legacy compatibility window expired")
    status = (callback_context or {}).get("status") or {}
    if status.get("execution") != "waiting_callback":
        raise RuntimeError("Host Remote callback is duplicate or out of order")
    if (callback_context or {}).get("raw_callback") is not None:
        raise RuntimeError("Host Remote callback is duplicate or out of order")
    deadline = int((callback_context or {}).get("callback_deadline_at") or 0)
    if deadline and deadline <= _now_ms():
        raise RuntimeError("Host Remote callback is expired")


def issue_host_remote_callback_identity(
    *,
    fence: int,
    target: str,
    collection_task_id: str,
    plugin_ref: str,
    owner_id: str,
    attempt: str,
    caller: str,
) -> tuple[dict, dict]:
    identity = {
        "protocol_version": HOST_REMOTE_CALLBACK_PROTOCOL_VERSION,
        "fence": fence,
        "target": target,
        "collection_task_id": collection_task_id,
        "plugin_ref": plugin_ref,
        "owner_id": owner_id,
        "attempt": attempt,
        "caller": caller,
    }
    token = _derive_host_remote_callback_token(identity)
    identity["token"] = token
    trusted = dict(identity)
    trusted.pop("token")
    trusted["token_hash"] = _hash_callback_token(token)
    return identity, trusted


def validate_host_remote_callback_identity(
    payload: dict, callback_context: dict
) -> None:
    if _is_legacy_host_remote_callback_context(payload, callback_context):
        _validate_legacy_host_remote_callback_context(callback_context)
        log_host_remote_event(
            "legacy_callback_accepted",
            (callback_context or {}).get("task_id"),
            level="warning",
            execution="waiting_callback",
        )
        return
    trusted = (callback_context or {}).get("ctx") or {}
    identity = (payload or {}).get("callback_context")
    if not isinstance(identity, dict):
        raise RuntimeError("Host Remote callback identity context is missing")
    if identity.get("protocol_version") != HOST_REMOTE_CALLBACK_PROTOCOL_VERSION:
        raise RuntimeError("Host Remote callback protocol version mismatch")
    token = identity.get("token")
    expected_token_hash = str(trusted.get("token_hash") or "")
    if (
        not isinstance(token, str)
        or not token
        or not expected_token_hash
        or not hmac.compare_digest(_hash_callback_token(token), expected_token_hash)
    ):
        raise RuntimeError("Host Remote callback token mismatch")
    expected_fence = int(trusted.get("fence") or 0)
    actual_fence = int(identity.get("fence") or 0)
    if not expected_fence or actual_fence != expected_fence:
        raise RuntimeError("Host Remote callback fencing token mismatch")
    if str(identity.get("target") or "") != str(trusted.get("target") or ""):
        raise RuntimeError("Host Remote callback target mismatch")
    if str(identity.get("collection_task_id") or "") != str(
        trusted.get("collection_task_id") or ""
    ):
        raise RuntimeError("Host Remote callback collection task mismatch")
    if str(identity.get("plugin_ref") or "") != str(trusted.get("plugin_ref") or ""):
        raise RuntimeError("Host Remote callback plugin mismatch")
    if str(identity.get("owner_id") or "") != str(trusted.get("owner_id") or ""):
        raise RuntimeError("Host Remote callback owner mismatch")
    if str(identity.get("attempt") or "") != str(trusted.get("attempt") or ""):
        raise RuntimeError("Host Remote callback attempt mismatch")
    if str(identity.get("caller") or "") != str(trusted.get("caller") or ""):
        raise RuntimeError("Host Remote callback caller mismatch")
    status = (callback_context or {}).get("status") or {}
    if status.get("execution") != "waiting_callback":
        raise RuntimeError("Host Remote callback is duplicate or out of order")
    if (callback_context or {}).get("raw_callback") is not None:
        raise RuntimeError("Host Remote callback is duplicate or out of order")
    deadline = int((callback_context or {}).get("callback_deadline_at") or 0)
    if deadline and deadline <= _now_ms():
        raise RuntimeError("Host Remote callback is expired")


async def ensure_host_remote_callback_fence_is_current(
    callback_context: dict,
) -> None:
    """拒绝 Pod 接管后由旧 fencing token 返回的迟到回调。"""
    if _is_legacy_host_remote_callback_context({}, callback_context):
        _validate_legacy_host_remote_callback_context(callback_context)
        return
    trusted = (callback_context or {}).get("ctx") or {}
    task_id = str(trusted.get("collection_task_id") or "").strip()
    expected_fence = int(trusted.get("fence") or 0)
    expected_attempt = str(trusted.get("attempt") or "").strip()
    expected_owner = str(trusted.get("owner_id") or "").strip()
    if not task_id or not expected_fence or not expected_attempt or not expected_owner:
        raise RuntimeError("Host Remote callback context identity is incomplete")
    redis_pool = await _get_host_remote_callback_pool()
    (
        raw_generation,
        active_fence,
        active_attempt,
        active_owner,
        run_exists,
        latest_fence,
        latest_attempt,
        latest_owner,
    ) = await redis_pool.eval(
        _READ_CALLBACK_GENERATION_LUA,
        3,
        _build_callback_generation_key(task_id),
        _build_collection_run_key(task_id),
        _build_collection_fence_key(task_id),
    )
    if not raw_generation:
        raise RuntimeError("Host Remote callback generation is stale")
    generation = json.loads(_decode_redis_text(raw_generation))
    current_fence = str(generation.get("fence") or "")
    current_attempt = str(generation.get("attempt") or "")
    current_owner = str(generation.get("owner_id") or "")
    if str(current_fence or "") != str(expected_fence):
        raise RuntimeError("Host Remote callback fencing token is stale")
    if current_attempt != expected_attempt:
        raise RuntimeError("Host Remote callback attempt is stale")
    if current_owner != expected_owner:
        raise RuntimeError("Host Remote callback owner is stale")
    if _decode_redis_text(latest_fence) != str(expected_fence):
        raise RuntimeError("Host Remote callback latest fencing token is stale")
    if _decode_redis_text(latest_attempt) != expected_attempt:
        raise RuntimeError("Host Remote callback latest attempt is stale")
    if _decode_redis_text(latest_owner) != expected_owner:
        raise RuntimeError("Host Remote callback latest owner is stale")
    if int(run_exists):
        if _decode_redis_text(active_fence) != str(expected_fence):
            raise RuntimeError("Host Remote callback active fencing token is stale")
        if _decode_redis_text(active_attempt) != expected_attempt:
            raise RuntimeError("Host Remote callback active attempt is stale")
        if _decode_redis_text(active_owner) != expected_owner:
            raise RuntimeError("Host Remote callback active owner is stale")


def _decode_redis_text(value) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return str(value or "")


def _build_callback_context_key(task_id) -> str:
    return f"{_HOST_REMOTE_CALLBACK_CONTEXT_KEY_PREFIX}:{_normalize_task_id(task_id)}"


def _build_callback_generation_key(collection_task_id) -> str:
    return (
        f"{_HOST_REMOTE_CALLBACK_GENERATION_KEY_PREFIX}:"
        f"{_normalize_task_id(collection_task_id)}"
    )


def _build_collection_run_key(collection_task_id) -> str:
    prefix = os.getenv("COLLECTION_REDIS_PREFIX", "stargazer:collection:v1")
    return f"{prefix.rstrip(':')}:run:{_normalize_task_id(collection_task_id)}"


def _build_collection_fence_key(collection_task_id) -> str:
    prefix = os.getenv("COLLECTION_REDIS_PREFIX", "stargazer:collection:v1")
    return f"{prefix.rstrip(':')}:fence:{_normalize_task_id(collection_task_id)}"


def get_task_running_key(task_id) -> str:
    return f"task:running:{_normalize_task_id(task_id)}"


async def claim_host_remote_processing(task_id: str) -> str:
    redis_pool = await _get_host_remote_callback_pool()
    token = uuid.uuid4().hex
    claimed = await redis_pool.set(
        f"{_HOST_REMOTE_PROCESSING_CLAIM_PREFIX}:{_normalize_task_id(task_id)}",
        token,
        nx=True,
        ex=max(1, HOST_REMOTE_PROCESSING_STALE_SECONDS),
    )
    return token if claimed else ""


async def release_host_remote_processing_claim(task_id: str, token: str) -> bool:
    if not token:
        return False
    redis_pool = await _get_host_remote_callback_pool()
    released = await redis_pool.eval(
        _RELEASE_PROCESSING_CLAIM_LUA,
        1,
        f"{_HOST_REMOTE_PROCESSING_CLAIM_PREFIX}:{_normalize_task_id(task_id)}",
        token,
    )
    return bool(released)


async def renew_host_remote_processing_claim(task_id: str, token: str) -> bool:
    redis_pool = await _get_host_remote_callback_pool()
    renewed = await redis_pool.eval(
        _RENEW_PROCESSING_CLAIM_LUA,
        1,
        f"{_HOST_REMOTE_PROCESSING_CLAIM_PREFIX}:{_normalize_task_id(task_id)}",
        token,
        max(1, HOST_REMOTE_PROCESSING_STALE_SECONDS),
    )
    return bool(renewed)


def _make_json_safe_dict(value) -> dict:
    if not isinstance(value, dict):
        return {}

    try:
        json.dumps(value)
        return dict(value)
    except TypeError:
        safe_value = {}
        for key, item in value.items():
            try:
                json.dumps(item)
            except TypeError:
                continue
            safe_value[key] = item
        return safe_value


def _now_ms() -> int:
    return int(time.time() * 1000)


def _default_callback_status() -> dict:
    return {
        "execution": "waiting_callback",
        "delivery": "not_ready",
    }


def is_retryable_host_remote_publish_error(error: Exception) -> bool:
    message = str(error or "").lower()
    retryable_keywords = (
        "timeout",
        "timed out",
        "connection",
        "tls",
        "temporarily unavailable",
        "reset by peer",
        "unreachable",
        "refused",
        "eof",
        "nats",
    )
    return any(keyword in message for keyword in retryable_keywords)


def get_host_remote_publish_retry_backoffs() -> List[int]:
    configured = os.getenv("HOST_REMOTE_PUBLISH_RETRY_BACKOFFS", "15,60,300,900")
    backoffs = []
    for raw_value in configured.split(","):
        raw_value = raw_value.strip()
        if not raw_value:
            continue
        try:
            parsed_value = int(raw_value)
        except ValueError:
            continue
        if parsed_value > 0:
            backoffs.append(parsed_value)
    return backoffs or [15, 60, 300, 900]


def get_host_remote_processing_job_id(task_id) -> str:
    return f"process_host_remote_callback:{_normalize_task_id(task_id)}"


def log_host_remote_event(
    event: str, task_id, level: str = "info", **fields: Any
) -> None:
    normalized_task_id = str(task_id or "").strip()
    rendered_fields = ", ".join(
        f"{key}={value}" for key, value in fields.items() if value is not None
    )
    message = "[Host Remote] event=%s, task_id=%s"
    arguments = [event, normalized_task_id]
    if rendered_fields:
        message = f"{message}, %s"
        arguments.append(rendered_fields)
    log_method = getattr(logger, level, logger.info)
    log_method(message, *arguments)


def _normalize_callback_context(task_id, callback_context) -> dict:
    callback_context = dict(callback_context or {})
    status = callback_context.get("status")
    normalized_status = _default_callback_status()
    if isinstance(status, dict):
        normalized_status.update({k: v for k, v in status.items() if v is not None})

    now_ms = callback_context.get("updated_at") or _now_ms()
    callback_context.setdefault("task_id", _normalize_task_id(task_id))
    callback_context.setdefault("ctx", {})
    callback_context.setdefault("params", {})
    callback_context["status"] = normalized_status
    callback_context.setdefault("raw_callback", None)
    callback_context.setdefault("callback_received_at", None)
    callback_context.setdefault(
        "callback_deadline_at",
        callback_context.get("created_at")
        or now_ms + HOST_REMOTE_CALLBACK_DEADLINE_SECONDS * 1000,
    )
    callback_context.setdefault("process_enqueued_at", None)
    callback_context.setdefault("process_started_at", None)
    callback_context.setdefault("process_completed_at", None)
    callback_context.setdefault("processing_job_id", None)
    callback_context.setdefault("publish_attempts", 0)
    callback_context.setdefault("last_retry_at", None)
    callback_context.setdefault("next_retry_at", None)
    callback_context.setdefault("published_at", None)
    callback_context.setdefault("last_error", None)
    callback_context.setdefault(
        "created_at", callback_context.get("created_at") or now_ms
    )
    callback_context["updated_at"] = now_ms
    return callback_context


async def _save_host_remote_callback_context(
    task_id,
    callback_context,
    ttl_seconds=None,
):
    redis_pool = await _get_host_remote_callback_pool()
    normalized_context = _normalize_callback_context(task_id, callback_context)
    await redis_pool.set(
        _build_callback_context_key(task_id),
        json.dumps(normalized_context),
        ex=ttl_seconds or HOST_REMOTE_CALLBACK_CONTEXT_TTL_SECONDS,
    )
    return normalized_context


async def _get_host_remote_callback_pool():
    global _host_remote_callback_pool

    if _host_remote_callback_pool is None:
        _host_remote_callback_pool = await get_redis_client()

    return _host_remote_callback_pool


async def store_host_remote_callback_context(
    task_id, params, ctx=None, ttl_seconds=None
):
    created_at = _now_ms()
    callback_context = {
        "task_id": _normalize_task_id(task_id),
        "ctx": _make_json_safe_dict(ctx or {}),
        "params": dict(params or {}),
        "status": _default_callback_status(),
        "created_at": created_at,
        "updated_at": created_at,
        "raw_callback": None,
        "callback_received_at": None,
        "callback_deadline_at": None,
        "process_enqueued_at": None,
        "process_started_at": None,
        "process_completed_at": None,
        "processing_job_id": None,
        "publish_attempts": 0,
        "last_retry_at": None,
        "next_retry_at": None,
        "published_at": None,
        "last_error": None,
    }
    trusted = callback_context["ctx"]
    collection_task_id = str(trusted.get("collection_task_id") or "").strip()
    owner_id = str(trusted.get("owner_id") or "").strip()
    fence = int(trusted.get("fence") or 0)
    attempt = str(trusted.get("attempt") or "").strip()
    if not collection_task_id or not owner_id or not fence or not attempt:
        raise RuntimeError("Host Remote callback context identity is incomplete")
    ttl = ttl_seconds or HOST_REMOTE_CALLBACK_CONTEXT_TTL_SECONDS
    generation_json = json.dumps(
        {"fence": fence, "attempt": attempt, "owner_id": owner_id},
        separators=(",", ":"),
    )
    context_json = json.dumps(callback_context)
    redis_pool = await _get_host_remote_callback_pool()
    status, stored_context_json = await redis_pool.eval(
        _STORE_CALLBACK_CONTEXT_LUA,
        3,
        _build_collection_run_key(collection_task_id),
        _build_callback_generation_key(collection_task_id),
        _build_callback_context_key(task_id),
        owner_id,
        fence,
        attempt,
        generation_json,
        context_json,
        ttl,
    )
    if int(status) == 0:
        raise RuntimeError("Host Remote callback generation is stale")
    stored_context = _normalize_callback_context(
        task_id,
        json.loads(_decode_redis_text(stored_context_json)),
    )
    log_host_remote_event(
        "context_stored",
        task_id,
        execution="waiting_callback",
        delivery="not_ready",
    )
    return stored_context


async def mark_host_remote_submit_accepted(task_id):
    now_ms = _now_ms()
    deadline_at = now_ms + HOST_REMOTE_CALLBACK_DEADLINE_SECONDS * 1000
    redis_pool = await _get_host_remote_callback_pool()
    status, stored_context_json = await redis_pool.eval(
        _MARK_SUBMIT_ACCEPTED_LUA,
        1,
        _build_callback_context_key(task_id),
        deadline_at,
        now_ms,
        HOST_REMOTE_CALLBACK_CONTEXT_TTL_SECONDS,
    )
    status = int(status)
    if status == 0:
        raise RuntimeError("Host Remote callback context disappeared before submit ack")
    updated_context = _normalize_callback_context(
        task_id,
        json.loads(_decode_redis_text(stored_context_json)),
    )
    event = "callback_deadline_started"
    fields = {"callback_deadline_at": deadline_at}
    if status == 2:
        event = "submit_ack_after_callback"
        fields = {}
    log_host_remote_event(
        event,
        task_id,
        execution=(updated_context or {}).get("status", {}).get("execution"),
        delivery=(updated_context or {}).get("status", {}).get("delivery"),
        **fields,
    )
    return updated_context


async def load_host_remote_callback_context(task_id):
    redis_pool = await _get_host_remote_callback_pool()
    callback_context = await redis_pool.get(_build_callback_context_key(task_id))
    if not callback_context:
        return None

    if isinstance(callback_context, (bytes, bytearray)):
        callback_context = callback_context.decode()

    return _normalize_callback_context(task_id, json.loads(callback_context))


async def update_host_remote_callback_context(task_id, **updates):
    callback_context = await load_host_remote_callback_context(task_id)
    if callback_context is None:
        return None

    callback_context = dict(callback_context)
    status_updates = updates.pop("status", None)
    if isinstance(status_updates, dict):
        status = dict(callback_context.get("status") or {})
        status.update({k: v for k, v in status_updates.items() if v is not None})
        callback_context["status"] = status

    callback_context.update(updates)
    callback_context["updated_at"] = _now_ms()
    return await _save_host_remote_callback_context(task_id, callback_context)


async def record_host_remote_callback_payload(task_id, payload):
    callback_context = await load_host_remote_callback_context(task_id)
    if callback_context is None:
        return None

    if _is_legacy_host_remote_callback_context(payload, callback_context):
        _validate_legacy_host_remote_callback_context(callback_context)
        return await update_host_remote_callback_context(
            task_id,
            raw_callback=payload,
            callback_received_at=_now_ms(),
            last_error=None,
            status={"execution": "execution_finished"},
        )

    trusted = (callback_context or {}).get("ctx") or {}
    collection_task_id = str(trusted.get("collection_task_id") or "").strip()
    owner_id = str(trusted.get("owner_id") or "").strip()
    fence = int(trusted.get("fence") or 0)
    attempt = str(trusted.get("attempt") or "").strip()
    if not collection_task_id or not owner_id or not fence or not attempt:
        raise RuntimeError("Host Remote callback context identity is incomplete")
    redacted_payload = dict(payload or {})
    identity = redacted_payload.get("callback_context")
    if isinstance(identity, dict):
        redacted_payload["callback_context"] = {
            key: value for key, value in identity.items() if key != "token"
        }
    redis_pool = await _get_host_remote_callback_pool()
    status, stored_context_json = await redis_pool.eval(
        _RECORD_CALLBACK_PAYLOAD_LUA,
        4,
        _build_callback_context_key(task_id),
        _build_callback_generation_key(collection_task_id),
        _build_collection_run_key(collection_task_id),
        _build_collection_fence_key(collection_task_id),
        owner_id,
        fence,
        attempt,
        json.dumps(redacted_payload),
        _now_ms(),
        HOST_REMOTE_CALLBACK_CONTEXT_TTL_SECONDS,
    )
    status = int(status)
    if status == 0:
        raise RuntimeError("Host Remote callback context disappeared before record")
    if status == 1:
        raise RuntimeError("Host Remote callback generation is stale")
    if status == 2:
        raise RuntimeError("Host Remote callback latest generation is stale")
    if status == 3:
        raise RuntimeError("Host Remote callback active generation is stale")
    if status == 4:
        log_host_remote_event(
            "callback_duplicate",
            task_id,
            execution=(callback_context.get("status") or {}).get("execution"),
            delivery=(callback_context.get("status") or {}).get("delivery"),
        )
        raise RuntimeError("Host Remote callback is duplicate or out of order")
    updated_context = _normalize_callback_context(
        task_id,
        json.loads(_decode_redis_text(stored_context_json)),
    )
    log_host_remote_event("callback_received", task_id, execution="execution_finished")
    return updated_context


async def mark_host_remote_processing_enqueued(task_id, processing_job_id=None):
    updated_context = await update_host_remote_callback_context(
        task_id,
        process_enqueued_at=_now_ms(),
        processing_job_id=processing_job_id
        or get_host_remote_processing_job_id(task_id),
        status={"delivery": "processing"},
    )
    log_host_remote_event(
        "processing_enqueued",
        task_id,
        delivery="processing",
        processing_job_id=(updated_context or {}).get("processing_job_id"),
    )
    return updated_context


async def mark_host_remote_processing_started(task_id):
    updated_context = await update_host_remote_callback_context(
        task_id,
        process_started_at=_now_ms(),
        last_error=None,
        next_retry_at=None,
        status={"delivery": "processing"},
    )
    log_host_remote_event("processing_started", task_id, delivery="processing")
    return updated_context


async def mark_host_remote_processing_published(task_id):
    now_ms = _now_ms()
    updated_context = await update_host_remote_callback_context(
        task_id,
        process_completed_at=now_ms,
        published_at=now_ms,
        last_error=None,
        next_retry_at=None,
        status={"delivery": "published"},
    )
    log_host_remote_event("published", task_id, delivery="published")
    return updated_context


async def mark_host_remote_processing_failed(task_id, error):
    updated_context = await update_host_remote_callback_context(
        task_id,
        process_completed_at=_now_ms(),
        last_error=str(error),
        next_retry_at=None,
        status={"delivery": "delivery_failed"},
    )
    log_host_remote_event(
        "processing_failed",
        task_id,
        level="error",
        delivery="delivery_failed",
        error=str(error),
    )
    return updated_context


async def schedule_host_remote_publish_retry(task_id, error):
    callback_context = await load_host_remote_callback_context(task_id)
    if callback_context is None:
        return {"retry_scheduled": False, "attempt": 0, "max_attempts": 0}

    attempts = int(callback_context.get("publish_attempts") or 0) + 1
    backoffs = get_host_remote_publish_retry_backoffs()
    if attempts > len(backoffs):
        await mark_host_remote_processing_failed(task_id, error)
        return {
            "retry_scheduled": False,
            "attempt": attempts,
            "max_attempts": len(backoffs),
        }

    delay_seconds = backoffs[attempts - 1]
    next_retry_at = _now_ms() + delay_seconds * 1000
    await update_host_remote_callback_context(
        task_id,
        publish_attempts=attempts,
        last_retry_at=_now_ms(),
        next_retry_at=next_retry_at,
        last_error=str(error),
        status={"delivery": "publish_pending"},
    )
    log_host_remote_event(
        "publish_retry_scheduled",
        task_id,
        delivery="publish_pending",
        attempt=attempts,
        retry_in_seconds=delay_seconds,
        error=str(error),
    )
    return {
        "retry_scheduled": True,
        "attempt": attempts,
        "max_attempts": len(backoffs),
        "delay_seconds": delay_seconds,
        "next_retry_at": next_retry_at,
    }


async def mark_host_remote_callback_timeout(task_id, reason: str = "callback timeout"):
    updated_context = await update_host_remote_callback_context(
        task_id,
        last_error=str(reason),
        status={"execution": "callback_timeout"},
    )
    log_host_remote_event(
        "callback_timeout",
        task_id,
        level="warning",
        execution="callback_timeout",
        error=str(reason),
    )
    return updated_context


async def list_host_remote_callback_contexts() -> List[Dict[str, Any]]:
    redis_pool = await _get_host_remote_callback_pool()
    raw_keys = await redis_pool.keys(f"{_HOST_REMOTE_CALLBACK_CONTEXT_KEY_PREFIX}:*")
    callback_contexts = []
    for raw_key in raw_keys:
        key = (
            raw_key.decode()
            if isinstance(raw_key, (bytes, bytearray))
            else str(raw_key)
        )
        task_id = key.rsplit(":", 1)[-1]
        callback_context = await load_host_remote_callback_context(task_id)
        if callback_context is not None:
            callback_contexts.append(callback_context)
    return callback_contexts


async def clear_host_remote_callback_context(task_id):
    callback_context = await load_host_remote_callback_context(task_id)
    if callback_context is None:
        return None

    redis_pool = await _get_host_remote_callback_pool()
    await redis_pool.delete(_build_callback_context_key(task_id))
    return callback_context


async def clear_host_remote_running_flag(task_id):
    redis_pool = await _get_host_remote_callback_pool()
    await redis_pool.delete(get_task_running_key(task_id))
