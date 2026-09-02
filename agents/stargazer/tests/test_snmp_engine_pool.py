# -*- coding: utf-8 -*-
"""进程级共享 SnmpEngine 池的行为锁定测试。"""

from __future__ import annotations

import asyncio
import time

import pytest
from core.infra import snmp_engine_pool as pool
from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    UdpTransportTarget,
    UsmUserData,
    getCmd,
    usmAesCfb128Protocol,
    usmHMACSHAAuthProtocol,
)

SECRET = "must-not-be-logged"


class FakeDispatcher:
    def __init__(self, fail_close=False):
        self.closed = 0
        self.fail_close = fail_close

    def closeDispatcher(self):
        self.closed += 1
        if self.fail_close:
            raise RuntimeError(f"dispatcher secret={SECRET}")


class FakeEngine:
    def __init__(self, fail_close=False):
        self.transportDispatcher = FakeDispatcher(fail_close=fail_close)


class RecordingLogger:
    def __init__(self):
        self.calls = []

    def __getattr__(self, level):
        def _log(message, *args, **kwargs):
            self.calls.append((level, message, args, kwargs))

        return _log

    def rendered(self, level):
        return [message % args if args else message for lvl, message, args, _ in self.calls if lvl == level]

    def levels(self):
        return [lvl for lvl, _, _, _ in self.calls]


class FakeApp:
    def __init__(self):
        self.listeners = {}

    def listener(self, event):
        def register(handler):
            self.listeners[event] = handler
            return handler

        return register


def _community(name="public"):
    return CommunityData(name)


def _usm(auth_key="authkey-one"):
    return UsmUserData(
        "admin",
        authKey=auth_key,
        privKey="privkey-one",
        authProtocol=usmHMACSHAAuthProtocol,
        privProtocol=usmAesCfb128Protocol,
    )


def _unreachable_get(engine, auth, port, timeout=1):
    return getCmd(
        engine,
        auth,
        UdpTransportTarget(("127.0.0.1", port), timeout=timeout, retries=0),
        ContextData(),
        ObjectType(ObjectIdentity("1.3.6.1.2.1.1.5.0")),
        lookupMib=False,
    )


@pytest.fixture(autouse=True)
def _reset_pool():
    pool.reset_snmp_engine_pool()
    yield
    pool.reset_snmp_engine_pool()


@pytest.fixture
def fake_engines(monkeypatch):
    engines = []

    def factory():
        engine = FakeEngine()
        engines.append(engine)
        return engine

    monkeypatch.setattr(pool, "create_snmp_engine", factory)
    return engines


@pytest.fixture
def settings():
    def _configure(**overrides):
        pool.configure_snmp_engine_pool(pool.SnmpEnginePoolSettings(**overrides))

    return _configure


@pytest.mark.asyncio
async def test_same_scope_reuses_one_engine_across_targets_and_calls(fake_engines):
    async def use(port):
        async with pool.shared_snmp_engine(_community(), target=("10.0.0.1", port)) as engine:
            await asyncio.sleep(0.01)
            return engine

    sequential = [await use(161) for _ in range(3)]
    concurrent = await asyncio.gather(*(use(1000 + index) for index in range(5)))

    assert len(fake_engines) == 1
    assert {id(engine) for engine in sequential + concurrent} == {id(fake_engines[0])}
    assert fake_engines[0].transportDispatcher.closed == 0
    snapshot = pool.snmp_engine_pool_snapshot()
    assert snapshot["active_engines"] == 1
    assert snapshot["draining_engines"] == 0
    assert snapshot["engines"] == [
        {
            "scope": "community",
            "generation": 1,
            "state": "active",
            "in_flight": 0,
            "acquisitions": 8,
            "distinct_targets": 6,
        }
    ]


@pytest.mark.asyncio
async def test_v2c_communities_share_engine_but_v3_key_material_does_not(fake_engines):
    async def use(auth):
        async with pool.shared_snmp_engine(auth, target=("10.0.0.2", 161)) as engine:
            return engine

    public = await use(_community("public"))
    private = await use(_community("private"))
    key_one = await use(_usm("authkey-one"))
    key_one_again = await use(_usm("authkey-one"))
    key_two = await use(_usm("authkey-two"))

    assert public is private
    assert key_one is key_one_again
    assert key_one is not key_two
    assert key_one is not public
    assert len(fake_engines) == 3
    labels = sorted(entry["scope"] for entry in pool.snmp_engine_pool_snapshot()["engines"])
    assert labels == ["community", "v3#1", "v3#2"]


