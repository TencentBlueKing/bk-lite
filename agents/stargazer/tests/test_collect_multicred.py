import asyncio
import importlib
import sys
import types
from pathlib import Path
import pytest


sys.path.insert(0, str(Path(__file__).parent.parent))


def _import_snmp_topo_with_stubbed_sanic_log(monkeypatch):
    sanic_module = types.ModuleType("sanic")
    sanic_module.__path__ = []
    sanic_log_module = types.ModuleType("sanic.log")
    sanic_log_module.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    sanic_module.log = sanic_log_module

    monkeypatch.setitem(sys.modules, "sanic", sanic_module)
    monkeypatch.setitem(sys.modules, "sanic.log", sanic_log_module)
    monkeypatch.delitem(sys.modules, "plugins.inputs.network_topo.snmp_topo", raising=False)

    return importlib.import_module("plugins.inputs.network_topo.snmp_topo")


def _import_snmp_facts_with_stubbed_deps(monkeypatch):
    sanic_module = types.ModuleType("sanic")
    sanic_module.__path__ = []
    sanic_log_module = types.ModuleType("sanic.log")
    sanic_log_module.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    sanic_module.log = sanic_log_module

    cmdgen_module = types.ModuleType("pysnmp.entity.rfc3413.oneliner.cmdgen")
    cmdgen_module.CommunityData = lambda *args, **kwargs: ("community", args, kwargs)
    cmdgen_module.UsmUserData = lambda *args, **kwargs: ("usm", args, kwargs)
    cmdgen_module.CommandGenerator = lambda *args, **kwargs: types.SimpleNamespace()
    cmdgen_module.UdpTransportTarget = lambda *args, **kwargs: ("udp", args, kwargs)
    cmdgen_module.MibVariable = lambda *args, **kwargs: ("mib", args, kwargs)

    pysnmp_module = types.ModuleType("pysnmp")
    entity_module = types.ModuleType("pysnmp.entity")
    rfc3413_module = types.ModuleType("pysnmp.entity.rfc3413")
    oneliner_module = types.ModuleType("pysnmp.entity.rfc3413.oneliner")
    oneliner_module.cmdgen = cmdgen_module

    proto_module = types.ModuleType("pysnmp.proto")
    rfc1905_module = types.ModuleType("pysnmp.proto.rfc1905")
    rfc1905_module.EndOfMibView = type("EndOfMibView", (), {})

    hlapi_module = types.ModuleType("pysnmp.hlapi")
    hlapi_module.usmHMACSHAAuthProtocol = object()
    hlapi_module.usmHMACMD5AuthProtocol = object()
    hlapi_module.usmAesCfb128Protocol = object()
    hlapi_module.usmDESPrivProtocol = object()

    monkeypatch.setitem(sys.modules, "sanic", sanic_module)
    monkeypatch.setitem(sys.modules, "sanic.log", sanic_log_module)
    monkeypatch.setitem(sys.modules, "pysnmp", pysnmp_module)
    monkeypatch.setitem(sys.modules, "pysnmp.entity", entity_module)
    monkeypatch.setitem(sys.modules, "pysnmp.entity.rfc3413", rfc3413_module)
    monkeypatch.setitem(sys.modules, "pysnmp.entity.rfc3413.oneliner", oneliner_module)
    monkeypatch.setitem(sys.modules, "pysnmp.entity.rfc3413.oneliner.cmdgen", cmdgen_module)
    monkeypatch.setitem(sys.modules, "pysnmp.proto", proto_module)
    monkeypatch.setitem(sys.modules, "pysnmp.proto.rfc1905", rfc1905_module)
    monkeypatch.setitem(sys.modules, "pysnmp.hlapi", hlapi_module)
    monkeypatch.delitem(sys.modules, "plugins.inputs.network.snmp_facts", raising=False)
    monkeypatch.delitem(sys.modules, "plugins.inputs.network_topo.snmp_topo", raising=False)

    return importlib.import_module("plugins.inputs.network.snmp_facts")


