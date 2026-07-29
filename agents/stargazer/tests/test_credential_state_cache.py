import asyncio
import shutil
import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager

import pytest
from redis import Redis

import core.credential_state_cache as credential_state_cache
from core.credential_state_cache import (
    CredentialStateCache,
    close_credential_state_cache_pool,
    register_credential_state_cache_lifecycle,
)


class FakeRedisPool:
    def __init__(self, value: bytes = b"credential-1"):
        self.value = value
        self.close_calls = 0

    async def get(self, _key):
        return self.value

    async def close(self):
        self.close_calls += 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_repeated_public_reads_reuse_one_pool(monkeypatch):
    created_pools = []

    async def fake_create_pool(_settings):
        pool = FakeRedisPool()
        created_pools.append(pool)
        return pool

    monkeypatch.setattr(credential_state_cache, "create_pool", fake_create_pool)

    results = [
        await CredentialStateCache.get_success_credential("task-1", "host-1")
        for _ in range(20)
    ]

    assert results == ["credential-1"] * 20
    assert len(created_pools) == 1
    assert created_pools[0].close_calls == 0
    await CredentialStateCache.close_pool()
    assert created_pools[0].close_calls == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_concurrent_public_reads_initialize_one_pool(monkeypatch):
    created_pools = []

    async def fake_create_pool(_settings):
        await asyncio.sleep(0)
        pool = FakeRedisPool()
        created_pools.append(pool)
        return pool

    monkeypatch.setattr(credential_state_cache, "create_pool", fake_create_pool)

    results = await asyncio.gather(
        *(
            CredentialStateCache.get_success_credential("task-1", f"host-{index}")
            for index in range(20)
        )
    )

    assert results == ["credential-1"] * 20
    assert len(created_pools) == 1
    assert created_pools[0].close_calls == 0
    await CredentialStateCache.close_pool()
    assert created_pools[0].close_calls == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_close_pool_is_idempotent_and_next_read_reconnects(monkeypatch):
    created_pools = []

    async def fake_create_pool(_settings):
        pool = FakeRedisPool()
        created_pools.append(pool)
        return pool

    monkeypatch.setattr(credential_state_cache, "create_pool", fake_create_pool)

    await CredentialStateCache.get_success_credential("task-1", "host-1")
    await CredentialStateCache.close_pool()
    await CredentialStateCache.close_pool()
    await CredentialStateCache.get_success_credential("task-1", "host-1")

    assert len(created_pools) == 2
    assert created_pools[0].close_calls == 1
    assert created_pools[1].close_calls == 0
    await CredentialStateCache.close_pool()
    assert created_pools[1].close_calls == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_sanic_shutdown_closes_the_current_loop_pool(monkeypatch):
    created_pools = []

    async def fake_create_pool(_settings):
        pool = FakeRedisPool()
        created_pools.append(pool)
        return pool

    class FakeApp:
        def __init__(self):
            self.listeners = {}

        def listener(self, event):
            def register(callback):
                self.listeners[event] = callback
                return callback

            return register

    monkeypatch.setattr(credential_state_cache, "create_pool", fake_create_pool)
    app = FakeApp()
    register_credential_state_cache_lifecycle(app)

    await CredentialStateCache.get_success_credential("task-1", "host-1")
    await app.listeners["after_server_stop"](app, asyncio.get_running_loop())

    assert len(created_pools) == 1
    assert created_pools[0].close_calls == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_arq_shutdown_closes_the_current_loop_pool(monkeypatch):
    from core.worker import WorkerSettings

    created_pools = []

    async def fake_create_pool(_settings):
        pool = FakeRedisPool()
        created_pools.append(pool)
        return pool

    monkeypatch.setattr(credential_state_cache, "create_pool", fake_create_pool)

    await CredentialStateCache.get_success_credential("task-1", "host-1")
    await WorkerSettings.on_shutdown({})

    assert WorkerSettings.on_shutdown is close_credential_state_cache_pool
    assert len(created_pools) == 1
    assert created_pools[0].close_calls == 1


