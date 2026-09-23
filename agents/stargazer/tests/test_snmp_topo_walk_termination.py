"""拓扑 WALK 必须在设备明确结束时停止，并保留其他列的有效数据。"""

import pytest
from plugins.inputs.network_topo import snmp_topo
from pysnmp.proto.rfc1902 import Integer, Null, ObjectIdentifier
from pysnmp.proto.rfc1905 import EndOfMibView


@pytest.mark.asyncio
@pytest.mark.parametrize("ended", [EndOfMibView(""), Null("")])
@pytest.mark.parametrize("rows", [1, 25])
async def test_walk_stops_at_explicit_end_without_requesting_another_pdu(monkeypatch, ended, rows):
    collector = snmp_topo.SnmpTopo({"host": "127.0.0.1", "version": "v2c", "community": "test-only"})
    roots = collector.oids[:2]
    collector.oids = roots
    monkeypatch.setattr(collector, "_format_oids", lambda oids: [(ObjectIdentifier(oid), Null("")) for oid in oids])
    calls = 0

    async def bulk(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        assert calls == 1, "WALK continued after all columns ended"
        row = [(ObjectIdentifier(root + ".1"), ended) for root in roots]
        return None, 0, 0, [row] * rows

    monkeypatch.setattr(snmp_topo, "hlapi_bulk_cmd", bulk)
    assert await collector._bulk_walk_all_with_engine(object()) == []
    assert calls == 1


@pytest.mark.asyncio
async def test_walk_preserves_live_column_after_other_column_ends(monkeypatch):
    collector = snmp_topo.SnmpTopo({"host": "127.0.0.1", "version": "v2c", "community": "test-only"})
    roots = collector.oids[:2]
    collector.oids = roots
    monkeypatch.setattr(collector, "_format_oids", lambda oids: [(ObjectIdentifier(oid), Null("")) for oid in oids])
    live = (ObjectIdentifier(roots[1] + ".1"), Integer(42))
    ended = (ObjectIdentifier(roots[0] + ".1"), EndOfMibView(""))
    calls = 0

    async def bulk(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return None, 0, 0, [[ended, live]]
        assert calls == 2, "WALK continued after the last live column ended"
        # 已结束的列即使携带值也不得重新激活；另一列越界结束。
        return None, 0, 0, [[(ended[0], Integer(99)), (ObjectIdentifier("9.1"), Integer(1))]]

    monkeypatch.setattr(snmp_topo, "hlapi_bulk_cmd", bulk)
    expected = collector._format_result([[live]], roots)
    assert expected
    assert await collector._bulk_walk_all_with_engine(object()) == expected
    assert calls == 2