def test_parse_credentials_pool_supports_flattened_params():
    from api.collect import _parse_credentials_pool

    params = {
        "credential_count": "2",
        "credential_0_credential_id": "cred-1",
        "credential_0_username": "admin",
        "credential_0_password": "${PASSWORD_password_cmdb_92_0}",
        "credential_0_port": "22",
        "credential_1_credential_id": "cred-2",
        "credential_1_username": "ops",
        "credential_1_password": "${PASSWORD_password_cmdb_92_1}",
        "credential_1_port": "2200",
    }

    parsed = _parse_credentials_pool(params=params)

    assert parsed == [
        {"credential_id": "cred-1", "username": "admin", "password": "${PASSWORD_password_cmdb_92_0}", "port": "22"},
        {"credential_id": "cred-2", "username": "ops", "password": "${PASSWORD_password_cmdb_92_1}", "port": "2200"},
    ]


def test_build_credential_results_payload_returns_next_since():
    from api.collect import _build_credential_results_payload

    events = [
        {"host": "10.0.0.1", "finished_at": "2026-06-03T12:00:00+00:00"},
        {"host": "10.0.0.2", "finished_at": "2026-06-03T12:05:00+00:00"},
    ]

    payload = _build_credential_results_payload(events)

    assert payload["results"] == events
    assert payload["next_since"] == "2026-06-03T12:05:00+00:00"


def test_network_topology_protocol_registry_contains_expected_groups():
    from plugins.inputs.network_topo.protocol_oids import PROTOCOL_OID_GROUPS

    assert {"arp", "lldp", "cdp", "fdb"}.issubset(PROTOCOL_OID_GROUPS)


def test_network_topology_root_oid_lookup_prefers_matching_prefix():
    from plugins.inputs.network_topo.protocol_oids import get_root_oid

    assert get_root_oid("1.3.6.1.2.1.17.4.3.1.2.10.20.30.40.50.60") == "1.3.6.1.2.1.17.4.3.1.2"
    assert get_root_oid("1.3.6.1.2.1.17.4.3.99") is None


def test_build_topology_fact_uses_protocol_default_confidence_for_lldp_and_fdb():
    from plugins.inputs.network_topo.topology_facts import build_topology_fact

    lldp_fact = build_topology_fact(
        "lldp",
        {
            "local_device_id": "sw-1",
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "sw-2",
            "remote_port_id": "202",
            "remote_port_name": "GigabitEthernet1/0/2",
        },
        raw_evidence={"oid": "1.0.8802.1.1.2.1.4.1.1.7.0.1.1"},
    )
    fdb_fact = build_topology_fact(
        "fdb",
        {
            "local_device_id": "sw-1",
            "local_port_id": "301",
            "local_port_name": "Vlan10",
            "remote_device_id": "00:11:22:33:44:55",
            "remote_port_id": "10",
            "remote_port_name": "dynamic-mac",
        },
        raw_evidence={"oid": "1.3.6.1.2.1.17.4.3.1.2.0.17.34.51.68.85"},
    )

    assert lldp_fact["source_protocol"] == "lldp"
    assert lldp_fact["confidence"] == 0.95
    assert fdb_fact["source_protocol"] == "fdb"
    assert fdb_fact["confidence"] == 0.7


def test_merge_topology_facts_prefers_fdb_over_arp_when_no_stronger_fact_exists():
    from plugins.inputs.network_topo.topology_facts import build_topology_fact, merge_topology_facts

    arp_fact = build_topology_fact(
        "arp",
        {
            "local_device_id": None,
            "local_port_id": "7",
            "local_port_name": "Vlan7",
            "remote_device_id": "10.0.0.8",
            "remote_port_id": None,
            "remote_port_name": None,
        },
        raw_evidence={"source": "arp"},
    )
    fdb_fact = build_topology_fact(
        "fdb",
        {
            "local_device_id": None,
            "local_port_id": "7",
            "local_port_name": "GigabitEthernet1/0/7",
            "remote_device_id": "10.0.0.8",
            "remote_port_id": None,
            "remote_port_name": None,
        },
        raw_evidence={"source": "fdb"},
    )

    assert merge_topology_facts([arp_fact, fdb_fact]) == [fdb_fact]