def test_scope_key_never_contains_credential_material():
    scope = pool.snmp_engine_scope(_usm(SECRET))
    assert scope.startswith("v3:")
    assert SECRET not in scope
    assert "admin" not in scope
    assert pool.snmp_engine_scope(_community(SECRET)) == "community"
    with pytest.raises(TypeError):
        pool.snmp_engine_scope(object())


@pytest.mark.asyncio
async def test_idle_engine_is_closed_after_ttl_and_reopened_on_demand(fake_engines, settings):
    settings(idle_seconds=0.05)

    async with pool.shared_snmp_engine(_community(), target=("10.0.0.3", 161)):
        pass
    assert fake_engines[0].transportDispatcher.closed == 0

    await asyncio.sleep(0.15)
    assert fake_engines[0].transportDispatcher.closed == 1
    assert pool.snmp_engine_pool_snapshot()["active_engines"] == 0

    async with pool.shared_snmp_engine(_community(), target=("10.0.0.3", 161)) as engine:
        assert engine is fake_engines[1]
    assert pool.snmp_engine_pool_snapshot()["engines"][0]["generation"] == 2


@pytest.mark.asyncio
async def test_reacquire_before_idle_ttl_cancels_pending_close(fake_engines, settings):
    settings(idle_seconds=0.05)

    for _ in range(4):
        async with pool.shared_snmp_engine(_community(), target=("10.0.0.4", 161)):
            pass
        await asyncio.sleep(0.02)

    assert len(fake_engines) == 1
    assert fake_engines[0].transportDispatcher.closed == 0


@pytest.mark.asyncio
async def test_target_limit_rotates_generation_and_drains_old_engine(fake_engines, settings):
    settings(max_targets=2)
    release = asyncio.Event()

    async def hold(port):
        async with pool.shared_snmp_engine(_community(), target=("10.0.0.5", port)) as engine:
            await release.wait()
            return engine

    holding = asyncio.create_task(hold(1))
    await asyncio.sleep(0)
    async with pool.shared_snmp_engine(_community(), target=("10.0.0.5", 2)) as second:
        pass
    async with pool.shared_snmp_engine(_community(), target=("10.0.0.5", 3)) as third:
        pass

    assert second is fake_engines[0]
    assert third is fake_engines[1]
    snapshot = pool.snmp_engine_pool_snapshot()
    assert snapshot["active_engines"] == 1
    assert snapshot["draining_engines"] == 1
    assert fake_engines[0].transportDispatcher.closed == 0  # 旧代仍有在途请求，不能关

    release.set()
    assert await holding is fake_engines[0]
    assert fake_engines[0].transportDispatcher.closed == 1
    snapshot = pool.snmp_engine_pool_snapshot()
    assert snapshot["draining_engines"] == 0
    assert snapshot["engines"][0]["generation"] == 2

    async with pool.shared_snmp_engine(_community(), target=("10.0.0.5", 3)) as again:
        assert again is fake_engines[1]  # 已知目标不触发再次轮换
    assert len(fake_engines) == 2


def test_engine_bound_to_finished_loop_is_dropped_without_closing(fake_engines):
    async def use():
        async with pool.shared_snmp_engine(_community(), target=("10.0.0.6", 161)) as engine:
            return engine

    first = asyncio.run(use())
    second = asyncio.run(use())

    assert first is fake_engines[0]
    assert second is fake_engines[1]
    assert first.transportDispatcher.closed == 0
    assert pool.snmp_engine_pool_snapshot()["active_engines"] == 1


@pytest.mark.asyncio
async def test_exception_inside_context_releases_engine(fake_engines):
    with pytest.raises(RuntimeError, match="boom"):
        async with pool.shared_snmp_engine(_community(), target=("10.0.0.7", 161)):
            raise RuntimeError("boom")

    assert pool.snmp_engine_pool_snapshot()["engines"][0]["in_flight"] == 0
    assert fake_engines[0].transportDispatcher.closed == 0


@pytest.mark.asyncio
async def test_cancellation_inside_context_releases_engine(fake_engines):
    started = asyncio.Event()

    async def use():
        async with pool.shared_snmp_engine(_community(), target=("10.0.0.8", 161)):
            started.set()
            await asyncio.sleep(10)

    task = asyncio.create_task(use())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert pool.snmp_engine_pool_snapshot()["engines"][0]["in_flight"] == 0


