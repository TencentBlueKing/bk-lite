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


def test_snmp_topo_transport_timeout_does_not_read_form_budget():
    collector = SnmpTopo(
        {
            "host": "127.0.0.1",
            "version": "v2c",
            "community": "public",
            "timeout": 999,
            "retries": 9,
        }
    )

    assert collector.transport_opts == {"timeout": 10, "retries": 1}


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

    async def fake_bulk(engine, *_args, **_kwargs):
        io_engines.append(engine)
        await asyncio.sleep(0.05)
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", fake_bulk)
    result = await _heartbeat_during(facts.list_all_resources())
    assert result["success"] is True
    assert result["result"]["network_system"][0]["sysname"] == "sw"
    assert result["result"]["network_interfaces"] == []
    assert len(engines) == 1
    assert io_engines == [engines[0], engines[0]]
    assert closed == []
    assert metrics.snapshot()["snmp_collect_to_first_io_seconds_p99"] >= 0


@pytest.mark.asyncio
async def test_snmp_facts_collect_rejects_system_get_error_status(monkeypatch):
    _install_fake_engines(monkeypatch)
    bulk_calls = 0

    async def failed_get(*_args, **_kwargs):
        return (None, "genErr", 1, [])

    async def unexpected_bulk(*_args, **_kwargs):
        nonlocal bulk_calls
        bulk_calls += 1
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", failed_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", unexpected_bulk)

    with pytest.raises(RuntimeError, match="SNMP system GET failed: genErr"):
        await SnmpFacts({"host": "127.0.0.1", "version": "v2c", "community": "public"}).collect()

    assert bulk_calls == 0


@pytest.mark.asyncio
async def test_snmp_facts_interface_walk_uses_getbulk_with_bounded_repetitions(monkeypatch):
    _install_fake_engines(monkeypatch)
    captured = {}

    async def fake_get(*_args, **_kwargs):
        return (None, 0, 0, _system_var_binds())

    async def fake_bulk(_engine, _auth, _target, _context, non_repeaters, max_repetitions, *_oids, **_kwargs):
        captured["non_repeaters"] = non_repeaters
        captured["max_repetitions"] = max_repetitions
        return (None, 0, 0, [])

    async def unexpected_next(*_args, **_kwargs):
        raise AssertionError("GETNEXT must not run on a successful GETBULK walk")

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", fake_bulk)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.nextCmd", unexpected_next)

    result = await SnmpFacts({"host": "127.0.0.1", "version": "v2c", "community": "public"}).collect()

    assert result["interfaces"] == []
    assert captured == {"non_repeaters": 0, "max_repetitions": 25}


@pytest.mark.asyncio
async def test_snmp_facts_converts_each_pdu_before_requesting_the_next_one(monkeypatch):
    _install_fake_engines(monkeypatch)
    metrics = CollectionMetrics()
    roots = (
        "1.3.6.1.2.1.2.2.1.1",
        "1.3.6.1.2.1.2.2.1.2",
        "1.3.6.1.2.1.2.2.1.4",
        "1.3.6.1.2.1.2.2.1.5",
        "1.3.6.1.2.1.2.2.1.6",
        "1.3.6.1.2.1.2.2.1.7",
        "1.3.6.1.2.1.2.2.1.8",
        "1.3.6.1.2.1.31.1.1.1.18",
    )

    class PduValue(FakeVal):
        expired = False

        def prettyPrint(self):
            if self.expired:
                raise AssertionError("raw varBind survived until the next PDU")
            return super().prettyPrint()

    values = [PduValue(str(index)) for index in range(len(roots))]
    calls = 0

    async def fake_get(*_args, **_kwargs):
        return (None, 0, 0, _system_var_binds())

    async def fake_bulk(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return (None, 0, 0, [[(FakeOid(f"{root}.1"), value) for root, value in zip(roots, values)]])
        for value in values:
            value.expired = True
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", fake_bulk)

    result = await SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2c",
            "community": "public",
            "_runtime_metrics": metrics,
        }
    ).collect()

    assert result["interfaces"] == [
        {
            "index": "0",
            "description": "1",
            "mtu": "2",
            "speed": "3",
            "mac_address": "4",
            "admin_status": "5",
            "oper_status": "6",
            "alias": "7",
        }
    ]
    assert metrics.snapshot()["snmp_walk_yield_total"] >= 1