def test_merge_topology_facts_keeps_arp_as_last_fallback_when_no_stronger_fact_exists():
    from plugins.inputs.network_topo.topology_facts import build_topology_fact, merge_topology_facts

    arp_fact = build_topology_fact(
        "arp",
        {
            "local_device_id": None,
            "local_port_id": "9",
            "local_port_name": "Vlan9",
            "remote_device_id": "10.0.0.9",
            "remote_port_id": None,
            "remote_port_name": None,
        },
        raw_evidence={"source": "arp"},
    )

    assert merge_topology_facts([arp_fact]) == [arp_fact]


def test_merge_topology_facts_preserves_stronger_fact_on_exact_full_edge_duplicate():
    from plugins.inputs.network_topo.topology_facts import build_topology_fact, merge_topology_facts

    cdp_fact = build_topology_fact(
        "cdp",
        {
            "local_device_id": None,
            "local_port_id": "7",
            "local_port_name": "GigabitEthernet1/0/7",
            "remote_device_id": "core-sw-1",
            "remote_port_id": "Gi1/0/48",
            "remote_port_name": "GigabitEthernet1/0/48",
        },
        raw_evidence={"source": "cdp"},
        confidence=0.95,
    )
    lldp_fact = build_topology_fact(
        "lldp",
        {
            "local_device_id": None,
            "local_port_id": "7",
            "local_port_name": "Ethernet7",
            "remote_device_id": "core-sw-1",
            "remote_port_id": "Gi1/0/48",
            "remote_port_name": "uplink-to-core",
        },
        raw_evidence={"source": "lldp"},
        confidence=0.95,
    )

    assert merge_topology_facts([cdp_fact, lldp_fact]) == [lldp_fact]


def test_merge_topology_facts_prefers_higher_confidence_across_protocols_for_same_full_edge():
    from plugins.inputs.network_topo.topology_facts import build_topology_fact, merge_topology_facts

    default_lldp_fact = build_topology_fact(
        "lldp",
        {
            "local_device_id": "access-sw-1",
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "dist-sw-1",
            "remote_port_id": "GigabitEthernet1/0/24",
            "remote_port_name": "GigabitEthernet1/0/24",
        },
        raw_evidence={"source": "lldp-default"},
    )
    higher_confidence_fdb_fact = build_topology_fact(
        "fdb",
        {
            "local_device_id": "access-sw-1",
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "dist-sw-1",
            "remote_port_id": "GigabitEthernet1/0/24",
            "remote_port_name": "dynamic-mac",
        },
        raw_evidence={"source": "fdb-override"},
        confidence=0.99,
    )

    assert merge_topology_facts([default_lldp_fact, higher_confidence_fdb_fact]) == [higher_confidence_fdb_fact]


def test_merge_topology_facts_prefers_higher_confidence_for_same_edge_key():
    from plugins.inputs.network_topo.topology_facts import build_topology_fact, merge_topology_facts

    weaker_lldp_fact = build_topology_fact(
        "lldp",
        {
            "local_device_id": None,
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "dist-sw-1",
            "remote_port_id": "GigabitEthernet1/0/24",
            "remote_port_name": "GigabitEthernet1/0/24",
        },
        raw_evidence={"source": "lldp-weak"},
        confidence=0.82,
    )
    stronger_lldp_fact = build_topology_fact(
        "lldp",
        {
            "local_device_id": None,
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "dist-sw-1",
            "remote_port_id": "GigabitEthernet1/0/24",
            "remote_port_name": "GigabitEthernet1/0/24",
        },
        raw_evidence={"source": "lldp-strong"},
        confidence=0.97,
    )

    assert merge_topology_facts([weaker_lldp_fact, stronger_lldp_fact]) == [stronger_lldp_fact]


