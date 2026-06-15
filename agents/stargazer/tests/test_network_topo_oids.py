from plugins.inputs.network_topo.protocol_oids import (
    ALL_PROTOCOL_OID_MAP,
    PROTOCOL_OID_GROUPS,
    flatten_oid_registry,
)


REQUIRED_TAGS = {
    # system
    "1.3.6.1.2.1.1.5": ("System-SysName", "system"),
    # interfaces（新增 IFXTable-IfName）
    "1.3.6.1.2.1.31.1.1.1.1": ("IFXTable-IfName", "interfaces"),
    "1.3.6.1.2.1.2.2.1.2": ("IFTable-IfDescr", "interfaces"),
    # lldp 本地端口表与远端补充
    "1.0.8802.1.1.2.1.3.7.1.2": ("LLDP-LocPortIdSubtype", "neighbors"),
    "1.0.8802.1.1.2.1.3.7.1.3": ("LLDP-LocPortId", "neighbors"),
    "1.0.8802.1.1.2.1.3.7.1.4": ("LLDP-LocPortDesc", "neighbors"),
    "1.0.8802.1.1.2.1.4.1.1.4": ("LLDP-RemChassisIdSubtype", "neighbors"),
    "1.0.8802.1.1.2.1.4.1.1.5": ("LLDP-RemChassisId", "neighbors"),
    "1.0.8802.1.1.2.1.4.1.1.6": ("LLDP-RemPortIdSubtype", "neighbors"),
    "1.0.8802.1.1.2.1.4.1.1.8": ("LLDP-RemPortDesc", "neighbors"),
    # cdp 补充
    "1.3.6.1.4.1.9.9.23.1.2.1.1.3": ("CDP-AddressType", "neighbors"),
    "1.3.6.1.4.1.9.9.23.1.2.1.1.4": ("CDP-Address", "neighbors"),
    "1.3.6.1.4.1.9.9.23.1.2.1.1.6": ("CDP-DeviceId", "neighbors"),
    "1.3.6.1.4.1.9.9.23.1.2.1.1.7": ("CDP-DevicePort", "neighbors"),
    "1.3.6.1.4.1.9.9.23.1.2.1.1.8": ("CDP-Platform", "neighbors"),
    "1.3.6.1.4.1.9.9.23.1.2.1.1.17": ("CDP-SysName", "neighbors"),
    # fdp
    "1.3.6.1.4.1.1991.1.1.3.20.1.2.1.1.3": ("FDP-DeviceId", "neighbors"),
    "1.3.6.1.4.1.1991.1.1.3.20.1.2.1.1.6": ("FDP-Version", "neighbors"),
    "1.3.6.1.4.1.1991.1.1.3.20.1.2.1.1.7": ("FDP-DevicePort", "neighbors"),
    "1.3.6.1.4.1.1991.1.1.3.20.1.2.1.1.8": ("FDP-Platform", "neighbors"),
    # bridge / fdb / qbridge
    "1.3.6.1.2.1.17.1.4.1.2": ("BRIDGE-BasePortIfIndex", "bridge"),
    "1.3.6.1.2.1.17.4.3.1.2": ("FDB-Port", "fdb"),
    "1.3.6.1.2.1.17.4.3.1.3": ("FDB-Status", "fdb"),
    "1.3.6.1.2.1.17.7.1.2.2.1.2": ("QBRIDGE-FdbPort", "fdb"),
    "1.3.6.1.2.1.17.7.1.2.2.1.3": ("QBRIDGE-FdbStatus", "fdb"),
}


def test_registry_covers_required_oids_with_groups():
    for oid, (tag, group) in REQUIRED_TAGS.items():
        meta = ALL_PROTOCOL_OID_MAP.get(oid)
        assert meta is not None, f"missing OID {oid} ({tag})"
        assert meta["tag"] == tag
        assert meta["group"] == group


def test_every_registry_entry_has_group():
    for entry in flatten_oid_registry():
        assert entry.get("group"), f"OID {entry['key']} missing group"


def test_fdp_is_a_selectable_protocol_group():
    assert "fdp" in PROTOCOL_OID_GROUPS
