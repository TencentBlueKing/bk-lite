"""启动时安全清理 Redis 中已失去对应 ARQ job 的任务标记。"""

import asyncio
import json
import math
import os
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Mapping

from redis.exceptions import ResponseError

LOCK_KEY = b"stargazer:maintenance:startup-orphan-cleanup"
QUEUE_KEY = b"arq:queue"
MARKER_PATTERNS = (b"task:running:*", b"task:dedupe:*")
IN_PROGRESS_PREFIX = b"arq:in-progress:"
RUNNING_MARKER_PREFIX = b"task:running:"
HOST_REMOTE_CALLBACK_CONTEXT_PREFIX = b"host_remote:callback_context:"
_VALID_CALLBACK_EXECUTIONS = frozenset(
    {"waiting_callback", "execution_finished", "callback_timeout"}
)
_INVALID_CALLBACK_CONTEXT_RESULT = -1

_DELETE_CONFIRMED_ORPHAN_LUA = """
local marker_value = redis.call('GET', KEYS[1])
if marker_value ~= ARGV[1] then
    return 0
end
if redis.call('ZSCORE', KEYS[2], ARGV[1]) then
    return 0
end
if redis.call('EXISTS', KEYS[3]) ~= 0 then
    return 0
end
if KEYS[4] ~= '' then
    local callback_value = redis.call('GET', KEYS[4])
    if callback_value then
        local decoded_ok, callback_context = pcall(cjson.decode, callback_value)
        if not decoded_ok or type(callback_context) ~= 'table' then
            return -1
        end
        local status = callback_context['status']
        if type(status) ~= 'table' or type(status['execution']) ~= 'string' then
            return -1
        end
        local execution = status['execution']
        if execution ~= 'waiting_callback'
            and execution ~= 'execution_finished'
            and execution ~= 'callback_timeout'
        then
            return -1
        end
        if execution == 'waiting_callback'
        then
            return 0
        end
    end
end
return redis.call('DEL', KEYS[1])
"""

_RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class StartupCleanupConfigError(ValueError):
    """启动清理配置无法保证安全删除时抛出。"""


class CallbackContextError(ValueError):
    """损坏 callback context 时，禁止删除对应 marker。"""


@dataclass(frozen=True)
class StartupCleanupConfig:
    enabled: bool = True
    confirm_delay_seconds: float = 5
    max_markers: int = 10_000
    timeout_seconds: float = 30
    lock_ttl_seconds: int = 60

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise StartupCleanupConfigError("开关必须是布尔值")
        if not _is_finite_number(self.confirm_delay_seconds):
            raise StartupCleanupConfigError("确认延迟必须是有限数字")
        if not isinstance(self.max_markers, int) or isinstance(
            self.max_markers, bool
        ):
            raise StartupCleanupConfigError("扫描上限必须是整数")
        if not _is_finite_number(self.timeout_seconds):
            raise StartupCleanupConfigError("总超时必须是有限数字")
        if not isinstance(self.lock_ttl_seconds, int) or isinstance(
            self.lock_ttl_seconds, bool
        ):
            raise StartupCleanupConfigError("锁 TTL 必须是整数")
        if self.confirm_delay_seconds < 0:
            raise StartupCleanupConfigError("确认延迟不能为负数")
        if self.max_markers <= 0:
            raise StartupCleanupConfigError("扫描上限必须为正数")
        if self.timeout_seconds <= 0:
            raise StartupCleanupConfigError("总超时必须为正数")
        if self.lock_ttl_seconds <= 0:
            raise StartupCleanupConfigError("锁 TTL 必须为正数")
        if self.timeout_seconds >= self.lock_ttl_seconds:
            raise StartupCleanupConfigError("总超时必须小于锁 TTL")

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None
    ) -> "StartupCleanupConfig":
        values = os.environ if env is None else env
        enabled = _parse_bool(
            values.get("TASK_QUEUE_STARTUP_ORPHAN_CLEANUP_ENABLED", "true"),
            "TASK_QUEUE_STARTUP_ORPHAN_CLEANUP_ENABLED",
        )
        confirm_delay_seconds = _parse_float(
            values.get("TASK_QUEUE_STARTUP_ORPHAN_CONFIRM_DELAY_SECONDS", "5"),
            "TASK_QUEUE_STARTUP_ORPHAN_CONFIRM_DELAY_SECONDS",
        )
        max_markers = _parse_int(
            values.get("TASK_QUEUE_STARTUP_ORPHAN_MAX_MARKERS", "10000"),
            "TASK_QUEUE_STARTUP_ORPHAN_MAX_MARKERS",
        )
        timeout_seconds = _parse_float(
            values.get("TASK_QUEUE_STARTUP_ORPHAN_TIMEOUT_SECONDS", "30"),
            "TASK_QUEUE_STARTUP_ORPHAN_TIMEOUT_SECONDS",
        )
        lock_ttl_seconds = _parse_int(
            values.get("TASK_QUEUE_STARTUP_ORPHAN_LOCK_TTL_SECONDS", "60"),
            "TASK_QUEUE_STARTUP_ORPHAN_LOCK_TTL_SECONDS",
        )
        return cls(
            enabled=enabled,
            confirm_delay_seconds=confirm_delay_seconds,
            max_markers=max_markers,
            timeout_seconds=timeout_seconds,
            lock_ttl_seconds=lock_ttl_seconds,
        )