@pytest.mark.asyncio
async def test_close_all_closes_active_and_draining_engines(fake_engines, settings):
    settings(max_targets=1)
    release = asyncio.Event()

    async def hold():
        async with pool.shared_snmp_engine(_community(), target=("10.0.0.9", 1)):
            await release.wait()

    holding = asyncio.create_task(hold())
    await asyncio.sleep(0)
    async with pool.shared_snmp_engine(_community(), target=("10.0.0.9", 2)):
        pass
    assert pool.snmp_engine_pool_snapshot()["draining_engines"] == 1

    assert pool.close_shared_snmp_engines(reason="server_stop") == 2
    assert [engine.transportDispatcher.closed for engine in fake_engines] == [1, 1]
    snapshot = pool.snmp_engine_pool_snapshot()
    assert snapshot["active_engines"] == 0
    assert snapshot["draining_engines"] == 0
    assert snapshot["engines"] == []

    release.set()
    await holding
    assert [engine.transportDispatcher.closed for engine in fake_engines] == [1, 1]


@pytest.mark.asyncio
async def test_lifecycle_logs_use_templates_with_lazy_args_and_no_secrets(fake_engines, settings, monkeypatch):
    settings(idle_seconds=0.05)
    recorder = RecordingLogger()
    monkeypatch.setattr(pool, "logger", recorder)

    async with pool.shared_snmp_engine(_community(SECRET), target=("10.0.0.10", 161)):
        pass
    async with pool.shared_snmp_engine(_usm(SECRET), target=("10.0.0.10", 161)):
        pass
    await asyncio.sleep(0.15)

    assert recorder.levels() == ["info", "info", "info", "info"]
    for _, message, args, kwargs in recorder.calls:
        assert "%s" in message  # 稳定模板
        assert args  # 惰性独立参数
        assert not kwargs
    rendered = recorder.rendered("info")
    assert rendered[0].startswith("event=snmp_engine_opened scope=community generation=1 active_engines=1 draining_engines=0 init_seconds=")
    assert rendered[1].startswith("event=snmp_engine_opened scope=v3#1 generation=2 active_engines=2 draining_engines=0 init_seconds=")
    assert rendered[2].startswith(
        "event=snmp_engine_closed scope=community generation=1 reason=idle acquisitions=1 distinct_targets=1 lifetime_seconds="
    )
    assert rendered[2].endswith("active_engines=1 draining_engines=0")
    assert rendered[3].startswith("event=snmp_engine_closed scope=v3#1 generation=2 reason=idle ")
    assert all(SECRET not in line and "admin" not in line for line in rendered)


@pytest.mark.asyncio
async def test_close_failure_logs_single_warning_without_traceback(monkeypatch):
    engines = []

    def factory():
        engine = FakeEngine(fail_close=True)
        engines.append(engine)
        return engine

    monkeypatch.setattr(pool, "create_snmp_engine", factory)
    recorder = RecordingLogger()
    monkeypatch.setattr(pool, "logger", recorder)

    async with pool.shared_snmp_engine(_community(), target=("10.0.0.11", 161)):
        pass
    assert pool.close_shared_snmp_engines(reason="server_stop") == 1

    assert recorder.levels() == ["info", "warning"]
    _, message, args, kwargs = recorder.calls[1]
    assert "%s" in message
    assert "exc_info" not in kwargs
    rendered = message % args
    assert rendered == "event=snmp_engine_close_failed scope=community generation=1 reason=server_stop error_type=RuntimeError"
    assert SECRET not in rendered
    assert engines[0].transportDispatcher.closed == 1
    assert pool.snmp_engine_pool_snapshot()["active_engines"] == 0


def test_settings_from_env_defaults_and_validation(monkeypatch):
    monkeypatch.delenv("SNMP_ENGINE_MAX_TARGETS", raising=False)
    monkeypatch.delenv("SNMP_ENGINE_IDLE_SECONDS", raising=False)
    assert pool.SnmpEnginePoolSettings.from_env() == pool.SnmpEnginePoolSettings(max_targets=2000, idle_seconds=300.0)

    monkeypatch.setenv("SNMP_ENGINE_MAX_TARGETS", "50")
    monkeypatch.setenv("SNMP_ENGINE_IDLE_SECONDS", "1.5")
    assert pool.SnmpEnginePoolSettings.from_env() == pool.SnmpEnginePoolSettings(max_targets=50, idle_seconds=1.5)

    for name, value in (
        ("SNMP_ENGINE_MAX_TARGETS", "0"),
        ("SNMP_ENGINE_MAX_TARGETS", "-5"),
        ("SNMP_ENGINE_MAX_TARGETS", "many"),
        ("SNMP_ENGINE_IDLE_SECONDS", "0"),
        ("SNMP_ENGINE_IDLE_SECONDS", "-1"),
        ("SNMP_ENGINE_IDLE_SECONDS", "soon"),
    ):
        monkeypatch.setenv("SNMP_ENGINE_MAX_TARGETS", "50")
        monkeypatch.setenv("SNMP_ENGINE_IDLE_SECONDS", "1.5")
        monkeypatch.setenv(name, value)
        with pytest.raises(ValueError, match=name):
            pool.SnmpEnginePoolSettings.from_env()


