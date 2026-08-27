# -*- coding: utf-8 -*-
"""SNMP 配置采集插件原生异步边界测试。"""

from __future__ import annotations

import asyncio
import inspect

import pytest
from core.collection.contracts import AccessProbeStatus
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

    async def fake_get(*_args, **_kwargs):
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

    async def fake_next(*_args, **_kwargs):
        await asyncio.sleep(0.05)
        return (
            None,
            0,
            0,
            [
                [
                    (FakeOid("1.3.6.1.2.1.2.2.1.1.1"), FakeVal("1")),
                    (FakeOid("1.3.6.1.2.1.2.2.1.2.1"), FakeVal("eth0")),
                    (FakeOid("1.3.6.1.2.1.2.2.1.4.1"), FakeVal("1500")),
                    (FakeOid("1.3.6.1.2.1.2.2.1.5.1"), FakeVal("1000")),
                    (FakeOid("1.3.6.1.2.1.2.2.1.6.1"), FakeVal("aa:bb")),
                    (FakeOid("1.3.6.1.2.1.2.2.1.7.1"), FakeVal("1")),
                    (FakeOid("1.3.6.1.2.1.2.2.1.8.1"), FakeVal("1")),
                    (FakeOid("1.3.6.1.2.1.31.1.1.1.18.1"), FakeVal("uplink")),
                ]
            ],
        )

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.SnmpEngine", FakeEngine)
    monkeypatch.setattr(facts, "_next_walk", fake_next)
    result = await _heartbeat_during(facts.list_all_resources())
    assert result["success"] is True
    assert result["result"]["network_system"][0]["sysname"] == "sw"
    assert result["result"]["network_interfaces"][0]["description"] == "eth0"
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
