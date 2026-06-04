import json
import os

HOST_REMOTE_CALLBACK_HANDLER = "host_remote.callback"
HOST_REMOTE_CALLBACK_CONTEXT_TTL_SECONDS = int(
    os.getenv("HOST_REMOTE_CALLBACK_CONTEXT_TTL_SECONDS", "3600")
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
    callback_context = {
        "ctx": _make_json_safe_dict(ctx or {}),
        "params": dict(params or {}),
    }
    redis_pool = await _get_host_remote_callback_pool()
    await redis_pool.set(
        _build_callback_context_key(task_id),
        json.dumps(callback_context),
        ex=ttl_seconds or HOST_REMOTE_CALLBACK_CONTEXT_TTL_SECONDS,
    )


async def load_host_remote_callback_context(task_id):
    redis_pool = await _get_host_remote_callback_pool()
    callback_context = await redis_pool.get(_build_callback_context_key(task_id))
    if not callback_context:
        return None

    if isinstance(callback_context, (bytes, bytearray)):
        callback_context = callback_context.decode()

    return json.loads(callback_context)


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
