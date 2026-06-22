import json
import os
import time
from typing import Any, Dict, List

from sanic.log import logger

HOST_REMOTE_CALLBACK_HANDLER = "host_remote.callback"
HOST_REMOTE_CALLBACK_CONTEXT_TTL_SECONDS = int(
    os.getenv("HOST_REMOTE_CALLBACK_CONTEXT_TTL_SECONDS", "3600")
)
_TASK_JOB_TIMEOUT_SECONDS = int(os.getenv("TASK_JOB_TIMEOUT", "600"))


def _resolve_host_remote_timeout(env_name: str, ratio: float, floor: int) -> int:
    """解析 host-remote 等待时限。

    显式设置环境变量时以其为准；否则按 TASK_JOB_TIMEOUT 的比例派生，
    保证默认配置下 submit-accept 等待与 callback 时限始终小于 worker job 超时，
    避免等待与 arq job 超时重叠（否则会触发启动告警且行为不一致）。
    """
    explicit = os.getenv(env_name)
    if explicit:
        return int(explicit)
    return max(floor, int(_TASK_JOB_TIMEOUT_SECONDS * ratio))


# submit-accept 等待发生在 worker job 内部，须明显小于 job 超时
HOST_REMOTE_SUBMIT_ACCEPT_TIMEOUT_SECONDS = _resolve_host_remote_timeout(
    "HOST_REMOTE_SUBMIT_ACCEPT_TIMEOUT_SECONDS", 0.5, 60
)
# callback 时限由 sweeper 兜底，保持小于 job 超时以避免重叠
HOST_REMOTE_CALLBACK_DEADLINE_SECONDS = _resolve_host_remote_timeout(
    "HOST_REMOTE_CALLBACK_DEADLINE_SECONDS", 0.8, 120
)
HOST_REMOTE_PROCESSING_STALE_SECONDS = int(
    os.getenv("HOST_REMOTE_PROCESSING_STALE_SECONDS", "300")
)
HOST_REMOTE_SWEEP_INTERVAL_SECONDS = int(
    os.getenv("HOST_REMOTE_SWEEP_INTERVAL_SECONDS", "30")
)
_HOST_REMOTE_CALLBACK_CONTEXT_KEY_PREFIX = "host_remote:callback_context"
_host_remote_callback_pool = None


def get_stargazer_service_name(instance_id: str | None = None) -> str:
    return f"{instance_id or os.getenv('NATS_INSTANCE_ID', 'default')}_stargazer"


def get_host_remote_callback_subject(service_name: str | None = None) -> str:
    return f"{service_name or get_stargazer_service_name()}.{HOST_REMOTE_CALLBACK_HANDLER}"


def get_host_remote_callback_queue(service_name: str | None = None) -> str:
    return get_host_remote_callback_subject(service_name)


def _normalize_task_id(task_id) -> str:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        raise ValueError("task_id is required for Host Remote callback context")
    return normalized_task_id


def _build_callback_context_key(task_id) -> str:
    return f"{_HOST_REMOTE_CALLBACK_CONTEXT_KEY_PREFIX}:{_normalize_task_id(task_id)}"


def get_task_running_key(task_id) -> str:
    return f"task:running:{_normalize_task_id(task_id)}"


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


def log_host_remote_event(event: str, task_id, level: str = "info", **fields: Any) -> None:
    normalized_task_id = str(task_id or "").strip()
    rendered_fields = ", ".join(
        f"{key}={value}" for key, value in fields.items() if value is not None
    )
    message = f"[Host Remote] event={event}, task_id={normalized_task_id}"
    if rendered_fields:
        message = f"{message}, {rendered_fields}"
    log_method = getattr(logger, level, logger.info)
    log_method(message)


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
    callback_context.setdefault("created_at", callback_context.get("created_at") or now_ms)
    callback_context["updated_at"] = now_ms
    return callback_context


async def _save_host_remote_callback_context(task_id, callback_context, ttl_seconds=None):
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
        from arq import create_pool
        from arq.connections import RedisSettings
        from core.redis_config import REDIS_CONFIG

        redis_settings = RedisSettings(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            password=REDIS_CONFIG["password"],
            database=REDIS_CONFIG["database"],
        )
        _host_remote_callback_pool = await create_pool(redis_settings)

    return _host_remote_callback_pool


async def store_host_remote_callback_context(task_id, params, ctx=None, ttl_seconds=None):
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
    await _save_host_remote_callback_context(task_id, callback_context, ttl_seconds)
    log_host_remote_event(
        "context_stored",
        task_id,
        execution="waiting_callback",
        delivery="not_ready",
    )


async def mark_host_remote_submit_accepted(task_id):
    deadline_at = _now_ms() + HOST_REMOTE_CALLBACK_DEADLINE_SECONDS * 1000
    updated_context = await update_host_remote_callback_context(
        task_id,
        callback_deadline_at=deadline_at,
        last_error=None,
    )
    log_host_remote_event(
        "callback_deadline_started",
        task_id,
        execution=(updated_context or {}).get("status", {}).get("execution"),
        delivery=(updated_context or {}).get("status", {}).get("delivery"),
        callback_deadline_at=deadline_at,
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

    if callback_context.get("raw_callback") is not None:
        log_host_remote_event(
            "callback_duplicate",
            task_id,
            execution=(callback_context.get("status") or {}).get("execution"),
            delivery=(callback_context.get("status") or {}).get("delivery"),
        )
        return callback_context

    updated_context = await update_host_remote_callback_context(
        task_id,
        raw_callback=payload,
        callback_received_at=_now_ms(),
        last_error=None,
        status={"execution": "execution_finished"},
    )
    log_host_remote_event("callback_received", task_id, execution="execution_finished")
    return updated_context


async def mark_host_remote_processing_enqueued(task_id, processing_job_id=None):
    updated_context = await update_host_remote_callback_context(
        task_id,
        process_enqueued_at=_now_ms(),
        processing_job_id=processing_job_id or get_host_remote_processing_job_id(task_id),
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
        key = raw_key.decode() if isinstance(raw_key, (bytes, bytearray)) else str(raw_key)
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
