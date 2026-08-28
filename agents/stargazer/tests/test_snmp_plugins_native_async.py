# -*- coding: utf-8 -*-
"""SNMP 配置采集插件原生异步边界测试。"""

from __future__ import annotations

import asyncio
import inspect

import pytest
from core.collection.contracts import AccessProbeStatus
from core.collection.metrics import CollectionMetrics
from plugins.inputs.network.snmp_facts import SnmpFacts
from plugins.inputs.network_topo.snmp_topo import SnmpTopo


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


@pytest.mark.asyncio
async def test_snmp_facts_probe_does_not_stall(monkeypatch):
    closed = []

    class FakeDispatcher:
        def closeDispatcher(self):
            closed.append(True)

    class FakeEngine:
        def __init__(self):
            self.transportDispatcher = FakeDispatcher()

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
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.SnmpEngine", FakeEngine)
    result = await _heartbeat_during(facts.probe())
    assert result.status == AccessProbeStatus.READY
    assert closed == [True]


@pytest.mark.asyncio
async def test_snmp_facts_collect_does_not_stall(monkeypatch):
    closed = []
    engines = []
    io_engines = []
    metrics = CollectionMetrics()

    class FakeDispatcher:
        def closeDispatcher(self):
            closed.append(True)

    class FakeEngine:
        def __init__(self):
            self.transportDispatcher = FakeDispatcher()
            engines.append(self)

    facts = SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2",
            "community": "public",
            "snmp_port": 161,
            "_runtime_metrics": metrics,
        }
    )

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

    async def fake_get(engine, *_args, **_kwargs):
        io_engines.append(engine)
        await asyncio.sleep(0.05)
        return (
            None,
            0,
            0,
            [
                (FakeOid("1.3.6.1.2.1.1.1.0"), FakeVal("desc")),
                (FakeOid("1.3.6.1.2.1.1.2.0"), FakeVal("1.3.6")),
                (FakeOid("1.3.6.1.2.1.1.4.0"), FakeVal("admin")),
                (FakeOid("1.3.6.1.2.1.1.5.0"), FakeVal("sw")),
                (FakeOid("1.3.6.1.2.1.1.6.0"), FakeVal("rack")),
            ],
        )

    async def fake_next(engine, *_args, **_kwargs):
        io_engines.append(engine)
        await asyncio.sleep(0.05)
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.nextCmd", fake_next)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.SnmpEngine", FakeEngine)
    result = await _heartbeat_during(facts.list_all_resources())
    assert result["success"] is True
    assert result["result"]["network_system"][0]["sysname"] == "sw"
    assert result["result"]["network_interfaces"] == []
    assert len(engines) == 1
    assert io_engines == [engines[0], engines[0]]
    assert closed == [True]
    assert metrics.snapshot()["snmp_collect_to_first_io_seconds_p99"] >= 0


@pytest.mark.asyncio
async def test_snmp_facts_walk_failure_closes_shared_engine_once(monkeypatch):
    engines = []
    closed = []

    class FakeDispatcher:
        def closeDispatcher(self):
            closed.append(True)

    class FakeEngine:
        def __init__(self):
            engines.append(self)
            self.transportDispatcher = FakeDispatcher()

    async def fake_get(*_args, **_kwargs):
        return (None, 0, 0, [])

    async def broken_next(*_args, **_kwargs):
        raise RuntimeError("walk failed")

    facts = SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2",
            "community": "public",
        }
    )
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.SnmpEngine", FakeEngine)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.nextCmd", broken_next)

    with pytest.raises(RuntimeError, match="SNMP interface information collection"):
        await facts.collect()

    assert len(engines) == 1
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
    finally:
        loop.set_exception_handler(previous_handler)

    assert callback_errors == []
