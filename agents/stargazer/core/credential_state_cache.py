import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from arq import create_pool
from arq.connections import RedisSettings

from core.redis_config import REDIS_CONFIG


class CredentialStateCache:
    """基于 Redis 的 host-credential 运行态缓存。"""

    SUCCESS_TTL_SECONDS = 7 * 24 * 3600
    FAILURE_TTL_SECONDS = 24 * 3600
    EVENT_RETENTION_SECONDS = 7 * 24 * 3600
    COOLDOWN_HOURS = {1: 1, 2: 4, 3: 24}

    @classmethod
    async def get_success_credential(cls, collect_task_id: Any, host: str) -> str:
        pool = await cls._create_pool()
        try:
            value = await pool.get(cls._success_key(collect_task_id, host))
            if isinstance(value, (bytes, bytearray)):
                return value.decode()
            return str(value or "")
        finally:
            await pool.close()

    @classmethod
    async def get_failure_state(cls, collect_task_id: Any, host: str, credential_id: str) -> dict:
        pool = await cls._create_pool()
        try:
            value = await pool.get(cls._failure_key(collect_task_id, host, credential_id))
            if not value:
                return {}
            if isinstance(value, (bytes, bytearray)):
                value = value.decode()
            return json.loads(value)
        finally:
            await pool.close()

    @classmethod
    async def mark_success(cls, collect_task_id: Any, host: str, credential_id: str) -> None:
        pool = await cls._create_pool()
        try:
            await pool.set(cls._success_key(collect_task_id, host), credential_id, ex=cls.SUCCESS_TTL_SECONDS)
            pattern = cls._failure_pattern(collect_task_id, host)
            async for key in cls._scan_keys(pool, pattern):
                await pool.delete(key)
        finally:
            await pool.close()

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
        pool = await cls._create_pool()
        try:
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
        finally:
            await pool.close()

    @classmethod
    async def clear_success(cls, collect_task_id: Any, host: str) -> None:
        pool = await cls._create_pool()
        try:
            await pool.delete(cls._success_key(collect_task_id, host))
        finally:
            await pool.close()

    @classmethod
    async def append_result_event(cls, event: dict) -> None:
        pool = await cls._create_pool()
        try:
            finished_at = str(event.get("finished_at") or datetime.now(timezone.utc).isoformat())
            score = cls._event_score(finished_at)
            payload = {**dict(event or {}), "event_id": uuid.uuid4().hex, "finished_at": finished_at}
            await pool.zadd(cls._event_stream_key(), {json.dumps(payload, ensure_ascii=False): score})
            await pool.zremrangebyscore(cls._event_stream_key(), 0, score - cls.EVENT_RETENTION_SECONDS * 1000)
        finally:
            await pool.close()

    @classmethod
    async def list_result_events(cls, since: str | None = None, limit: int = 500) -> list[dict]:
        pool = await cls._create_pool()
        try:
            min_score = "-inf"
            if since:
                min_score = f"({cls._event_score(since)}"
            raw_items = await pool.zrangebyscore(cls._event_stream_key(), min=min_score, max="+inf", start=0, num=limit)
            events = []
            for item in raw_items or []:
                if isinstance(item, (bytes, bytearray)):
                    item = item.decode()
                events.append(json.loads(item))
            return events
        finally:
            await pool.close()

    @classmethod
    async def _create_pool(cls):
        redis_settings = RedisSettings(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            password=REDIS_CONFIG["password"],
            database=REDIS_CONFIG["database"],
        )
        return await create_pool(redis_settings)

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
    def _push_cursor_key() -> str:
        return "collect:credential:push_cursor"

    @classmethod
    async def get_push_cursor(cls) -> str:
        pool = await cls._create_pool()
        try:
            value = await pool.get(cls._push_cursor_key())
            if isinstance(value, (bytes, bytearray)):
                return value.decode()
            return str(value or "")
        finally:
            await pool.close()

    @classmethod
    async def set_push_cursor(cls, since: str) -> None:
        if not since:
            return
        pool = await cls._create_pool()
        try:
            await pool.set(cls._push_cursor_key(), since)
        finally:
            await pool.close()

    @staticmethod
    def _event_score(value: str) -> int:
        normalized = str(value or "").strip().replace("Z", "+00:00")
        if not normalized:
            return int(datetime.now(timezone.utc).timestamp() * 1000)
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)

    @classmethod
    def cooldown_hours_for(cls, cooldown_level: int) -> int:
        return cls.COOLDOWN_HOURS.get(int(cooldown_level or 0), 24)

    @classmethod
    def cooldown_seconds_for(cls, cooldown_level: int) -> int:
        return cls.cooldown_hours_for(cooldown_level) * 3600