@pytest.mark.asyncio
async def test_snmp_facts_getbulk_reduces_repetitions_before_getnext_fallback(monkeypatch):
    _install_fake_engines(monkeypatch)
    repetitions = []
    next_calls = 0

    async def fake_get(*_args, **_kwargs):
        return (None, 0, 0, _system_var_binds())

    async def too_big_bulk(_engine, _auth, _target, _context, _non_repeaters, max_repetitions, *_oids, **_kwargs):
        repetitions.append(max_repetitions)
        return (None, "tooBig", 1, [])

    async def fallback_next(*_args, **_kwargs):
        nonlocal next_calls
        next_calls += 1
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", too_big_bulk)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.nextCmd", fallback_next)

    result = await SnmpFacts({"host": "127.0.0.1", "version": "v2c", "community": "public"}).collect()

    assert result["interfaces"] == []
    assert repetitions == [25, 12, 6, 3, 1]
    assert next_calls == 1


@pytest.mark.asyncio
async def test_snmp_facts_getbulk_non_increasing_oid_falls_back_once(monkeypatch):
    _install_fake_engines(monkeypatch)
    roots = (
        "1.3.6.1.2.1.2.2.1.1",
        "1.3.6.1.2.1.2.2.1.2",
        "1.3.6.1.2.1.2.2.1.4",
        "1.3.6.1.2.1.2.2.1.5",
        "1.3.6.1.2.1.2.2.1.6",
        "1.3.6.1.2.1.2.2.1.7",
        "1.3.6.1.2.1.2.2.1.8",
        "1.3.6.1.2.1.31.1.1.1.18",
    )
    repeated_row = [(FakeOid(f"{root}.1"), FakeVal("value")) for root in roots]
    next_calls = 0

    async def fake_get(*_args, **_kwargs):
        return (None, 0, 0, _system_var_binds())

    async def non_increasing_bulk(*_args, **_kwargs):
        return (None, 0, 0, [repeated_row, repeated_row])

    async def fallback_next(*_args, **_kwargs):
        nonlocal next_calls
        next_calls += 1
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", non_increasing_bulk)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.nextCmd", fallback_next)

    result = await SnmpFacts({"host": "127.0.0.1", "version": "v2c", "community": "public"}).collect()

    assert result["interfaces"] == []
    assert next_calls == 1


@pytest.mark.asyncio
async def test_snmp_facts_getbulk_response_bytes_are_bounded(monkeypatch):
    _install_fake_engines(monkeypatch)
    facts = SnmpFacts({"host": "127.0.0.1", "version": "v2c", "community": "public"})

    async def oversized_bulk(*_args, **_kwargs):
        return (
            None,
            0,
            0,
            [[(FakeOid("1.3.6.1.2.1.2.2.1.1.1"), FakeVal("oversized"))]],
        )

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", oversized_bulk)
    error, status, _index, rows = await facts._bulk_walk(
        object(),
        ["1.3.6.1.2.1.2.2.1.1"],
        max_response_bytes=1,
    )

    assert status == 0
    assert rows == []
    assert "response byte limit exceeded" in str(error)


