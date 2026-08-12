import asyncio

import pytest

from core.infra.redis_client import GatedRedis, RedisPoolTimeoutError


@pytest.mark.asyncio
async def test_gated_redis_times_out_when_pool_is_exhausted():
    client = GatedRedis(
        host="127.0.0.1",
        port=1,
        db=0,
        decode_responses=True,
        max_connections=1,
        pool_timeout_seconds=0.05,
        socket_connect_timeout=0.01,
        socket_timeout=0.01,
    )
    # 直接占用门闩，模拟在途命令占满池
    await client._command_gate.acquire()
    try:
        with pytest.raises(RedisPoolTimeoutError):
            await client.execute_command("PING")
        assert client.pool_timeout_total == 1
        assert client.pool_exhaustion_total == 1
    finally:
        client._command_gate.release()
        await client.aclose()


@pytest.mark.asyncio
async def test_gated_redis_waits_then_proceeds_when_slot_frees():
    client = GatedRedis(
        host="127.0.0.1",
        port=1,
        db=0,
        decode_responses=True,
        max_connections=1,
        pool_timeout_seconds=1,
        socket_connect_timeout=0.01,
        socket_timeout=0.01,
    )
    await client._command_gate.acquire()

    async def release_later():
        await asyncio.sleep(0.05)
        client._command_gate.release()

    releaser = asyncio.create_task(release_later())
    # 释放后门闩可获得，但真实 Redis 不可达；至少验证等待后能进入 execute
    with pytest.raises(Exception):
        await client.execute_command("PING")
    await releaser
    assert client.pool_wait_seconds_total > 0
    await client.aclose()
