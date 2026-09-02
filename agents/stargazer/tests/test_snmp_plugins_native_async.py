# -*- coding: utf-8 -*-
"""SNMP 配置采集插件原生异步边界测试。"""

from __future__ import annotations

import asyncio
import inspect

import pytest
from core.collection.contracts import AccessProbeStatus
from core.collection.metrics import CollectionMetrics
from core.infra import snmp_engine_pool
from plugins.inputs.network.snmp_facts import SnmpFacts
from plugins.inputs.network_topo.snmp_topo import SnmpTopo


@pytest.fixture(autouse=True)
def _reset_snmp_engine_pool():
    snmp_engine_pool.reset_snmp_engine_pool()
    yield
    snmp_engine_pool.reset_snmp_engine_pool()


def _install_fake_engines(monkeypatch):
    """用假 engine 替换池的工厂；返回 (已创建 engine 列表, closeDispatcher 调用记录)。"""

    engines = []
    closed = []

    class FakeDispatcher:
        def closeDispatcher(self):
            closed.append(True)

    class FakeEngine:
        def __init__(self):
            self.transportDispatcher = FakeDispatcher()
            engines.append(self)

    monkeypatch.setattr(snmp_engine_pool, "create_snmp_engine", FakeEngine)
    return engines, closed


async def _heartbeat_during(awaitable, minimum_ticks: int = 5):
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    task = asyncio.create_task(heartbeat())
    try:
        return await awaitable
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert ticks >= minimum_ticks, "event_loop_stalled"


class FakeOid:
    def __init__(self, text):
        self._text = text

    def prettyPrint(self):
        return self._text


class FakeVal:
    def __init__(self, text):
        self._text = text
        self._value = text.encode() if isinstance(text, str) else text

    def prettyPrint(self):
        return self._text


def _system_var_binds():
    return [
        (FakeOid("1.3.6.1.2.1.1.1.0"), FakeVal("desc")),
        (FakeOid("1.3.6.1.2.1.1.2.0"), FakeVal("1.3.6")),
        (FakeOid("1.3.6.1.2.1.1.4.0"), FakeVal("admin")),
        (FakeOid("1.3.6.1.2.1.1.5.0"), FakeVal("sw")),
        (FakeOid("1.3.6.1.2.1.1.6.0"), FakeVal("rack")),
    ]


@pytest.mark.asyncio
async def test_snmp_facts_probe_does_not_stall(monkeypatch):
    engines, closed = _install_fake_engines(monkeypatch)

    facts = SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2",
            "community": "public",
            "snmp_port": 161,
        }
    )

    async def slow_get(*_args, **_kwargs):
        await asyncio.sleep(0.05)
        return (None, 0, 0, [("1.3.6.1.2.1.1.5.0", "sw")])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", slow_get)
    result = await _heartbeat_during(facts.probe())
    assert result.status == AccessProbeStatus.READY
    assert len(engines) == 1
    assert closed == []  # 共享 engine 不随单目标结束而关闭


@pytest.mark.asyncio
async def test_snmp_facts_collect_does_not_stall(monkeypatch):
    engines, closed = _install_fake_engines(monkeypatch)
    io_engines = []
    metrics = CollectionMetrics()

    facts = SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2",
            "community": "public",
            "snmp_port": 161,
            "_runtime_metrics": metrics,
        }
    )

    async def fake_get(engine, *_args, **_kwargs):
        io_engines.append(engine)
        await asyncio.sleep(0.05)
        return (None, 0, 0, _system_var_binds())

    async def fake_next(engine, *_args, **_kwargs):
        io_engines.append(engine)
        await asyncio.sleep(0.05)
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.nextCmd", fake_next)
    result = await _heartbeat_during(facts.list_all_resources())
    assert result["success"] is True
    assert result["result"]["network_system"][0]["sysname"] == "sw"
    assert result["result"]["network_interfaces"] == []
    assert len(engines) == 1
    assert io_engines == [engines[0], engines[0]]
    assert closed == []
    assert metrics.snapshot()["snmp_collect_to_first_io_seconds_p99"] >= 0


