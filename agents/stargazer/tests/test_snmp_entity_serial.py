# -*- coding: utf-8 -*-
"""ENTITY-MIB 序列号行组装，以及 walk 失败不拖垮设备采集。"""
import pytest
from core.infra import snmp_engine_pool
from plugins.inputs.network.snmp_facts import SnmpFacts, assemble_entity_serial_rows, format_entity_label


def test_format_entity_label_prefixes_chassis_only():
    assert format_entity_label("3", "HUAWEI S5735 Routing Switch", "") == "chassis / HUAWEI S5735 Routing Switch"
    assert format_entity_label("chassis(3)", "C1200-8T-D", "") == "chassis / C1200-8T-D"
    assert format_entity_label("9", "", "MPU Board 0") == "MPU Board 0"
    assert format_entity_label("3", "", "") == "chassis"


def test_assemble_keeps_duplicate_serial_on_distinct_entities_and_drops_blank():
    rows = assemble_entity_serial_rows(
        [
            {"index": "67108867", "serial": "4E2480048371", "physical_class": "3", "descr": "HUAWEI S5735 Routing Switch"},
            {"index": "67108873", "serial": "4E2480048371", "physical_class": "9", "name": "MPU Board 0"},
            {"index": "68157449", "serial": "4E2480048608", "physical_class": "9", "descr": "MPU Board 1"},
            {"index": "1", "serial": "  ", "descr": "empty"},
            {"index": "67108867", "serial": "SHOULD-NOT-REPLACE", "descr": "again"},
        ]
    )

    assert rows == [
        {
            "index": "67108867",
            "oid": "1.3.6.1.2.1.47.1.1.1.1.11.67108867",
            "serial": "4E2480048371",
            "entity": "chassis / HUAWEI S5735 Routing Switch",
        },
        {
            "index": "67108873",
            "oid": "1.3.6.1.2.1.47.1.1.1.1.11.67108873",
            "serial": "4E2480048371",
            "entity": "MPU Board 0",
        },
        {
            "index": "68157449",
            "oid": "1.3.6.1.2.1.47.1.1.1.1.11.68157449",
            "serial": "4E2480048608",
            "entity": "MPU Board 1",
        },
    ]


class _Oid:
    def __init__(self, text):
        self._text = text

    def prettyPrint(self):
        return self._text


class _Val:
    def __init__(self, text):
        self._text = text
        self._value = text.encode()

    def prettyPrint(self):
        return self._text


def _system_binds():
    return [
        (_Oid("1.3.6.1.2.1.1.1.0"), _Val("desc")),
        (_Oid("1.3.6.1.2.1.1.2.0"), _Val("1.3.6.1.4.1.2011.2.23.968")),
        (_Oid("1.3.6.1.2.1.1.4.0"), _Val("admin")),
        (_Oid("1.3.6.1.2.1.1.5.0"), _Val("sw")),
        (_Oid("1.3.6.1.2.1.1.6.0"), _Val("rack")),
    ]


def _entity_row(index, descr, physical_class, name, serial):
    return [
        (_Oid(f"1.3.6.1.2.1.47.1.1.1.1.2.{index}"), _Val(descr)),
        (_Oid(f"1.3.6.1.2.1.47.1.1.1.1.5.{index}"), _Val(physical_class)),
        (_Oid(f"1.3.6.1.2.1.47.1.1.1.1.7.{index}"), _Val(name)),
        (_Oid(f"1.3.6.1.2.1.47.1.1.1.1.11.{index}"), _Val(serial)),
    ]


def _install_fake_engines(monkeypatch):
    snmp_engine_pool.reset_snmp_engine_pool()

    class FakeDispatcher:
        def closeDispatcher(self):
            return None

    class FakeEngine:
        def __init__(self):
            self.transportDispatcher = FakeDispatcher()

    monkeypatch.setattr(snmp_engine_pool, "create_snmp_engine", FakeEngine)


@pytest.mark.asyncio
async def test_collect_publishes_entity_serials_and_keeps_device_when_walk_fails(monkeypatch):
    _install_fake_engines(monkeypatch)
    calls = {"bulk": 0}

    async def fake_get(*_args, **_kwargs):
        return (None, 0, 0, _system_binds())

    entity_rows = [
        _entity_row("2", "S5130V2", "3", "chassis", "219801A4S57243K100CV"),
        _entity_row("3", "fan", "7", "Fan", ""),
        _entity_row("192", "", "9", "Board", "219801A4S57243K100CV"),
    ]

    async def fake_bulk(*_args, **_kwargs):
        calls["bulk"] += 1
        if calls["bulk"] == 2:
            return (None, 0, 0, entity_rows)
        return (None, 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get)
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", fake_bulk)

    result = await SnmpFacts({"host": "10.10.69.246", "version": "v2c", "community": "public"}).list_all_resources()

    assert result["success"] is True
    assert result["result"]["network_system"][0]["sn_collected"] == "true"
    assert result["result"]["network_interfaces"] == []
    assert result["result"]["network_sn"] == [
        {
            "index": "2",
            "oid": "1.3.6.1.2.1.47.1.1.1.1.11.2",
            "serial": "219801A4S57243K100CV",
            "entity": "chassis / S5130V2",
            "ip_addr": "10.10.69.246",
        },
        {
            "index": "192",
            "oid": "1.3.6.1.2.1.47.1.1.1.1.11.192",
            "serial": "219801A4S57243K100CV",
            "entity": "Board",
            "ip_addr": "10.10.69.246",
        },
    ]

    async def failing_bulk(*_args, **_kwargs):
        calls["bulk"] += 1
        if calls["bulk"] == 1:
            return (None, 0, 0, [])
        raise RuntimeError("entity walk down")

    calls["bulk"] = 0
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.bulkCmd", failing_bulk)
    failed = await SnmpFacts({"host": "10.10.69.246", "version": "v2c", "community": "public"}).list_all_resources()

    assert failed["success"] is True
    assert failed["result"]["network_system"][0]["sysname"] == "sw"
    assert failed["result"]["network_system"][0]["sn_collected"] == "false"
    assert "network_sn" not in failed["result"]