def test_snmp_topo_format_result_preserves_raw_row_shape_after_registry_refactor(monkeypatch):
    from plugins.inputs.network_topo.protocol_oids import NETWORK_TOPO_OIDS

    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo

    class FakeValue:
        def __init__(self, value):
            self.value = value

        def prettyPrint(self):
            return self.value

    varbinds = [[
        (
            FakeValue("1.3.6.1.2.1.4.22.1.1.192.168.1.10"),
            FakeValue("7"),
        ),
        (
            FakeValue("1.3.6.1.2.1.2.2.1.2.7"),
            FakeValue("GigabitEthernet1/0/7"),
        ),
    ]]

    result = SnmpTopo._format_result(varbinds, eval_oids=NETWORK_TOPO_OIDS)

    assert result == [
        {
            "root": "1.3.6.1.2.1.4.22.1.1",
            "key": "1.3.6.1.2.1.4.22.1.1.192.168.1.10",
            "tag": "ARP-IfIndex",
            "ifindex": "192.168.1.10",
            "ifindex_type": "ipaddr",
            "val": "7",
            "group": "arp",
        },
        {
            "root": "1.3.6.1.2.1.2.2.1.2",
            "key": "1.3.6.1.2.1.2.2.1.2.7",
            "tag": "IFTable-IfDescr",
            "ifindex": "7",
            "ifindex_type": "default",
            "val": "GigabitEthernet1/0/7",
            "group": "interfaces",
        },
    ]


def test_snmp_topo_format_result_prefers_longest_matching_eval_oid(monkeypatch):
    snmp_topo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch)

    class FakeValue:
        def __init__(self, value):
            self.value = value

        def prettyPrint(self):
            return self.value

    def parse_suffix(oid, root_oid):
        return oid[len(root_oid) + 1:] if oid != root_oid else None

    fake_oid_meta = {
        "1.2.3": {
            "tag": "short-root",
            "ifindex_type": "suffix",
            "index_parser": parse_suffix,
        },
        "1.2.3.4": {
            "tag": "long-root",
            "ifindex_type": "suffix",
            "index_parser": parse_suffix,
        },
    }

    monkeypatch.setattr(snmp_topo, "get_oid_meta", lambda root_oid: fake_oid_meta[root_oid])

    result = snmp_topo.SnmpTopo._format_result(
        [[(FakeValue("1.2.3.4.5"), FakeValue("value"))]],
        eval_oids=["1.2.3", "1.2.3.4"],
    )

    assert result == [
        {
            "root": "1.2.3.4",
            "key": "1.2.3.4.5",
            "tag": "long-root",
            "ifindex": "5",
            "ifindex_type": "suffix",
            "val": "value",
            "group": "interfaces",
        }
    ]


def test_snmp_topo_build_topology_facts_builds_lldp_neighbor_evidence(monkeypatch):
    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo

    snmp_rows = [
        {"tag": "LLDP-LocPortId", "ifindex": "101", "val": "GigabitEthernet1/0/1"},
        {"tag": "LLDP-RemSysName", "ifindex": "8457.101.1", "val": "dist-sw-1"},
        {"tag": "LLDP-RemPortId", "ifindex": "8457.101.1", "val": "GigabitEthernet1/0/24"},
    ]

    facts = SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=("lldp",))

    assert facts == [
        {
            "source_protocol": "lldp",
            "confidence": 0.95,
            "local_device_id": None,
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "dist-sw-1",
            "remote_port_id": "GigabitEthernet1/0/24",
            "remote_port_name": "GigabitEthernet1/0/24",
            "raw_evidence": {
                "local_port": snmp_rows[0],
                "remote_system": snmp_rows[1],
                "remote_port": snmp_rows[2],
            },
        }
    ]


def test_snmp_topo_extract_lldp_local_ifindex_uses_local_port_component(monkeypatch):
    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo

    assert SnmpTopo._extract_lldp_local_ifindex("8457.101.1") == "101"


def test_snmp_topo_build_topology_facts_builds_cdp_neighbor_evidence(monkeypatch):
    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo

    snmp_rows = [
        {"tag": "IFTable-IfDescr", "ifindex": "7", "val": "GigabitEthernet1/0/7"},
        {"tag": "CDP-DeviceId", "ifindex": "7.1", "val": "core-sw-1"},
        {"tag": "CDP-DevicePort", "ifindex": "7.1", "val": "GigabitEthernet1/0/48"},
    ]

    facts = SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=("cdp",))

    assert facts == [
        {
            "source_protocol": "cdp",
            "confidence": 0.9,
            "local_device_id": None,
            "local_port_id": "7",
            "local_port_name": "GigabitEthernet1/0/7",
            "remote_device_id": "core-sw-1",
            "remote_port_id": "GigabitEthernet1/0/48",
            "remote_port_name": "GigabitEthernet1/0/48",
            "raw_evidence": {
                "local_port": snmp_rows[0],
                "remote_device": snmp_rows[1],
                "remote_port": snmp_rows[2],
            },
        }
    ]


