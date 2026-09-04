from unittest import mock

import pytest
from plugins.inputs.network_topo import snmp_topo as topo_mod
from plugins.inputs.network_topo.snmp_topo import FallbackOidResult, SnmpTopo


def _make_collector():
    collector = SnmpTopo.__new__(SnmpTopo)
    collector.host = "192.0.2.1"
    collector.snmp_port = 161
    collector.oids = SnmpTopo._build_oids(None)
    return collector


def test_build_oid_dict_carries_group():
    record = topo_mod.build_oid_dict("1.3.6.1.2.1.2.2.1.2.7", "GigabitEthernet0/0/7")
    assert record["group"] == "interfaces"
    record = topo_mod.build_oid_dict("1.3.6.1.2.1.17.1.4.1.2.5", "23")
    assert record["group"] == "bridge"


def test_huawei_ndp_is_collected_by_default_and_safe_to_skip():
    ndp_oids = {
        "1.3.6.1.4.1.2011.6.7.5.6.1.1",
        "1.3.6.1.4.1.2011.6.7.5.6.1.2",
        "1.3.6.1.4.1.2011.6.7.5.6.1.3",
    }

    assert ndp_oids.issubset(SnmpTopo._build_oids(None))
    assert ndp_oids.issubset(topo_mod.OPTIONAL_FALLBACK_ROOTS)


@pytest.mark.asyncio
async def test_bulk_cmd_falls_back_per_oid_on_retryable_error():
    collector = _make_collector()
    fallback_records = [{"tag": "IFTable-IfDescr", "ifindex": "1", "val": "eth0", "group": "interfaces"}]

    async def failing_bulk():
        raise RuntimeError("OID not increasing")

    async def fake_fallback():
        return fallback_records

    with mock.patch.object(collector, "_bulk_walk_all", side_effect=failing_bulk), mock.patch.object(
        collector, "_fallback_walk_cmd", side_effect=fake_fallback
    ) as fallback:
        result = await collector.bulkCmd()
    fallback.assert_awaited_once()
    assert result == fallback_records


@pytest.mark.asyncio
async def test_bulk_cmd_does_not_fall_back_on_non_retryable_error():
    collector = _make_collector()

    async def failing_bulk():
        raise RuntimeError("timeout")

    with mock.patch.object(collector, "_bulk_walk_all", side_effect=failing_bulk):
        with pytest.raises(RuntimeError, match="timeout"):
            await collector.bulkCmd()


@pytest.mark.asyncio
async def test_fallback_skips_optional_oid_and_keeps_required():
    collector = _make_collector()

    async def fake_collect(oid):
        if oid in topo_mod.OPTIONAL_FALLBACK_ROOTS:
            return FallbackOidResult(records=[], skipped=True)
        return FallbackOidResult(records=[{"tag": "x", "root": oid, "group": "interfaces"}])

    with mock.patch.object(collector, "_fallback_collect_oid", side_effect=fake_collect):
        records = await collector._fallback_walk_cmd()
    assert records  # 可选 OID 跳过不影响整体


@pytest.mark.asyncio
async def test_fallback_raises_when_required_oid_skipped():
    collector = _make_collector()
    required_oid = "1.3.6.1.2.1.2.2.1.2"  # IFTable-IfDescr 属于必采

    async def fake_collect(oid):
        if oid == required_oid:
            return FallbackOidResult(records=[], skipped=True)
        return FallbackOidResult(records=[{"tag": "x", "root": oid, "group": "interfaces"}])

    with mock.patch.object(collector, "_fallback_collect_oid", side_effect=fake_collect):
        with pytest.raises(topo_mod.IncompleteFallbackError):
            await collector._fallback_walk_cmd()
