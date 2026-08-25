import asyncio
import base64
import binascii
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from core.infra.redis_client import get_redis_client

_APPEND_RESULT_EVENT_LUA = """
if redis.call("EXISTS", KEYS[2]) == 1 then
  return 0
end
local score = tonumber(ARGV[1])
local current = tonumber(redis.call("GET", KEYS[3]) or "0")
if score <= current then
  return -1
end
redis.call("SET", KEYS[3], score)
redis.call("ZADD", KEYS[1], ARGV[1], ARGV[2])
redis.call("SET", KEYS[2], "1", "EX", ARGV[3])
redis.call("ZREMRANGEBYSCORE", KEYS[1], 0, ARGV[4])
return 1
"""

_PROPOSE_EVENT_SCORE_LUA = """
local requested = tonumber(ARGV[1])
local current = tonumber(redis.call("GET", KEYS[1]) or "0")
return math.max(requested, current + 1)
"""


class CredentialStateCache:
    """基于 Redis 的 host-credential 运行态缓存。"""

    SUCCESS_TTL_SECONDS = 7 * 24 * 3600
    FAILURE_TTL_SECONDS = 24 * 3600
    EVENT_RETENTION_SECONDS = 7 * 24 * 3600
    ROLLBACK_CURSOR_SAFETY_SECONDS = 60
    COOLDOWN_HOURS = {1: 1, 2: 4, 3: 24}
    _STREAM_CURSOR_FIELD = "_stream_cursor"
    _APPEND_EVENT_LOCK = asyncio.Lock()

    @classmethod
    async def get_success_credential(cls, collect_task_id: Any, host: str) -> str:
        pool = await cls._get_or_create_pool()
        value = await pool.get(cls._success_key(collect_task_id, host))
        if isinstance(value, (bytes, bytearray)):
            return value.decode()
        return str(value or "")

    @classmethod
    async def get_failure_state(cls, collect_task_id: Any, host: str, credential_id: str) -> dict:
        pool = await cls._get_or_create_pool()
        value = await pool.get(cls._failure_key(collect_task_id, host, credential_id))
        if not value:
            return {}
        if isinstance(value, (bytes, bytearray)):
            value = value.decode()
        return json.loads(value)

    @classmethod
    async def mark_success(cls, collect_task_id: Any, host: str, credential_id: str) -> None:
        pool = await cls._get_or_create_pool()
        await pool.set(cls._success_key(collect_task_id, host), credential_id, ex=cls.SUCCESS_TTL_SECONDS)
        pattern = cls._failure_pattern(collect_task_id, host)
        async for key in cls._scan_keys(pool, pattern):
            await pool.delete(key)

    @classmethod
    async def mark_failure(
        cls,
        collect_task_id: Any,
        host: str,
        credential_id: str,
        error_message: str,
        cooldown_level: int,
        consecutive_failures: int,
        next_retry_at: str,
    ) -> None:
        pool = await cls._get_or_create_pool()
        payload = {
            "is_cooled": True,
            "error_message": error_message or "",
            "cooldown_level": cooldown_level,
            "consecutive_failures": consecutive_failures,
            "next_retry_at": next_retry_at,
        }
        await pool.set(
            cls._failure_key(collect_task_id, host, credential_id),
            json.dumps(payload),
            ex=cls.cooldown_seconds_for(cooldown_level),
        )

    @classmethod
    async def clear_success(cls, collect_task_id: Any, host: str) -> None:
        pool = await cls._get_or_create_pool()
        await pool.delete(cls._success_key(collect_task_id, host))

    @classmethod
    async def append_result_event(cls, event: dict) -> None:
        # 单进程内先串行，跨 Pod 再由 Redis CAS 收敛，避免高并发下无界争抢。
        async with cls._APPEND_EVENT_LOCK:
            await cls._append_result_event(event)

    @classmethod
    async def _append_result_event(cls, event: dict) -> None:
        pool = await cls._get_or_create_pool()
        event_id = str(event.get("event_id") or uuid.uuid4().hex)
        observed_at = str(event.get("finished_at") or datetime.now(timezone.utc).isoformat())
        requested_score = cls._event_score(observed_at)
        for _attempt in range(256):
            score = int(
                await pool.eval(
                    _PROPOSE_EVENT_SCORE_LUA,
                    1,
                    cls._event_clock_key(),
                    requested_score,
                )
            )
            finished_at = datetime.fromtimestamp(
                score / 1000, timezone.utc
            ).isoformat(timespec="milliseconds")
            payload = {
                **dict(event or {}),
                "event_id": event_id,
                "observed_at": str(event.get("observed_at") or observed_at),
                "finished_at": finished_at,
            }
            # 成员仍保持旧版可直接 json.loads 的形态，代码回滚不会读坏存量事件。
            member = cls._encode_event_member(payload)
            committed = int(
                await pool.eval(
                    _APPEND_RESULT_EVENT_LUA,
                    3,
                    cls._event_stream_key(),
                    cls._event_dedupe_key(event_id),
                    cls._event_clock_key(),
                    score,
                    member,
                    cls.EVENT_RETENTION_SECONDS,
                    score - cls.EVENT_RETENTION_SECONDS * 1000,
                )
            )
            if committed >= 0:
                return
        raise RuntimeError("result event stream is too busy; retry append")

    @classmethod
    async def list_result_events(cls, since: str | None = None, limit: int = 500) -> list[dict]:
        pool = await cls._get_or_create_pool()
        bounded_limit = max(1, int(limit or 500))
        cursor_time, cursor_member = cls._parse_event_cursor(since)
        cursor_score = cls._event_score(cursor_time) if cursor_time else None
        # 旧时间戳游标在升级后的首次读取允许边界重投，依靠 event_id 去重；
        # 这比继续沿用排他游标并永久丢失同毫秒事件更安全。
        min_score = cursor_score if cursor_score is not None else "-inf"
        events: list[dict] = []
        chunk_size = min(max(bounded_limit, 100), 1000)
        offset = 0
        while len(events) < bounded_limit:
            raw_items = await pool.zrangebyscore(
                cls._event_stream_key(),
                min=min_score,
                max="+inf",
                start=offset,
                num=chunk_size,
                withscores=True,
            )
            if not raw_items:
                break
            offset += len(raw_items)
            for item, score in raw_items:
                member = cls._text(item)
                if cursor_member and score == cursor_score and member <= cursor_member:
                    continue
                event = cls._decode_event_member(member)
                event[cls._STREAM_CURSOR_FIELD] = cls._encode_cursor_member(member)
                events.append(event)
                if len(events) >= bounded_limit:
                    return events[:bounded_limit]
        return events

    @classmethod
    async def _get_or_create_pool(cls):
        return await get_redis_client()

    @classmethod
    async def close_pool(cls) -> None:
        # 共享 Client 只由 core.infra.redis_client 的 Sanic 生命周期统一关闭。
        return None

    @staticmethod
    async def _scan_keys(pool, pattern: str):
        cursor = 0
        while True:
            cursor, keys = await pool.scan(cursor=cursor, match=pattern, count=100)
            for key in keys:
                yield key
            if cursor == 0:
                break

    @staticmethod
    def _success_key(collect_task_id: Any, host: str) -> str:
        return f"collect:task:{collect_task_id}:host:{host}:success"

    @staticmethod
    def _failure_key(collect_task_id: Any, host: str, credential_id: str) -> str:
        return f"collect:task:{collect_task_id}:host:{host}:credential:{credential_id}:failure"

    @staticmethod
    def _failure_pattern(collect_task_id: Any, host: str) -> str:
        return f"collect:task:{collect_task_id}:host:{host}:credential:*:failure"

    @staticmethod
    def _event_stream_key() -> str:
        return "collect:credential:events"

    @staticmethod
    def _event_dedupe_key(event_id: str) -> str:
        return f"collect:credential:event:{event_id}"

    @staticmethod
    def _event_clock_key() -> str:
        return "collect:credential:event_clock_ms"

    @staticmethod
    def _push_cursor_key() -> str:
        return "collect:credential:push_cursor"

    @staticmethod
    def _push_cursor_v2_key() -> str:
        return "collect:credential:push_cursor:v2"

    @classmethod
    async def get_push_cursor(cls) -> str:
        pool = await cls._get_or_create_pool()
        value = await pool.get(cls._push_cursor_v2_key())
        if not value:
            value = await pool.get(cls._push_cursor_key())
        if isinstance(value, (bytes, bytearray)):
            return value.decode()
        return str(value or "")

    @classmethod
    async def set_push_cursor(cls, since: str) -> None:
        if not since:
            return
        pool = await cls._get_or_create_pool()
        await pool.set(cls._push_cursor_v2_key(), since)
        # 旧镜像只认识排他 ISO 时间游标，也不会遵守新 event_clock。
        # 安全滞后允许滚动回退期间的旧 writer 有界重放；下游 event_id 负责去重。
        legacy_since, _member = cls._parse_event_cursor(since)
        rollback_floor = datetime.now(timezone.utc) - timedelta(
            seconds=cls.ROLLBACK_CURSOR_SAFETY_SECONDS
        )
        rollback_floor_score = cls._event_score(rollback_floor.isoformat())
        legacy_score = cls._event_score(legacy_since)
        rollback_safe_since = (
            legacy_since
            if legacy_score <= rollback_floor_score
            else rollback_floor.isoformat(timespec="milliseconds")
        )
        await pool.set(cls._push_cursor_key(), rollback_safe_since)

    @staticmethod
    def _event_score(value: str) -> int:
        normalized = str(value or "").strip().replace("Z", "+00:00")
        if not normalized:
            return int(datetime.now(timezone.utc).timestamp() * 1000)
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)

    @staticmethod
    def _decode_event_member(item) -> dict:
        if isinstance(item, (bytes, bytearray)):
            item = item.decode()
        payload = str(item)
        if "\0" in payload:
            _event_id, payload = payload.split("\0", 1)
        return json.loads(payload)

    @staticmethod
    def _encode_event_member(event: dict) -> str:
        payload = dict(event or {})
        payload.pop(CredentialStateCache._STREAM_CURSOR_FIELD, None)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _encode_cursor_member(member: str) -> str:
        encoded = base64.urlsafe_b64encode(member.encode("utf-8")).decode("ascii")
        return encoded.rstrip("=")

    @staticmethod
    def _decode_cursor_member(value: str) -> str:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("ascii")).decode("utf-8")

    @staticmethod
    def _text(value) -> str:
        if isinstance(value, (bytes, bytearray)):
            return value.decode()
        return str(value)

    @staticmethod
    def _parse_event_cursor(value: str | None) -> tuple[str, str]:
        cursor = str(value or "")
        if "|m:" not in cursor:
            return cursor, ""
        cursor_time, encoded_member = cursor.rsplit("|m:", 1)
        try:
            return cursor_time, CredentialStateCache._decode_cursor_member(encoded_member)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return cursor_time, ""

    @staticmethod
    def event_cursor(event: dict) -> str:
        finished_at = str((event or {}).get("finished_at") or "")
        cursor_member = str((event or {}).get(CredentialStateCache._STREAM_CURSOR_FIELD) or "")
        if not cursor_member and event:
            cursor_member = CredentialStateCache._encode_cursor_member(
                CredentialStateCache._encode_event_member(event)
            )
        return f"{finished_at}|m:{cursor_member}" if finished_at and cursor_member else finished_at

    @classmethod
    def cooldown_hours_for(cls, cooldown_level: int) -> int:
        return cls.COOLDOWN_HOURS.get(int(cooldown_level or 0), 24)

    @classmethod
    def cooldown_seconds_for(cls, cooldown_level: int) -> int:
        return cls.cooldown_hours_for(cooldown_level) * 3600


async def close_credential_state_cache_pool(_context=None) -> None:
    await CredentialStateCache.close_pool()


def register_credential_state_cache_lifecycle(app) -> None:
    @app.listener("after_server_stop")
    async def stop_credential_state_cache(_app, _loop):
        await close_credential_state_cache_pool()
