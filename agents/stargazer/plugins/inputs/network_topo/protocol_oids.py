def _parse_default_index(oid, root_oid):
    if oid == root_oid:
        return None
    return oid.rsplit(".", 1)[-1]


def _parse_ipaddr_index(oid, root_oid):
    if oid == root_oid:
        return None
    return ".".join(oid.rsplit(".", 4)[-4:])


def _parse_suffix_index(oid, root_oid):
    if oid == root_oid:
        return None
    return oid[len(root_oid) + 1:]


PROTOCOL_OID_GROUPS = {
    "arp": {
        "default_confidence": 0.6,
        "oids": [
            {
                "key": "1.3.6.1.2.1.4.22.1.1",
                "tag": "ARP-IfIndex",
                "ifindex_type": "ipaddr",
                "index_kind": "ipaddr",
                "index_parser": _parse_ipaddr_index,
            },
            {
                "key": "1.3.6.1.2.1.4.22.1.2",
                "tag": "ARP-PhysAddress",
                "ifindex_type": "ipaddr",
                "index_kind": "ipaddr",
                "index_parser": _parse_ipaddr_index,
            },
        ],
    },
    "lldp": {
        "default_confidence": 0.95,
        "oids": [
            {
                "key": "1.0.8802.1.1.2.1.3.7.1.3",
                "tag": "LLDP-LocalPortId",
                "ifindex_type": "suffix",
                "index_kind": "lldp_local_port",
                "index_parser": _parse_suffix_index,
            },
            {
                "key": "1.0.8802.1.1.2.1.4.1.1.7",
                "tag": "LLDP-RemPortId",
                "ifindex_type": "suffix",
                "index_kind": "lldp_remote_port",
                "index_parser": _parse_suffix_index,
            },
            {
                "key": "1.0.8802.1.1.2.1.4.1.1.9",
                "tag": "LLDP-RemSysName",
                "ifindex_type": "suffix",
                "index_kind": "lldp_remote_system",
                "index_parser": _parse_suffix_index,
            },
        ],
    },
    "cdp": {
        "default_confidence": 0.9,
        "oids": [
            {
                "key": "1.3.6.1.4.1.9.9.23.1.2.1.1.6",
                "tag": "CDP-CacheDeviceId",
                "ifindex_type": "suffix",
                "index_kind": "cdp_cache",
                "index_parser": _parse_suffix_index,
            },
            {
                "key": "1.3.6.1.4.1.9.9.23.1.2.1.1.7",
                "tag": "CDP-CacheDevicePort",
                "ifindex_type": "suffix",
                "index_kind": "cdp_cache",
                "index_parser": _parse_suffix_index,
            },
        ],
    },
    "fdb": {
        "default_confidence": 0.7,
        "oids": [
            {
                "key": "1.3.6.1.2.1.17.1.4.1.2",
                "tag": "BRIDGE-MIB-BasePortIfIndex",
                "ifindex_type": "default",
                "index_kind": "bridge_port",
                "index_parser": _parse_default_index,
            },
            {
                "key": "1.3.6.1.2.1.17.4.3.1.1",
                "tag": "FDB-MacAddress",
                "ifindex_type": "suffix",
                "index_kind": "mac_address",
                "index_parser": _parse_suffix_index,
            },
            {
                "key": "1.3.6.1.2.1.17.4.3.1.2",
                "tag": "FDB-Port",
                "ifindex_type": "suffix",
                "index_kind": "mac_address",
                "index_parser": _parse_suffix_index,
            },
        ],
    },
    "interface": {
        "oids": [
            {
                "key": "1.3.6.1.2.1.2.2.1.2",
                "tag": "IFTable-IfDescr",
                "ifindex_type": "default",
                "index_kind": "ifindex",
                "index_parser": _parse_default_index,
            },
            {
                "key": "1.3.6.1.2.1.2.2.1.6",
                "tag": "IFTable-PhysAddress",
                "ifindex_type": "default",
                "index_kind": "ifindex",
                "index_parser": _parse_default_index,
            },
            {
                "key": "1.3.6.1.2.1.31.1.1.1.18",
                "tag": "IFTable-IfAlias",
                "ifindex_type": "default",
                "index_kind": "ifindex",
                "index_parser": _parse_default_index,
            },
        ],
    },
    "ipaddr": {
        "oids": [
            {
                "key": "1.3.6.1.2.1.4.20.1.1",
                "tag": "IpAddr-IpAddr",
                "ifindex_type": "ipaddr",
                "index_kind": "ipaddr",
                "index_parser": _parse_ipaddr_index,
            },
        ],
    },
}


def flatten_oid_registry(group_names=None):
    names = group_names or PROTOCOL_OID_GROUPS.keys()
    registry = []
    for group_name in names:
        group = PROTOCOL_OID_GROUPS[group_name]
        for oid_meta in group["oids"]:
            registry.append(
                {
                    **oid_meta,
                    "protocol": group_name,
                    "default_confidence": group.get("default_confidence"),
                }
            )
    return registry


ALL_PROTOCOL_OID_REGISTRY = flatten_oid_registry()
ALL_PROTOCOL_OID_MAP = {entry["key"]: entry for entry in ALL_PROTOCOL_OID_REGISTRY}
NETWORK_TOPO_REGISTRY = flatten_oid_registry(("arp", "interface", "ipaddr"))
NETWORK_TOPO_OIDS = [entry["key"] for entry in NETWORK_TOPO_REGISTRY]


def _matches_root(oid, root_oid):
    return oid == root_oid or oid.startswith(f"{root_oid}.")


def get_root_oid(oid, roots=None):
    candidate_roots = roots or ALL_PROTOCOL_OID_MAP.keys()
    matches = [root_oid for root_oid in candidate_roots if _matches_root(oid, root_oid)]
    if not matches:
        return None
    return max(matches, key=len)


def get_oid_meta(root_oid):
    return ALL_PROTOCOL_OID_MAP.get(root_oid, {})