@pytest.mark.asyncio
async def test_snmp_facts_walk_failure_keeps_shared_engine_for_next_target(monkeypatch):
    engines, closed = _install_fake_engines(monkeypatch)
    io_engines = []

    async def fake_get(engine, *_args, **_kwargs):
        io_engines.append(engine)
        return (None, 0, 0, [])

    async def broken_bulk(*_args, **_kwargs):
        raise RuntimeError("walk failed")

    async def fake_bulk(engine, *_args, **_kwargs):
        io_engines.append(engine)
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", broken_bulk)

    facts = SnmpFacts({"host": "127.0.0.1", "version": "v2", "community": "public"})
    with pytest.raises(RuntimeError, match="SNMP interface information collection"):
        await facts.collect()
    assert len(engines) == 1
    assert closed == []
    assert snmp_engine_pool.snmp_engine_pool_snapshot()["engines"][0]["in_flight"] == 0

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", fake_bulk)
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

    async def fake_bulk(engine, *_args, **_kwargs):
        io_engines.append(engine)
        await asyncio.sleep(0.01)
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", fake_bulk)

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
async def test_160_concurrent_snmp_walks_keep_the_loop_responsive(monkeypatch):
    """单 Worker 的 160 个目标同时 WALK 时，每个 PDU 都必须给 I/O 调度机会。"""

    _install_fake_engines(monkeypatch)
    roots = (
        "1.3.6.1.2.1.2.2.1.1",
        "1.3.6.1.2.1.2.2.1.2",
        "1.3.6.1.2.1.2.2.1.4",
        "1.3.6.1.2.1.2.2.1.5",
        "1.3.6.1.2.1.2.2.1.6",
        "1.3.6.1.2.1.2.2.1.7",
        "1.3.6.1.2.1.2.2.1.8",
        "1.3.6.1.2.1.31.1.1.1.18",
    )
    pdu_by_context = {}
    heartbeat_ticks = 0
    lag_samples = []
    stop_heartbeat = False

    async def fake_get(*_args, **_kwargs):
        return (None, 0, 0, _system_var_binds())

    async def fake_bulk(_engine, _auth, _target, context, *_args, **_kwargs):
        pdu = pdu_by_context.get(id(context), 0) + 1
        pdu_by_context[id(context)] = pdu
        if pdu > 20:
            return (None, 0, 0, [])
        row = [(FakeOid(f"{root}.{pdu}"), FakeVal(f"value-{pdu}-{column}")) for column, root in enumerate(roots)]
        return (None, 0, 0, [row])

    async def heartbeat():
        nonlocal heartbeat_ticks
        expected = asyncio.get_running_loop().time()
        while not stop_heartbeat:
            await asyncio.sleep(0)
            now = asyncio.get_running_loop().time()
            lag_samples.append(max(0.0, now - expected))
            heartbeat_ticks += 1
            expected = now

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", fake_bulk)
    collectors = [
        SnmpFacts(
            {
                "host": f"127.0.0.{index + 1}",
                "version": "v2c",
                "community": "public",
            }
        )
        for index in range(160)
    ]

    heartbeat_task = asyncio.create_task(heartbeat())
    results = await asyncio.gather(*(collector.collect() for collector in collectors))
    stop_heartbeat = True
    await heartbeat_task

    assert len(pdu_by_context) == 160
    assert all(len(result["interfaces"]) == 20 for result in results)
    assert heartbeat_ticks >= 20
    assert max(lag_samples, default=0.0) < 0.1


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

    # 其他测试可能重载 network_topo module；直接替换方法实际使用的 globals，
    # 避免顶层导入的 SnmpTopo 类仍引用旧 module dict。
    method_globals = SnmpTopo._bulk_walk_all_with_engine.__globals__
    monkeypatch.setitem(method_globals, "hlapi_bulk_cmd", fake_bulk)
    monkeypatch.setitem(method_globals, "hlapi_next_cmd", fake_next)
    monkeypatch.setitem(method_globals, "hlapi_get_cmd", fake_get)

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
async def test_snmp_topo_formats_each_pdu_and_yields_before_requesting_the_next_one(monkeypatch):
    _install_fake_engines(monkeypatch)
    collector = SnmpTopo({"host": "127.0.0.1", "version": "v2c", "community": "public"})
    collector.oids = ["1.3.6.1.2.1.2.2.1.2"]
    yielded = False
    calls = 0

    class PduValue(FakeVal):
        expired = False

        def prettyPrint(self):
            if self.expired:
                raise AssertionError("raw topology varBind survived until the next PDU")
            return super().prettyPrint()

    value = PduValue("eth0")

    def mark_yielded():
        nonlocal yielded
        yielded = True

    async def fake_bulk(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            asyncio.get_running_loop().call_soon(mark_yielded)
            return (None, 0, 0, [[(FakeOid("1.3.6.1.2.1.2.2.1.2.1"), value)]])
        assert yielded is True
        value.expired = True
        return (None, 0, 0, [])

    method_globals = SnmpTopo._bulk_walk_all_with_engine.__globals__
    monkeypatch.setitem(method_globals, "hlapi_bulk_cmd", fake_bulk)

    records = await collector._bulk_walk_all()

    assert len(records) == 1
    assert records[0]["val"] == "eth0"


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
