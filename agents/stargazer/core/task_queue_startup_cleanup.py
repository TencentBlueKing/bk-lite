"""启动时安全清理 Redis 中已失去对应 ARQ job 的任务标记。"""

import asyncio
import math
import os
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Mapping


LOCK_KEY = b"stargazer:maintenance:startup-orphan-cleanup"
QUEUE_KEY = b"arq:queue"
MARKER_PATTERNS = (b"task:running:*", b"task:dedupe:*")
IN_PROGRESS_PREFIX = b"arq:in-progress:"

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
        if not isinstance(self.max_markers, int) or isinstance(self.max_markers, bool):
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

    token = uuid.uuid4().hex.encode()
    lock_acquired = await redis.set(
        LOCK_KEY, token, nx=True, ex=config.lock_ttl_seconds
    )
    if not lock_acquired:
        return _result(status="skipped", reason="lock_not_acquired")

    scanned = candidates_count = deleted = preserved = errors = 0
    truncated = False
    candidates: list[tuple[bytes, bytes]] = []
    try:
        try:
            async with asyncio.timeout(config.timeout_seconds):
                for pattern in MARKER_PATTERNS:
                    async for raw_marker_key in redis.scan_iter(
                        match=pattern, count=500
                    ):
                        if scanned >= config.max_markers:
                            truncated = True
                            break
                        scanned += 1
                        marker_key = _as_bytes(raw_marker_key)
                        marker_value = await redis.get(marker_key)
                        job_id = _marker_job_id(marker_value)
                        if job_id is None:
                            errors += 1
                            preserved += 1
                        elif await redis.zscore(QUEUE_KEY, job_id) is not None:
                            preserved += 1
                        elif await redis.exists(IN_PROGRESS_PREFIX + job_id):
                            preserved += 1
                        else:
                            candidates.append((marker_key, job_id))
                        if scanned >= config.max_markers:
                            truncated = True
                            break
                    if truncated:
                        break

                candidates_count = len(candidates)
                if candidates:
                    await sleep(config.confirm_delay_seconds)
                for marker_key, job_id in candidates:
                    try:
                        did_delete = await redis.eval(
                            _DELETE_CONFIRMED_ORPHAN_LUA,
                            3,
                            marker_key,
                            QUEUE_KEY,
                            IN_PROGRESS_PREFIX + job_id,
                            job_id,
                        )
                    except Exception:
                        errors += 1
                        preserved += 1
                        continue
                    if did_delete:
                        deleted += 1
                    else:
                        preserved += 1
        except TimeoutError:
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
    finally:
        try:
            await redis.eval(_RELEASE_LOCK_LUA, 1, LOCK_KEY, token)
        except Exception:
            pass

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


def _as_bytes(value: bytes | str) -> bytes:
    return value if isinstance(value, bytes) else value.encode()