@pytest.mark.asyncio
async def test_snmp_facts_walk_failure_keeps_shared_engine_for_next_target(monkeypatch):
    engines, closed = _install_fake_engines(monkeypatch)
    io_engines = []

    async def fake_get(engine, *_args, **_kwargs):
        io_engines.append(engine)
        return (None, 0, 0, [])

    async def broken_next(*_args, **_kwargs):
        raise RuntimeError("walk failed")

    async def fake_next(engine, *_args, **_kwargs):
        io_engines.append(engine)
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.nextCmd", broken_next)

    facts = SnmpFacts({"host": "127.0.0.1", "version": "v2", "community": "public"})
    with pytest.raises(RuntimeError, match="SNMP interface information collection"):
        await facts.collect()
    assert len(engines) == 1
    assert closed == []
    assert snmp_engine_pool.snmp_engine_pool_snapshot()["engines"][0]["in_flight"] == 0

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.nextCmd", fake_next)
    next_facts = SnmpFacts({"host": "127.0.0.2", "version": "v2", "community": "public"})
    result = await next_facts.collect()
    assert result["system"]["ip_addr"] == "127.0.0.2"
    assert len(engines) == 1
    assert io_engines == [engines[0]] * 3
    assert closed == []


@pytest.mark.asyncio
async def test_snmp_facts_collect_and_probe_share_one_engine_per_process(monkeypatch):
    """同一进程内多次 collect/probe（不同目标、串行与并发）都复用同一个 engine 实例。"""

    engines, closed = _install_fake_engines(monkeypatch)
    io_engines = []

    async def fake_get(engine, *_args, **_kwargs):
        io_engines.append(engine)
        await asyncio.sleep(0.01)
        return (None, 0, 0, _system_var_binds())

    async def fake_next(engine, *_args, **_kwargs):
        io_engines.append(engine)
        await asyncio.sleep(0.01)
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.nextCmd", fake_next)

    def make(host):
        return SnmpFacts({"host": host, "version": "v2c", "community": "public", "snmp_port": 161})

    for index in range(1, 4):
        assert (await make(f"127.0.0.{index}").probe()).status == AccessProbeStatus.READY
        assert (await make(f"127.0.0.{index}").collect())["system"]["sysname"] == "sw"
    await asyncio.gather(*(make(f"127.0.0.{index}").collect() for index in range(4, 8)))
    await asyncio.gather(*(make(f"127.0.0.{index}").probe() for index in range(4, 8)))

    assert len(engines) == 1
    assert io_engines
    assert {id(engine) for engine in io_engines} == {id(engines[0])}
    assert closed == []
    snapshot = snmp_engine_pool.snmp_engine_pool_snapshot()
    assert snapshot["active_engines"] == 1
    assert snapshot["engines"][0]["in_flight"] == 0
    assert snapshot["engines"][0]["distinct_targets"] == 7
    assert snmp_engine_pool.close_shared_snmp_engines(reason="test") == 1
    assert closed == [True]


@pytest.mark.asyncio
async def test_snmp_topo_list_all_resources_does_not_stall(monkeypatch):
    collector = SnmpTopo.__new__(SnmpTopo)
    collector.host = "127.0.0.1"
    collector.snmp_port = 161

    async def fake_bulk():
        await asyncio.sleep(0.05)
        return [{"tag": "IFTable-IfDescr", "val": "eth0"}]

    monkeypatch.setattr(collector, "bulkCmd", fake_bulk)
    result = await _heartbeat_during(collector.list_all_resources())
    assert result["success"] is True
    assert result["result"]["network_topo"][0]["val"] == "eth0"


