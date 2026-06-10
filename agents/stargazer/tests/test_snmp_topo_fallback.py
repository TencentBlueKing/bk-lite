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


def test_bulk_cmd_falls_back_per_oid_on_retryable_error():
    collector = _make_collector()
    fallback_records = [{"tag": "IFTable-IfDescr", "ifindex": "1", "val": "eth0", "group": "interfaces"}]
    with mock.patch.object(
        collector, "_bulk_walk_all", side_effect=RuntimeError("OID not increasing")
    ), mock.patch.object(
        collector, "_fallback_walk_cmd", return_value=fallback_records
    ) as fallback:
        result = collector.bulkCmd()
    fallback.assert_called_once()
    assert result == fallback_records


def test_bulk_cmd_does_not_fall_back_on_non_retryable_error():
    collector = _make_collector()
    with mock.patch.object(
        collector, "_bulk_walk_all", side_effect=RuntimeError("timeout")
    ):
        with pytest.raises(RuntimeError, match="timeout"):
            collector.bulkCmd()


def test_fallback_skips_optional_oid_and_keeps_required():
    collector = _make_collector()

    def fake_collect(oid):
        if oid in topo_mod.OPTIONAL_FALLBACK_ROOTS:
            return FallbackOidResult(records=[], skipped=True)
        return FallbackOidResult(records=[{"tag": "x", "root": oid, "group": "interfaces"}])

    with mock.patch.object(collector, "_fallback_collect_oid", side_effect=fake_collect):
        records = collector._fallback_walk_cmd()
    assert records  # 可选 OID 跳过不影响整体


def test_fallback_raises_when_required_oid_skipped():
    collector = _make_collector()
    required_oid = "1.3.6.1.2.1.2.2.1.2"  # IFTable-IfDescr 属于必采

    def fake_collect(oid):
        if oid == required_oid:
            return FallbackOidResult(records=[], skipped=True)
        return FallbackOidResult(records=[{"tag": "x", "root": oid, "group": "interfaces"}])

    with mock.patch.object(collector, "_fallback_collect_oid", side_effect=fake_collect):
        with pytest.raises(topo_mod.IncompleteFallbackError):
            collector._fallback_walk_cmd()