def test_snmp_topo_build_topology_facts_returns_no_neighbor_facts_for_explicit_empty_or_unsupported_protocols(monkeypatch):
    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo

    snmp_rows = [
        {"tag": "LLDP-LocPortId", "ifindex": "101", "val": "GigabitEthernet1/0/1"},
        {"tag": "LLDP-RemSysName", "ifindex": "8457.101.1", "val": "dist-sw-1"},
        {"tag": "LLDP-RemPortId", "ifindex": "8457.101.1", "val": "GigabitEthernet1/0/24"},
        {"tag": "IFTable-IfDescr", "ifindex": "7", "val": "GigabitEthernet1/0/7"},
        {"tag": "CDP-DeviceId", "ifindex": "7.1", "val": "core-sw-1"},
        {"tag": "CDP-DevicePort", "ifindex": "7.1", "val": "GigabitEthernet1/0/48"},
    ]

    assert SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=()) == []
    assert SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=("ospf",)) == []


def test_snmp_topo_build_topology_facts_skips_fdb_when_bridge_port_mapping_missing(monkeypatch):
    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo
    snmp_rows = [
        {"tag": "FDB-MacAddress", "ifindex": "0.17.34.51.68.85", "val": "00:11:22:33:44:55"},
        {"tag": "FDB-Port", "ifindex": "0.17.34.51.68.85", "val": "10"},
        {"tag": "IFTable-IfDescr", "ifindex": "15", "val": "GigabitEthernet1/0/15"},
        {"tag": "IFTable-IfAlias", "ifindex": "15", "val": "server-uplink"},
    ]

    assert SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=("fdb",)) == []


def test_snmp_topo_build_topology_facts_builds_fdb_neighbor_when_bridge_port_mapping_exists(monkeypatch):
    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo

    snmp_rows = [
        {"tag": "FDB-MacAddress", "ifindex": "0.17.34.51.68.85", "val": "00:11:22:33:44:55"},
        {"tag": "FDB-Port", "ifindex": "0.17.34.51.68.85", "val": "10"},
        {"tag": "BRIDGE-BasePortIfIndex", "ifindex": "10", "val": "15"},
        {"tag": "IFTable-IfDescr", "ifindex": "15", "val": "GigabitEthernet1/0/15"},
        {"tag": "IFTable-IfAlias", "ifindex": "15", "val": "server-uplink"},
    ]

    assert SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=("fdb", "arp")) == [
        {
            "source_protocol": "fdb",
            "confidence": 0.7,
            "local_device_id": None,
            "local_port_id": "15",
            "local_port_name": "server-uplink",
            "remote_device_id": "00:11:22:33:44:55",
            "remote_port_id": None,
            "remote_port_name": None,
            "raw_evidence": {
                "local_port": snmp_rows[3],
                "local_port_alias": snmp_rows[4],
                "bridge_port": snmp_rows[2],
                "fdb_mac": snmp_rows[0],
                "fdb_port": snmp_rows[1],
            },
        }
    ]


def test_snmp_topo_default_oid_collection_includes_fdb_fallback_without_duplicates(monkeypatch):
    snmp_topo_module = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch)
    SnmpTopo = snmp_topo_module.SnmpTopo

    default_oids = SnmpTopo._build_oids()
    expected_fdb_oids = [
        entry["key"] for entry in snmp_topo_module.flatten_oid_registry(("fdb",))
    ]

    assert set(expected_fdb_oids).issubset(default_oids)
    assert len(default_oids) == len(set(default_oids))