@pytest.mark.asyncio
async def test_snmp_topo_bulk_walk_and_fallback_share_one_engine(monkeypatch):
    engines, closed = _install_fake_engines(monkeypatch)
    io_engines = []

    async def fake_bulk(engine, *_args, **_kwargs):
        io_engines.append(engine)
        return (None, 0, 0, [])

    async def fake_next(engine, *_args, **_kwargs):
        io_engines.append(engine)
        return (None, 0, 0, [])

    async def fake_get(engine, *_args, **_kwargs):
        io_engines.append(engine)
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network_topo.snmp_topo.hlapi_bulk_cmd", fake_bulk)
    monkeypatch.setattr("plugins.inputs.network_topo.snmp_topo.hlapi_next_cmd", fake_next)
    monkeypatch.setattr("plugins.inputs.network_topo.snmp_topo.hlapi_get_cmd", fake_get)

    first = SnmpTopo({"host": "127.0.0.1", "version": "v2c", "community": "public"})
    second = SnmpTopo({"host": "127.0.0.2", "version": "v2c", "community": "public"})
    assert await first._bulk_walk_all() == []
    assert await second._bulk_walk_all() == []
    assert (await first._next_walk_oid("1.3.6.1.2.1.2.2.1.2"))[3] == []
    assert (await second._get_scalar_oid("1.3.6.1.2.1.1.5")).records == []

    assert len(engines) == 1
    assert io_engines == [engines[0]] * 4
    assert closed == []


@pytest.mark.asyncio
async def test_snmp_facts_ignores_legacy_inline_topology_parameters(monkeypatch):
    facts = SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2c",
            "community": "public",
            "has_network_topo": "True",
            "topology_protocols": ("lldp", "cdp"),
        }
    )

    async def fake_collect():
        return {
            "system": {"sysname": "edge-sw-1"},
            "interfaces": [{"index": "7"}],
        }

    monkeypatch.setattr(facts, "collect", fake_collect)

    result = await facts.list_all_resources()

    assert result == {
        "success": True,
        "result": {
            "network_system": [{"sysname": "edge-sw-1"}],
            "network_interfaces": [{"index": "7"}],
        },
    }


def test_snmp_modules_have_no_to_thread():
    import plugins.inputs.network.snmp_facts as facts_mod
    import plugins.inputs.network_topo.snmp_topo as topo_mod

    assert "asyncio.to_thread" not in inspect.getsource(facts_mod)
    assert "asyncio.to_thread" not in inspect.getsource(topo_mod)


def test_snmp_modules_never_create_per_target_engines():
    import plugins.inputs.network.snmp_facts as facts_mod
    import plugins.inputs.network_topo.snmp_topo as topo_mod

    for module in (facts_mod, topo_mod):
        source = inspect.getsource(module)
        assert "SnmpEngine()" not in source
        assert "closeDispatcher" not in source
        assert "shared_snmp_engine" in source


@pytest.mark.asyncio
async def test_real_pysnmp_dispatchers_close_cleanly_after_concurrent_cancellation():
    """不替换 getCmd，锁定真实 pysnmp Future 取消后的 callback 边界。"""

    loop = asyncio.get_running_loop()
    callback_errors = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: callback_errors.append(context))

    async def cancel_one(index):
        facts = SnmpFacts(
            {
                "host": "127.0.0.1",
                "version": "v2c",
                "community": "public",
                "snmp_port": 65000 + index,
            }
        )
        try:
            async with asyncio.timeout(0.05):
                await facts.collect()
        except (TimeoutError, RuntimeError):
            pass

    try:
        await asyncio.gather(*(cancel_one(index) for index in range(32)))
        await asyncio.sleep(0.1)
        snapshot = snmp_engine_pool.snmp_engine_pool_snapshot()
        assert snapshot["active_engines"] == 1
        assert snapshot["engines"][0]["in_flight"] == 0
        assert snapshot["engines"][0]["distinct_targets"] == 32
        # 共享 engine 在仍有已取消的在途请求时关闭，也不得产生事件循环回调错误
        assert snmp_engine_pool.close_shared_snmp_engines(reason="test") == 1
        await asyncio.sleep(0.1)
    finally:
        loop.set_exception_handler(previous_handler)

    assert callback_errors == []