@pytest.mark.asyncio
async def test_lifecycle_validates_settings_at_start_and_closes_engines_at_stop(fake_engines, monkeypatch):
    app = FakeApp()
    pool.register_snmp_engine_lifecycle(app)
    assert set(app.listeners) == {"before_server_start", "after_server_stop"}

    monkeypatch.setenv("SNMP_ENGINE_MAX_TARGETS", "nope")
    with pytest.raises(ValueError, match="SNMP_ENGINE_MAX_TARGETS"):
        await app.listeners["before_server_start"](app, None)

    monkeypatch.setenv("SNMP_ENGINE_MAX_TARGETS", "10")
    await app.listeners["before_server_start"](app, None)
    assert pool.snmp_engine_pool_settings().max_targets == 10

    async with pool.shared_snmp_engine(_community(), target=("10.0.0.12", 161)):
        pass
    await app.listeners["after_server_stop"](app, None)
    assert fake_engines[0].transportDispatcher.closed == 1
    assert pool.snmp_engine_pool_snapshot()["active_engines"] == 0


@pytest.mark.asyncio
async def test_real_engines_share_one_mib_compiler_and_build_parser_once(monkeypatch):
    """锁定根因：进程内只构建一次 pysmi/PLY 解析器，之后每一代 engine 复用同一编译器。"""

    import ply.yacc as yacc

    pool.reset_snmp_engine_pool(drop_mib_compiler=True)
    real_yacc = yacc.yacc
    yacc_calls = []

    def counting_yacc(*args, **kwargs):
        yacc_calls.append(1)
        return real_yacc(*args, **kwargs)

    monkeypatch.setattr(yacc, "yacc", counting_yacc)

    async with pool.shared_snmp_engine(_community(), target=("127.0.0.1", 40001)) as community_engine:
        indication, _status, _index, _binds = await _unreachable_get(community_engine, _community(), 40001)
    assert "timeout" in str(indication).lower()
    assert len(yacc_calls) == 1

    async with pool.shared_snmp_engine(_usm(), target=("127.0.0.1", 40002)) as usm_engine:
        await _unreachable_get(usm_engine, _usm(), 40002)
    assert usm_engine is not community_engine
    assert len(yacc_calls) == 1
    assert community_engine.getMibBuilder().getMibCompiler() is usm_engine.getMibBuilder().getMibCompiler()
    assert pool.snmp_engine_pool_snapshot()["mib_compiler_shared"] is True

    async with pool.shared_snmp_engine(_community(), target=("127.0.0.1", 40003)) as engine:
        assert engine is community_engine
        await _unreachable_get(engine, _community(), 40003)
    assert len(yacc_calls) == 1
    assert pool.close_shared_snmp_engines(reason="test") == 2


@pytest.mark.asyncio
async def test_one_shared_engine_multiplexes_concurrent_targets_with_independent_timeouts():
    auth = _community()

    async def probe(port):
        async with pool.shared_snmp_engine(auth, target=("127.0.0.1", port)) as engine:
            indication, _status, _index, _binds = await _unreachable_get(engine, auth, port, timeout=1)
            return engine, indication

    started = time.monotonic()
    results = await asyncio.gather(*(probe(41000 + index) for index in range(8)))
    elapsed = time.monotonic() - started

    assert len({id(engine) for engine, _ in results}) == 1
    assert all("timeout" in str(indication).lower() for _, indication in results)
    assert elapsed < 4.0  # 8 个目标各 1 秒超时并发进行，而不是串行 8 秒
    assert pool.snmp_engine_pool_snapshot()["engines"][0]["in_flight"] == 0
    assert pool.close_shared_snmp_engines(reason="test") == 1