@dataclass(frozen=True)
class StartupCleanupResult:
    status: Literal["success", "skipped", "warning"]
    reason: str | None
    scanned: int
    candidates: int
    deleted: int
    preserved: int
    errors: int
    truncated: bool


async def cleanup_startup_orphan_markers(
    redis,
    config: StartupCleanupConfig,
    *,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> StartupCleanupResult:
    """双阶段确认后，仅删除未在队列或执行中的 marker。"""
    if not config.enabled:
        return _result(status="skipped", reason="disabled")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + config.timeout_seconds
    token = uuid.uuid4().hex.encode()
    scanned = candidates_count = deleted = preserved = errors = 0
    truncated = False
    candidates: list[tuple[bytes, bytes, bytes]] = []
    lock_acquired = False
    timed_out = False
    early_result: StartupCleanupResult | None = None
    try:
        try:
            async with asyncio.timeout_at(deadline):
                lock_acquired = await redis.set(
                    LOCK_KEY, token, nx=True, ex=config.lock_ttl_seconds
                )
                if not lock_acquired:
                    early_result = _result(
                        status="skipped", reason="lock_not_acquired"
                    )
                else:
                    for pattern in MARKER_PATTERNS:
                        async for raw_marker_key in redis.scan_iter(
                            match=pattern, count=500
                        ):
                            if scanned >= config.max_markers:
                                truncated = True
                                break
                            scanned += 1
                            marker_key = _as_bytes(raw_marker_key)
                            callback_context_key = _callback_context_key(
                                marker_key
                            )
                            try:
                                marker_value = await redis.get(marker_key)
                                job_id = _marker_job_id(marker_value)
                                if job_id is None:
                                    errors += 1
                                    preserved += 1
                                elif (
                                    await redis.zscore(QUEUE_KEY, job_id)
                                    is not None
                                ):
                                    preserved += 1
                                elif await redis.exists(
                                    IN_PROGRESS_PREFIX + job_id
                                ):
                                    preserved += 1
                                elif (
                                    callback_context_key
                                    and await _is_waiting_callback(
                                        redis, callback_context_key
                                    )
                                ):
                                    preserved += 1
                                else:
                                    candidates.append(
                                        (
                                            marker_key,
                                            job_id,
                                            callback_context_key,
                                        )
                                    )
                            except (ResponseError, CallbackContextError):
                                errors += 1
                                preserved += 1
                            if scanned >= config.max_markers:
                                truncated = True
                                break
                        if truncated:
                            break

                    candidates_count = len(candidates)
                    if candidates:
                        await sleep(config.confirm_delay_seconds)
                    for marker_key, job_id, callback_context_key in candidates:
                        try:
                            did_delete = await redis.eval(
                                _DELETE_CONFIRMED_ORPHAN_LUA,
                                4,
                                marker_key,
                                QUEUE_KEY,
                                IN_PROGRESS_PREFIX + job_id,
                                callback_context_key,
                                job_id,
                            )
                        except ResponseError:
                            errors += 1
                            preserved += 1
                            continue
                        if did_delete == 1:
                            deleted += 1
                        else:
                            preserved += 1
                            if did_delete == _INVALID_CALLBACK_CONTEXT_RESULT:
                                errors += 1
        except TimeoutError:
            timed_out = True
    finally:
        try:
            remaining = deadline - loop.time()
            if lock_acquired and remaining > 0:
                async with asyncio.timeout(remaining):
                    await redis.eval(_RELEASE_LOCK_LUA, 1, LOCK_KEY, token)
            elif lock_acquired:
                timed_out = True
        except TimeoutError:
            timed_out = True
        except Exception:
            pass

    if timed_out or loop.time() >= deadline:
        return _result(
            status="warning",
            reason="timeout",
            scanned=scanned,
            candidates=candidates_count,
            deleted=deleted,
            preserved=preserved,
            errors=errors,
            truncated=truncated,
        )
    if early_result is not None:
        return early_result
    if truncated:
        return _result(
            status="warning",
            reason="limit_reached",
            scanned=scanned,
            candidates=candidates_count,
            deleted=deleted,
            preserved=preserved,
            errors=errors,
            truncated=True,
        )
    if errors:
        return _result(
            status="warning",
            reason="marker_errors",
            scanned=scanned,
            candidates=candidates_count,
            deleted=deleted,
            preserved=preserved,
            errors=errors,
        )
    return _result(
        status="success",
        scanned=scanned,
        candidates=candidates_count,
        deleted=deleted,
        preserved=preserved,
    )


def _result(
    *,
    status: Literal["success", "skipped", "warning"],
    reason: str | None = None,
    scanned: int = 0,
    candidates: int = 0,
    deleted: int = 0,
    preserved: int = 0,
    errors: int = 0,
    truncated: bool = False,
) -> StartupCleanupResult:
    return StartupCleanupResult(
        status=status,
        reason=reason,
        scanned=scanned,
        candidates=candidates,
        deleted=deleted,
        preserved=preserved,
        errors=errors,
        truncated=truncated,
    )


def _parse_bool(value: str, name: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise StartupCleanupConfigError(f"{name} 必须是布尔值")


def _parse_float(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise StartupCleanupConfigError(f"{name} 必须是数字") from error
    if not math.isfinite(parsed):
        raise StartupCleanupConfigError(f"{name} 必须是有限数字")
    return parsed


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _parse_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise StartupCleanupConfigError(f"{name} 必须是整数") from error
    return parsed


def _marker_job_id(marker_value: object) -> bytes | None:
    if isinstance(marker_value, bytes):
        return marker_value or None
    if isinstance(marker_value, str):
        return marker_value.encode() if marker_value else None
    return None


async def _is_waiting_callback(redis, callback_context_key: bytes) -> bool:
    callback_value = await redis.get(callback_context_key)
    if not callback_value:
        return False
    try:
        if isinstance(callback_value, bytes):
            callback_value = callback_value.decode()
        callback_context = json.loads(callback_value)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CallbackContextError("callback context 不是有效 JSON") from error
    if not isinstance(callback_context, dict):
        raise CallbackContextError("callback context 必须是对象")
    status = callback_context.get("status")
    execution = status.get("execution") if isinstance(status, dict) else None
    if (
        not isinstance(execution, str)
        or execution not in _VALID_CALLBACK_EXECUTIONS
    ):
        raise CallbackContextError("callback context status 非法")
    return execution == "waiting_callback"


def _callback_context_key(marker_key: bytes) -> bytes:
    if not marker_key.startswith(RUNNING_MARKER_PREFIX):
        return b""
    task_id = marker_key.removeprefix(RUNNING_MARKER_PREFIX)
    return HOST_REMOTE_CALLBACK_CONTEXT_PREFIX + task_id if task_id else b""


def _as_bytes(value: bytes | str) -> bytes:
    return value if isinstance(value, bytes) else value.encode()