@pytest.mark.parametrize(
    ("configured_timeout", "expected_probe_timeout"),
    [(3, 3), (5, 5), (10, 5)],
)
def test_snmp_facts_caps_initial_probe_timeout_without_shortening_followup_collection(
    monkeypatch,
    configured_timeout,
    expected_probe_timeout,
):
    snmp_facts_module = _import_snmp_facts_with_stubbed_deps(monkeypatch)
    transport_options = []

    class FakeCommandGenerator:
        @staticmethod
        def getCmd(*args, **kwargs):
            return None, None, None, []

        @staticmethod
        def nextCmd(*args, **kwargs):
            return None, None, None, []

    def capture_transport_target(address, **kwargs):
        transport_options.append(kwargs)
        return "udp", address, kwargs

    monkeypatch.setattr(
        snmp_facts_module.cmdgen,
        "CommandGenerator",
        FakeCommandGenerator,
    )
    monkeypatch.setattr(
        snmp_facts_module.cmdgen,
        "UdpTransportTarget",
        capture_transport_target,
    )

    collector = snmp_facts_module.SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2c",
            "community": "public",
            "timeout": configured_timeout,
        }
    )

    collector.collect()

    assert transport_options[0] == {"timeout": expected_probe_timeout, "retries": 2}
    assert transport_options[1] == {"timeout": configured_timeout, "retries": 2}


@pytest.mark.asyncio
async def test_snmp_facts_list_all_resources_adds_network_topology_facts_without_changing_raw_topo(monkeypatch):
    snmp_facts_module = _import_snmp_facts_with_stubbed_deps(monkeypatch)

    raw_topology_rows = [
        {"tag": "ARP-IfIndex", "ifindex": "192.168.1.10", "val": "7"},
    ]
    topology_facts = [
        {"source_protocol": "lldp", "remote_device_id": "dist-sw-1"},
    ]

    class FakeSnmpTopo:
        def __init__(self, kwargs):
            self.kwargs = kwargs

        def bulkCmd(self):
            return raw_topology_rows

        @staticmethod
        def build_topology_facts(snmp_rows, enabled_protocols=None):
            assert snmp_rows == raw_topology_rows
            assert enabled_protocols == ("lldp", "cdp")
            return topology_facts

    monkeypatch.setattr(snmp_facts_module, "SnmpTopo", FakeSnmpTopo)
    monkeypatch.setattr(
        snmp_facts_module.SnmpFacts,
        "collect",
        lambda self: {"system": {"sysname": "edge-sw-1"}, "interfaces": [{"index": "7"}]},
    )

    result = await snmp_facts_module.SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2c",
            "community": "public",
            "has_network_topo": "True",
            "topology_protocols": ("lldp", "cdp"),
        }
    ).list_all_resources()

    assert result["success"] is True
    assert result["result"]["network_topo"] == raw_topology_rows
    assert result["result"]["network_topology_facts"] == topology_facts
    assert result["result"]["network_system"] == [{"sysname": "edge-sw-1"}]


@pytest.mark.asyncio
async def test_snmp_facts_list_all_resources_uses_default_neighbor_protocols_when_topology_protocols_omitted(monkeypatch):
    snmp_facts_module = _import_snmp_facts_with_stubbed_deps(monkeypatch)
    snmp_topo_module = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch)

    raw_topology_rows = [
        {"tag": "LLDP-LocPortId", "ifindex": "101", "val": "GigabitEthernet1/0/1"},
        {"tag": "LLDP-RemSysName", "ifindex": "8457.101.1", "val": "dist-sw-1"},
        {"tag": "LLDP-RemPortId", "ifindex": "8457.101.1", "val": "GigabitEthernet1/0/24"},
    ]

    class FakeSnmpTopo:
        def __init__(self, kwargs):
            self.kwargs = kwargs

        def bulkCmd(self):
            return raw_topology_rows

        @staticmethod
        def build_topology_facts(snmp_rows, enabled_protocols=None):
            assert snmp_rows == raw_topology_rows
            assert enabled_protocols is None
            return snmp_topo_module.SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=enabled_protocols)

    monkeypatch.setattr(snmp_facts_module, "SnmpTopo", FakeSnmpTopo)
    monkeypatch.setattr(
        snmp_facts_module.SnmpFacts,
        "collect",
        lambda self: {"system": {"sysname": "edge-sw-1"}, "interfaces": [{"index": "7"}]},
    )

    result = await snmp_facts_module.SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2c",
            "community": "public",
            "has_network_topo": "True",
        }
    ).list_all_resources()

    assert result["success"] is True
    assert result["result"]["network_topology_facts"] == [
        {
            "source_protocol": "lldp",
            "confidence": 0.95,
            "local_device_id": None,
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "dist-sw-1",
            "remote_port_id": "GigabitEthernet1/0/24",
            "remote_port_name": "GigabitEthernet1/0/24",
            "raw_evidence": {
                "local_port": raw_topology_rows[0],
                "remote_system": raw_topology_rows[1],
                "remote_port": raw_topology_rows[2],
            },
        }
    ]