@pytest.mark.unit
def test_distinct_event_loops_do_not_share_a_pool(monkeypatch):
    created_pools = []

    async def fake_create_pool(_settings):
        pool = FakeRedisPool()
        created_pools.append(pool)
        return pool

    async def read_and_close():
        result = await CredentialStateCache.get_success_credential("task-1", "host-1")
        await CredentialStateCache.close_pool()
        return result

    monkeypatch.setattr(credential_state_cache, "create_pool", fake_create_pool)

    assert asyncio.run(read_and_close()) == "credential-1"
    assert asyncio.run(read_and_close()) == "credential-1"
    assert len(created_pools) == 2
    assert [pool.close_calls for pool in created_pools] == [1, 1]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pool_creation_failure_does_not_poison_reconnect(monkeypatch):
    attempts = 0
    recovered_pool = FakeRedisPool()

    async def flaky_create_pool(_settings):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("redis unavailable")
        return recovered_pool

    monkeypatch.setattr(credential_state_cache, "create_pool", flaky_create_pool)

    with pytest.raises(ConnectionError, match="redis unavailable"):
        await CredentialStateCache.get_success_credential("task-1", "host-1")

    result = await CredentialStateCache.get_success_credential("task-1", "host-1")
    await CredentialStateCache.close_pool()

    assert result == "credential-1"
    assert attempts == 2
    assert recovered_pool.close_calls == 1


@contextmanager
def _redis_server():
    executable = shutil.which("redis-server")
    if executable is None:
        pytest.skip("redis-server is not installed")

    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        port = port_probe.getsockname()[1]

    with tempfile.TemporaryDirectory(prefix="stargazer-credential-cache-") as directory:
        process = subprocess.Popen(
            [
                executable,
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
                "--dir",
                directory,
                "--save",
                "",
                "--appendonly",
                "no",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        client = Redis(host="127.0.0.1", port=port, db=15)
        try:
            deadline = time.monotonic() + 5
            while True:
                try:
                    client.ping()
                    break
                except Exception:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            yield port, client
        finally:
            client.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


@pytest.mark.integration
def test_real_redis_reuses_one_connection_and_reconnects_after_close(monkeypatch):
    async def exercise(client):
        client.flushdb()
        client.set("collect:task:task-1:host:host-1:success", "credential-1")
        before = client.info("stats")["total_connections_received"]

        results = [
            await CredentialStateCache.get_success_credential("task-1", "host-1")
            for _ in range(20)
        ]
        after_reuse = client.info("stats")["total_connections_received"]

        await CredentialStateCache.mark_failure(
            "task-1",
            "host-1",
            "credential-2",
            "authentication failed",
            1,
            1,
            "2026-07-29T00:00:00+00:00",
        )
        assert await CredentialStateCache.get_failure_state(
            "task-1", "host-1", "credential-2"
        ) == {
            "is_cooled": True,
            "error_message": "authentication failed",
            "cooldown_level": 1,
            "consecutive_failures": 1,
            "next_retry_at": "2026-07-29T00:00:00+00:00",
        }
        await CredentialStateCache.mark_success(
            "task-1", "host-1", "credential-2"
        )
        assert (
            await CredentialStateCache.get_success_credential(
                "task-1", "host-1"
            )
            == "credential-2"
        )
        assert (
            await CredentialStateCache.get_failure_state(
                "task-1", "host-1", "credential-2"
            )
            == {}
        )

        event = {
            "finished_at": "2026-07-29T00:00:00+00:00",
            "success": True,
        }
        await CredentialStateCache.append_result_event(event)
        events = await CredentialStateCache.list_result_events(limit=10)
        assert len(events) == 1
        assert events[0]["success"] is True
        assert events[0]["finished_at"] == event["finished_at"]
        assert events[0]["event_id"]

        await CredentialStateCache.set_push_cursor(event["finished_at"])
        assert (
            await CredentialStateCache.get_push_cursor()
            == event["finished_at"]
        )
        await CredentialStateCache.clear_success("task-1", "host-1")
        assert (
            await CredentialStateCache.get_success_credential(
                "task-1", "host-1"
            )
            == ""
        )
        after_command_matrix = client.info("stats")[
            "total_connections_received"
        ]

        await CredentialStateCache.close_pool()
        reconnected = await CredentialStateCache.get_push_cursor()
        after_reconnect = client.info("stats")["total_connections_received"]
        await CredentialStateCache.close_pool()

        assert results == ["credential-1"] * 20
        assert reconnected == event["finished_at"]
        assert after_reuse - before == 1
        assert after_command_matrix == after_reuse
        assert after_reconnect - after_command_matrix == 1

    with _redis_server() as (port, client):
        monkeypatch.setitem(credential_state_cache.REDIS_CONFIG, "host", "127.0.0.1")
        monkeypatch.setitem(credential_state_cache.REDIS_CONFIG, "port", port)
        monkeypatch.setitem(credential_state_cache.REDIS_CONFIG, "password", "")
        monkeypatch.setitem(credential_state_cache.REDIS_CONFIG, "database", 15)
        asyncio.run(exercise(client))
