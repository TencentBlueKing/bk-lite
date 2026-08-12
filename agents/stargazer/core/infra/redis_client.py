"""Stargazer 普通异步 Redis Client 生命周期。"""

from __future__ import annotations

import asyncio
import os
import time

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import MaxConnectionsError

from core.infra.redis_config import REDIS_CONFIG

# 对齐配置采集目标并发意向（默认 2000）并留租约/余量
_DEFAULT_MAX_CONNECTIONS = 2560
_DEFAULT_POOL_TIMEOUT_SECONDS = 2.0

_redis_client: "GatedRedis | None" = None
_redis_lock = asyncio.Lock()


class RedisPoolTimeoutError(TimeoutError):
    """借连接等待超过 REDIS_POOL_TIMEOUT。"""


def _pool_timeout_seconds() -> float:
    return float(
        os.getenv("REDIS_POOL_TIMEOUT", str(_DEFAULT_POOL_TIMEOUT_SECONDS))
    )


def _max_connections() -> int:
    return int(
        os.getenv("REDIS_MAX_CONNECTIONS", str(_DEFAULT_MAX_CONNECTIONS))
    )


def is_redis_pool_exhaustion(exc: BaseException) -> bool:
    if isinstance(exc, (MaxConnectionsError, RedisPoolTimeoutError)):
        return True
    if isinstance(exc, RedisConnectionError):
        return "too many connections" in str(exc).lower()
    return False


def is_credential_state_redis_error(exc: BaseException) -> bool:
    """凭据亲和/冷冻路径可隔离的 Redis 故障（含池耗尽）。"""
    if is_redis_pool_exhaustion(exc):
        return True
    if isinstance(exc, (RedisConnectionError, OSError, TimeoutError)):
        return True
    return False


class GatedRedis(Redis):
    """用信号量限制在途命令，池满时有限等待而非立刻 MaxConnectionsError。"""

    def __init__(
        self,
        *args,
        pool_timeout_seconds: float = _DEFAULT_POOL_TIMEOUT_SECONDS,
        max_connections: int = _DEFAULT_MAX_CONNECTIONS,
        **kwargs,
    ) -> None:
        kwargs.setdefault("max_connections", max_connections)
        super().__init__(*args, **kwargs)
        self._pool_timeout_seconds = float(pool_timeout_seconds)
        self._command_gate = asyncio.Semaphore(int(max_connections))
        self.pool_wait_seconds_total = 0.0
        self.pool_timeout_total = 0
        self.pool_exhaustion_total = 0

    async def execute_command(self, *args, **kwargs):
        started = time.monotonic()
        try:
            await asyncio.wait_for(
                self._command_gate.acquire(),
                timeout=self._pool_timeout_seconds,
            )
        except TimeoutError as exc:
            self.pool_timeout_total += 1
            self.pool_exhaustion_total += 1
            raise RedisPoolTimeoutError(
                "redis connection pool wait timed out"
            ) from exc
        waited = time.monotonic() - started
        if waited > 0:
            self.pool_wait_seconds_total += waited
        try:
            try:
                return await super().execute_command(*args, **kwargs)
            except Exception as exc:
                if is_redis_pool_exhaustion(exc):
                    self.pool_exhaustion_total += 1
                raise
        finally:
            self._command_gate.release()


def build_redis_client() -> GatedRedis:
    max_connections = _max_connections()
    return GatedRedis(
        host=REDIS_CONFIG["host"],
        port=REDIS_CONFIG["port"],
        password=REDIS_CONFIG["password"],
        db=REDIS_CONFIG["database"],
        decode_responses=True,
        health_check_interval=30,
        socket_connect_timeout=float(
            os.getenv("REDIS_CONNECT_TIMEOUT", "5")
        ),
        socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "5")),
        max_connections=max_connections,
        pool_timeout_seconds=_pool_timeout_seconds(),
        retry_on_timeout=True,
    )


async def get_redis_client() -> GatedRedis:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    async with _redis_lock:
        if _redis_client is None:
            _redis_client = build_redis_client()
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client
    async with _redis_lock:
        client = _redis_client
        _redis_client = None
    if client is not None:
        await client.aclose()


def register_redis_lifecycle(app) -> None:
    @app.listener("before_server_start")
    async def connect_redis(app, _loop):
        client = await get_redis_client()
        await client.ping()
        app.ctx.redis = client

    @app.listener("after_server_stop")
    async def disconnect_redis(_app, _loop):
        await close_redis_client()