@pytest.mark.asyncio
async def test_snmp_facts_list_all_resources_uses_fdb_default_fallback_when_topology_protocols_omitted(monkeypatch):
    snmp_facts_module = _import_snmp_facts_with_stubbed_deps(monkeypatch)
    snmp_topo_module = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch)

    raw_topology_rows = [
        {"tag": "FDB-MacAddress", "ifindex": "0.17.34.51.68.85", "val": "00:11:22:33:44:55"},
        {"tag": "FDB-Port", "ifindex": "0.17.34.51.68.85", "val": "10"},
        {"tag": "BRIDGE-BasePortIfIndex", "ifindex": "10", "val": "15"},
        {"tag": "IFTable-IfDescr", "ifindex": "15", "val": "GigabitEthernet1/0/15"},
        {"tag": "IFTable-IfAlias", "ifindex": "15", "val": "server-uplink"},
    ]

    class FakeSnmpTopo:
        def __init__(self, kwargs):
            self.kwargs = kwargs

        def bulkCmd(self):
            return raw_topology_rows

        @staticmethod
        def build_topology_facts(snmp_rows, enabled_protocols=None):
            assert snmp_rows == raw_topology_rows
            assert enabled_protocols is None
            return snmp_topo_module.SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=enabled_protocols)

    monkeypatch.setattr(snmp_facts_module, "SnmpTopo", FakeSnmpTopo)
    monkeypatch.setattr(
        snmp_facts_module.SnmpFacts,
        "collect",
        lambda self: {"system": {"sysname": "edge-sw-1"}, "interfaces": [{"index": "15"}]},
    )

    result = await snmp_facts_module.SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2c",
            "community": "public",
            "has_network_topo": "True",
        }
    ).list_all_resources()

    assert result["success"] is True
    assert result["result"]["network_topology_facts"] == [
        {
            "source_protocol": "fdb",
            "confidence": 0.7,
            "local_device_id": None,
            "local_port_id": "15",
            "local_port_name": "server-uplink",
            "remote_device_id": "00:11:22:33:44:55",
            "remote_port_id": None,
            "remote_port_name": None,
            "raw_evidence": {
                "local_port": raw_topology_rows[3],
                "local_port_alias": raw_topology_rows[4],
                "bridge_port": raw_topology_rows[2],
                "fdb_mac": raw_topology_rows[0],
                "fdb_port": raw_topology_rows[1],
            },
        }
    ]


@pytest.mark.asyncio
async def test_snmp_facts_list_all_resources_preserves_raw_topology_when_fact_building_fails(monkeypatch):
    snmp_facts_module = _import_snmp_facts_with_stubbed_deps(monkeypatch)

    raw_topology_rows = [
        {"tag": "LLDP-RemSysName", "ifindex": "8457.101.1", "val": "dist-sw-1"},
    ]

    class FakeSnmpTopo:
        def __init__(self, kwargs):
            self.kwargs = kwargs

        def bulkCmd(self):
            return raw_topology_rows

        @staticmethod
        def build_topology_facts(snmp_rows, enabled_protocols=None):
            assert snmp_rows == raw_topology_rows
            raise ValueError("invalid topology fact payload")

    monkeypatch.setattr(snmp_facts_module, "SnmpTopo", FakeSnmpTopo)
    monkeypatch.setattr(
        snmp_facts_module.SnmpFacts,
        "collect",
        lambda self: {"system": {"sysname": "edge-sw-1"}, "interfaces": [{"index": "7"}]},
    )

    result = await snmp_facts_module.SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2c",
            "community": "public",
            "has_network_topo": "True",
        }
    ).list_all_resources()

    assert result["success"] is True
    assert result["result"]["network_topo"] == raw_topology_rows
    assert result["result"]["network_topology_facts"] == []
