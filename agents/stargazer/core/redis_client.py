"""Stargazer 普通异步 Redis Client 生命周期。"""

from __future__ import annotations

import asyncio
import os

from redis.asyncio import Redis

from core.redis_config import REDIS_CONFIG

_redis_client: Redis | None = None
_redis_lock = asyncio.Lock()


def build_redis_client() -> Redis:
    return Redis(
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
        max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "100")),
        retry_on_timeout=True,
    )


async def get_redis_client() -> Redis:
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
