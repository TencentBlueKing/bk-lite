# 移植自 snmp_topo_tool/parse_topology.py（独立工具，已真机验证）。
# 修改时需与工具侧保持同步。
from __future__ import annotations

import ipaddress
from collections import defaultdict
from typing import Any

from apps.cmdb.collection.collect_plugin.topology.models import (
    ArpObservation,
    FdbObservation,
    LinkCandidate,
    NeighborObservation,
    NormalizedDevice,
    NormalizedPort,
)


LLDP_PORT_SUBTYPE_INTERFACE_ALIAS = "1"
LLDP_PORT_SUBTYPE_PORT_COMPONENT = "2"
LLDP_PORT_SUBTYPE_MAC_ADDRESS = "3"
LLDP_PORT_SUBTYPE_NETWORK_ADDRESS = "4"
LLDP_PORT_SUBTYPE_INTERFACE_NAME = "5"
LLDP_PORT_SUBTYPE_AGENT_CIRCUIT_ID = "6"
LLDP_PORT_SUBTYPE_LOCAL = "7"

LLDP_CHASSIS_SUBTYPE_CHASSIS_COMPONENT = "1"
LLDP_CHASSIS_SUBTYPE_INTERFACE_ALIAS = "2"
LLDP_CHASSIS_SUBTYPE_PORT_COMPONENT = "3"
LLDP_CHASSIS_SUBTYPE_MAC_ADDRESS = "4"
LLDP_CHASSIS_SUBTYPE_NETWORK_ADDRESS = "5"
LLDP_CHASSIS_SUBTYPE_INTERFACE_NAME = "6"
LLDP_CHASSIS_SUBTYPE_LOCAL = "7"


def extract_previous_links(payload):
    """从上一轮 parsed 结果 dict 中提取 current 链路列表（authoritative + inferred）。"""
    if not isinstance(payload, dict):
        return []
    topology = payload.get("topology", {})
    if isinstance(topology, dict):
        combined = []
        for key in ("authoritative_links", "inferred_links"):
            items = topology.get(key, [])
            if isinstance(items, list):
                combined.extend(item for item in items if isinstance(item, dict))
        return combined
    relationships = payload.get("relationships", [])
    if isinstance(relationships, list):
        return [item for item in relationships if isinstance(item, dict)]
    return []


def normalize_mac(mac: str) -> str:
    value = (mac or "").strip().lower()
    if value.startswith("0x"):
        value = value[2:]
    if not value:
        return ""
    if ":" in value:
        return value
    return ":".join(value[i : i + 2] for i in range(0, len(value), 2))


def normalize_mac_from_oid_suffix(suffix: str) -> str:
    value = (suffix or "").strip()
    if not value:
        return ""
    parts = [part for part in value.split(".") if part != ""]
    if len(parts) == 6 and all(part.isdigit() for part in parts):
        return ":".join(f"{int(part):02x}" for part in parts)
    return normalize_mac(value.replace(".", ""))


def decode_ipv4ish(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if "." in value and all(part.isdigit() for part in value.split(".")):
        parts = value.split(".")
        if len(parts) == 4:
            return value
        if len(parts) == 5:
            return ".".join(parts[1:])
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    if value.startswith("0x"):
        hex_value = value[2:]
        if len(hex_value) == 8:
            try:
                octets = [str(int(hex_value[index : index + 2], 16)) for index in range(0, 8, 2)]
                return ".".join(octets)
            except ValueError:
                return value
    return value


def decode_cdp_address(address_type: str, raw_value: str) -> str:
    if not raw_value:
        return ""
    if address_type in {"1", "ip", "ipv4"}:
        value = (raw_value or "").strip()
        if value.startswith("0x"):
            hex_value = value[2:]
            if len(hex_value) == 10:
                try:
                    afi = int(hex_value[:2], 16)
                    if afi == 1:
                        octets = [str(int(hex_value[index : index + 2], 16)) for index in range(2, 10, 2)]
                        return ".".join(octets)
                except ValueError:
                    return value
        return decode_ipv4ish(value)
    return decode_ipv4ish(raw_value)


def decode_lldp_port_id(subtype: str, raw_value: str) -> tuple[str, int]:
    value = str(raw_value or "")
    if subtype in {LLDP_PORT_SUBTYPE_INTERFACE_NAME, LLDP_PORT_SUBTYPE_INTERFACE_ALIAS}:
        return value, 100
    if subtype == LLDP_PORT_SUBTYPE_MAC_ADDRESS:
        return normalize_mac(value), 80
    if subtype == LLDP_PORT_SUBTYPE_NETWORK_ADDRESS:
        return decode_ipv4ish(value), 60
    if subtype == LLDP_PORT_SUBTYPE_LOCAL:
        return value, 50
    if subtype in {LLDP_PORT_SUBTYPE_PORT_COMPONENT, LLDP_PORT_SUBTYPE_AGENT_CIRCUIT_ID}:
        return value, 30
    return value, 40


def decode_lldp_chassis_id(subtype: str, raw_value: str) -> str:
    value = str(raw_value or "")
    if not value:
        return ""
    if subtype == LLDP_CHASSIS_SUBTYPE_MAC_ADDRESS:
        return normalize_mac(value)
    if subtype == LLDP_CHASSIS_SUBTYPE_NETWORK_ADDRESS:
        return decode_ipv4ish(value)
    return value


def get_neighbor_identifier_quality(protocol: str, remote_port_subtype: str, remote_port_value: str) -> int:
    if protocol == "cdp":
        return 5 if str(remote_port_value or "").strip() else 0
    if remote_port_subtype in {LLDP_PORT_SUBTYPE_INTERFACE_NAME, LLDP_PORT_SUBTYPE_INTERFACE_ALIAS}:
        return 10
    if remote_port_subtype == LLDP_PORT_SUBTYPE_MAC_ADDRESS:
        return 5
    if remote_port_subtype == LLDP_PORT_SUBTYPE_NETWORK_ADDRESS:
        return 0
    if remote_port_subtype == LLDP_PORT_SUBTYPE_LOCAL:
        return 0
    return 0


def build_unresolved_neighbor_entry(
    observation: dict[str, Any],
    source_port: NormalizedPort | None,
    resolution_state: str,
    decision_reason: str,
    confidence: int,
    supporting_signals: list[str],
) -> dict[str, Any]:
    return {
        "protocol": observation.get("protocol"),
        "evidence_key": observation.get("evidence_key"),
        "source_device": observation.get("source_device_id"),
        "source_port_id": source_port.port_id if source_port else observation.get("local_port_id"),
        "source_inst_name": make_interface_inst_name(
            str(observation.get("source_device_id", "unknown")),
            source_port,
        ),
        "remote_device_name": observation.get("remote_system_name") or observation.get("remote_chassis_id"),
        "remote_port_name": observation.get("remote_port_id") or observation.get("remote_port_value"),
        "remote_address": observation.get("remote_address"),
        "resolution_state": resolution_state,
        "confidence": confidence,
        "decision_reason": decision_reason,
        "supporting_signals": supporting_signals,
        "conflicting_signals": [],
        "conflicts_with_relationship_id": None,
        "raw_remote_fields": observation.get("raw_remote_fields", {}),
    }


def summarize_supporting_candidate(candidate: dict[str, Any], disposition: str, winner_link_id: str) -> dict[str, Any]:
    return {
        "relationship_id": candidate.get("relationship_id"),
        "relationship_type": candidate.get("relationship_type"),
        "evidence_source": candidate.get("evidence_source"),
        "confidence": candidate.get("confidence"),
        "status": candidate.get("status"),
        "remote_device_name": candidate.get("remote_device_name"),
        "remote_port_name": candidate.get("remote_port_name"),
        "vlan": candidate.get("vlan"),
        "disposition": disposition,
        "winner_link_id": winner_link_id,
        "provenance": candidate.get("provenance", []),
    }


def append_supporting_evidence(winner: dict[str, Any], candidate: dict[str, Any], disposition: str) -> None:
    supporting = winner.setdefault("supporting_evidence", [])
    if not isinstance(supporting, list):
        supporting = []
        winner["supporting_evidence"] = supporting
    supporting.append(
        summarize_supporting_candidate(
            candidate=candidate,
            disposition=disposition,
            winner_link_id=str(winner.get("relationship_id", "")),
        )
    )


def canonical_device_labels(device: dict[str, Any]) -> set[str]:
    labels: set[str] = set()
    host = str(device.get("host", "") or "").strip()
    sys_name = str(device.get("sys_name", "") or "").strip()
    if host:
        labels.add(host)
    if sys_name:
        labels.add(sys_name)
    for ip_address in device.get("ips", []):
        value = str(ip_address or "").strip()
        if value:
            labels.add(value)
    return labels


def build_device_label_indexes(
    devices: dict[str, dict[str, Any]],
    ports: dict[str, NormalizedPort],
) -> tuple[dict[str, str], dict[str, set[str]]]:
    device_labels: dict[str, set[str]] = {}
    label_to_devices: dict[str, set[str]] = defaultdict(set)
    device_identity_macs = build_device_identity_mac_sets(ports)

    for device_id, device in devices.items():
        labels = canonical_device_labels(device)
        labels.update(device_identity_macs.get(device_id, set()))
        device_labels[device_id] = labels
        for label in labels:
            label_to_devices[label].add(device_id)

    unique_labels = {
        label: next(iter(device_ids))
        for label, device_ids in label_to_devices.items()
        if len(device_ids) == 1
    }
    return unique_labels, device_labels


def build_unique_mac_port_index(ports: dict[str, NormalizedPort]) -> dict[str, NormalizedPort]:
    mac_to_ports: dict[str, list[NormalizedPort]] = defaultdict(list)
    for port in ports.values():
        if not port.mac:
            continue
        mac_to_ports[port.mac].append(port)

    return {
        mac: candidates[0]
        for mac, candidates in mac_to_ports.items()
        if len(candidates) == 1
    }


def is_l2_candidate_port(port: NormalizedPort) -> bool:
    identity = " ".join([port.ifname, port.ifalias, port.ifdescr]).lower()
    excluded_tokens = ("vlan-interface", "vlanif", "loopback", "inloopback", "null0")
    excluded_prefixes = ("vlan",)
    names = [part.strip().lower() for part in [port.ifname, port.ifalias, port.ifdescr] if part.strip()]
    if any(name.startswith(excluded_prefixes) for name in names):
        return False
    return not any(token in identity for token in excluded_tokens)


def winner_priority(item: dict[str, Any]) -> tuple[int, int]:
    relationship_type = str(item.get("relationship_type", ""))
    evidence_source = str(item.get("evidence_source", "") or "")
    if relationship_type == "authoritative":
        priority = 3
    elif evidence_source == "fdb+arp":
        priority = 2
    else:
        priority = 1
    return (priority, int(item.get("confidence", 0) or 0))


def normalize_interface_name(value: str) -> str:
    return "".join(str(value or "").strip().lower().split())


def build_interface_name_candidates(value: str) -> set[str]:
    normalized = normalize_interface_name(value)
    if not normalized:
        return set()

    candidates = {normalized}
    replacements = (
        ("gigabitethernet", "gi"),
        ("tengigabitethernet", "te"),
        ("ten-gigabitethernet", "te"),
        ("ethernet", "eth"),
        ("port-channel", "po"),
    )
    for full, short in replacements:
        if normalized.startswith(full):
            candidates.add(short + normalized[len(full):])
        if normalized.startswith(short):
            candidates.add(full + normalized[len(short):])
    return candidates


def build_port_match_candidates(port: NormalizedPort) -> set[str]:
    candidates: set[str] = set()
    for value in (port.ifname, port.ifdescr, port.ifalias):
        candidates.update(build_interface_name_candidates(value))
    for value in (port.ifindex, port.mac):
        normalized = normalize_interface_name(value)
        if normalized:
            candidates.add(normalized)
    return candidates


def build_device_identity_mac_sets(ports: dict[str, NormalizedPort]) -> dict[str, set[str]]:
    macs_by_device: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for port in ports.values():
        if not port.mac or not is_l2_candidate_port(port):
            continue
        macs_by_device[port.device_id][port.mac].add(port.port_id)

    return {
        device_id: {mac for mac, port_ids in mac_map.items() if len(port_ids) == 1}
        for device_id, mac_map in macs_by_device.items()
    }


def build_globally_unique_device_mac_sets(ports: dict[str, NormalizedPort]) -> dict[str, set[str]]:
    mac_owners: dict[str, set[str]] = defaultdict(set)
    per_device_macs: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for port in ports.values():
        if not port.mac or not is_l2_candidate_port(port):
            continue
        per_device_macs[port.device_id][port.mac].add(port.port_id)
        mac_owners[port.mac].add(port.device_id)

    return {
        device_id: {
            mac
            for mac, port_ids in mac_map.items()
            if len(port_ids) == 1 and len(mac_owners.get(mac, set())) == 1
        }
        for device_id, mac_map in per_device_macs.items()
    }


def build_globally_unique_non_l2_device_mac_sets(ports: dict[str, NormalizedPort]) -> dict[str, set[str]]:
    mac_owners: dict[str, set[str]] = defaultdict(set)
    per_device_macs: dict[str, set[str]] = defaultdict(set)
    for port in ports.values():
        if not port.mac or is_l2_candidate_port(port):
            continue
        per_device_macs[port.device_id].add(port.mac)
        mac_owners[port.mac].add(port.device_id)

    return {
        device_id: {mac for mac in macs if len(mac_owners.get(mac, set())) == 1}
        for device_id, macs in per_device_macs.items()
    }


def build_observed_device_mac_sets(ports: dict[str, NormalizedPort]) -> dict[str, set[str]]:
    observed: dict[str, set[str]] = defaultdict(set)
    for port in ports.values():
        if not port.mac or not is_l2_candidate_port(port):
            continue
        observed[port.device_id].add(port.mac)
    return observed


def build_stable_shared_device_mac_sets(normalized: dict[str, Any], ports: dict[str, NormalizedPort]) -> dict[str, set[str]]:
    mac_owners: dict[str, set[str]] = defaultdict(set)
    source_port_mac_counts: dict[tuple[str, str, str], int] = defaultdict(int)

    for port in ports.values():
        if not port.mac or not is_l2_candidate_port(port):
            continue
        mac_owners[port.mac].add(port.device_id)

    for entry in normalized.get("fdb_observations", []):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status", "")) not in {"3", "learned", "learned(3)"}:
            continue
        local_port_id = str(entry.get("local_port_id", "") or "")
        mac = str(entry.get("mac", "") or "")
        port = ports.get(local_port_id)
        if not local_port_id or not mac or port is None or not is_l2_candidate_port(port):
            continue
        owner_devices = mac_owners.get(mac, set())
        if len(owner_devices) != 1:
            continue
        owner_device = next(iter(owner_devices))
        if owner_device == port.device_id:
            continue
        source_port_mac_counts[(port.device_id, local_port_id, mac)] += 1

    stable: dict[str, set[str]] = defaultdict(set)
    for (source_device_id, _local_port_id, mac), count in source_port_mac_counts.items():
        if count < 2:
            continue
        owner_device = next(iter(mac_owners.get(mac, set())), "")
        if owner_device and owner_device != source_device_id:
            stable[owner_device].add(mac)
    return stable


def infer_fdb_confidence(vlan: str) -> tuple[int, list[str]]:
    normalized_vlan = str(vlan or "").strip()
    if normalized_vlan:
        return 75, [f"vlan:{normalized_vlan}", "vlan_scoped_match"]
    return 60, ["vlan_scope_missing", "mac_only_fallback"]


def resolve_local_neighbor_port_id(
    device_id: str,
    local_port_num: str,
    lldp_local_fields: dict[str, str],
    bridge_port_map: dict[str, dict[str, str]],
    ports: dict[str, NormalizedPort],
    protocol: str = "lldp",
) -> tuple[str, str]:
    direct_port_id = f"{device_id}:{local_port_num}"

    local_port_raw = lldp_local_fields.get("LLDP-LocPortId", "")
    local_port_subtype = lldp_local_fields.get("LLDP-LocPortIdSubtype", "")
    local_port_desc = lldp_local_fields.get("LLDP-LocPortDesc", "")
    decoded_local_port, _ = decode_lldp_port_id(local_port_subtype, local_port_raw)
    has_local_name_evidence = bool(decoded_local_port or local_port_desc)

    def matches_local_fields(port: NormalizedPort) -> bool:
        if decoded_local_port and decoded_local_port in {port.ifname, port.ifalias, port.ifdescr, port.ifindex, port.mac}:
            return True
        if local_port_desc and local_port_desc in {port.ifname, port.ifalias, port.ifdescr}:
            return True
        return False

    def find_by_local_fields() -> str | None:
        if not has_local_name_evidence:
            return None
        for port in ports.values():
            if port.device_id == device_id and matches_local_fields(port):
                return port.port_id
        return None

    # CDP/FDP 的索引第一段就是 ifIndex，不存在 basePort 语义，禁止查 bridge 映射。
    if protocol in {"cdp", "fdp"}:
        if direct_port_id in ports:
            return direct_port_id, "resolved"
        matched = find_by_local_fields()
        if matched:
            return matched, "resolved"
        return direct_port_id, "unresolved_local_port"

    bridge_mapped_ifindex = bridge_port_map.get(device_id, {}).get(local_port_num)
    bridge_port_id = f"{device_id}:{bridge_mapped_ifindex}" if bridge_mapped_ifindex else ""

    # bridge 命中后用 LLDP 本地端口名交叉校验；无名称证据时维持原有 bridge 优先行为。
    if bridge_port_id and bridge_port_id in ports:
        if not has_local_name_evidence or matches_local_fields(ports[bridge_port_id]):
            return bridge_port_id, "resolved"

    if direct_port_id in ports:
        if not has_local_name_evidence or matches_local_fields(ports[direct_port_id]):
            return direct_port_id, "resolved"

    matched = find_by_local_fields()
    if matched:
        return matched, "resolved"

    # 名称证据与所有候选都不一致：退回原优先级，避免把可解析端口判为 unresolved。
    if bridge_port_id and bridge_port_id in ports:
        return bridge_port_id, "resolved"
    if direct_port_id in ports:
        return direct_port_id, "resolved"

    return direct_port_id, "unresolved_local_port"


def make_interface_inst_name(device_id: str, port: NormalizedPort | None) -> str:
    if port is None:
        return f"{device_id}-unknown"
    return f"{device_id}-{port.display_name}"


def _iter_device_items(aggregate: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items = []
    errors = []
    for item in aggregate.get("devices", []):
        if not isinstance(item, dict):
            continue
        device_info = item.get("device", {})
        device_id = str(device_info.get("host", "")).strip() or "unknown"
        collector_result = item.get("collector_result", {})
        success = bool(item.get("success", False))
        if not success:
            errors.append(
                {
                    "device_id": device_id,
                    "error": collector_result.get("result", {}).get("cmdb_collect_error") or item.get("error"),
                }
            )
            continue
        result = collector_result.get("result", {})
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            legacy_records = result.get("network_topo", [])
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for entry in legacy_records if isinstance(legacy_records, list) else []:
                if not isinstance(entry, dict):
                    continue
                tag = str(entry.get("tag", ""))
                if tag.startswith("ARP-"):
                    grouped["arp"].append(entry)
                elif tag.startswith("IF"):
                    grouped["interfaces"].append(entry)
                elif tag.startswith("IpAddr-"):
                    grouped["ip"].append(entry)
                elif tag.startswith("System-"):
                    grouped["system"].append(entry)
            evidence = dict(grouped)
        items.append({"device": device_info, "device_id": device_id, "evidence": evidence, "raw_result": result})
    return items, errors


def normalize_topology_data(aggregate: dict[str, Any]) -> dict[str, Any]:
    items, errors = _iter_device_items(aggregate)
    devices: dict[str, NormalizedDevice] = {}
    ports: dict[str, NormalizedPort] = {}
    neighbors: list[NeighborObservation] = []
    arp_observations: list[ArpObservation] = []
    fdb_observations: list[FdbObservation] = []
    bridge_port_map: dict[str, dict[str, str]] = defaultdict(dict)

    for item in items:
        device_id = item["device_id"]
        evidence = item.get("evidence", {}) or {}
        system_records = evidence.get("system", [])
        device = NormalizedDevice(device_id=device_id, host=device_id)
        if isinstance(system_records, list):
            for entry in system_records:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("tag", "")) == "System-SysName":
                    device.sys_name = str(entry.get("val", "") or "")
        devices[device_id] = device

        interface_details: dict[str, dict[str, str]] = defaultdict(dict)
        raw_interface_records: list[dict[str, Any]] = []
        for group_name in ("interfaces", "ip"):
            group_records = evidence.get(group_name, [])
            if isinstance(group_records, list):
                raw_interface_records.extend(entry for entry in group_records if isinstance(entry, dict))

        for entry in raw_interface_records:
            tag = str(entry.get("tag", ""))
            index = str(entry.get("ifindex", "") or "")
            value = str(entry.get("val", "") or "")
            if tag == "IFTable-IfDescr":
                interface_details[index]["ifdescr"] = value
            elif tag == "IFTable-IfAlias":
                interface_details[index]["ifalias"] = value
            elif tag == "IFXTable-IfName":
                interface_details[index]["ifname"] = value
            elif tag == "IFTable-PhysAddress":
                interface_details[index]["mac"] = normalize_mac(value)
            elif tag == "IpAddr-IpAddr" and value:
                device.ips.append(decode_ipv4ish(value))

        for ifindex, details in interface_details.items():
            port_id = f"{device_id}:{ifindex}"
            ports[port_id] = NormalizedPort(
                device_id=device_id,
                port_id=port_id,
                ifindex=ifindex,
                ifname=details.get("ifname", ""),
                ifalias=details.get("ifalias", ""),
                ifdescr=details.get("ifdescr", ""),
                mac=details.get("mac", ""),
            )

        arp_records = evidence.get("arp", [])
        if isinstance(arp_records, list):
            arp_rows: dict[str, dict[str, str]] = defaultdict(dict)
            for entry in arp_records:
                if not isinstance(entry, dict):
                    continue
                tag = str(entry.get("tag", ""))
                index = str(entry.get("ifindex", "") or "")
                value = str(entry.get("val", "") or "")
                if tag == "ARP-IfIndex":
                    arp_rows[index]["ifindex"] = value
                elif tag == "ARP-PhysAddress":
                    arp_rows[index]["mac"] = normalize_mac(value)

            for ip_address, row in arp_rows.items():
                ifindex = row.get("ifindex", "")
                port_id = f"{device_id}:{ifindex}"
                arp_observations.append(
                    ArpObservation(
                        source_device_id=device_id,
                        local_port_id=port_id,
                        ip_address=decode_ipv4ish(ip_address),
                        mac=row.get("mac", ""),
                        evidence_key=f"{device_id}:arp:{ip_address}",
                    )
                )

        bridge_records = evidence.get("bridge", [])
        if isinstance(bridge_records, list):
            for entry in bridge_records:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("tag", "")) == "BRIDGE-BasePortIfIndex":
                    bridge_port_map[device_id][str(entry.get("ifindex", "") or "")] = str(entry.get("val", "") or "")

        fdb_records = evidence.get("fdb", [])
        if isinstance(fdb_records, list):
            fdb_rows: dict[str, dict[str, str]] = defaultdict(dict)
            for entry in fdb_records:
                if not isinstance(entry, dict):
                    continue
                suffix = str(entry.get("ifindex", "") or "")
                tag = str(entry.get("tag", ""))
                value = str(entry.get("val", "") or "")
                if tag in {"FDB-Port", "QBRIDGE-FdbPort"}:
                    fdb_rows[suffix]["bridge_port"] = value
                    suffix_parts = suffix.split(".")
                    mac_suffix = ".".join(suffix_parts[-6:]) if len(suffix_parts) >= 6 else suffix
                    fdb_rows[suffix]["mac"] = normalize_mac_from_oid_suffix(mac_suffix)
                    if tag == "QBRIDGE-FdbPort":
                        if len(suffix_parts) > 6:
                            # dot1qTpFdbTable 索引首段是 dot1qFdbId，多数设备等于 VLAN ID，
                            # 但协议不保证；仅用于 VLAN 标注与 per-VLAN 去重粒度，可接受。
                            fdb_rows[suffix]["vlan"] = suffix_parts[0]
                elif tag in {"FDB-Status", "QBRIDGE-FdbStatus"}:
                    fdb_rows[suffix]["status"] = value

            for suffix, row in fdb_rows.items():
                bridge_port = row.get("bridge_port", "")
                if bridge_port == "0":
                    continue
                ifindex = bridge_port_map.get(device_id, {}).get(bridge_port)
                if not ifindex:
                    continue
                fdb_observations.append(
                    FdbObservation(
                        source_device_id=device_id,
                        local_port_id=f"{device_id}:{ifindex}",
                        mac=row.get("mac", ""),
                        evidence_key=f"{device_id}:fdb:{suffix}",
                        status=row.get("status", ""),
                        vlan=row.get("vlan", ""),
                    )
                )

        neighbor_records = evidence.get("neighbors", [])
        if isinstance(neighbor_records, list):
            grouped_neighbors: dict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
            lldp_local_ports: dict[str, dict[str, str]] = defaultdict(dict)
            for entry in neighbor_records:
                if not isinstance(entry, dict):
                    continue
                tag = str(entry.get("tag", ""))
                suffix = str(entry.get("ifindex", "") or "")
                if tag.startswith("LLDP-Loc"):
                    lldp_local_ports[suffix][tag] = str(entry.get("val", "") or "")
                    continue
                if tag.startswith("LLDP-"):
                    protocol = "lldp"
                elif tag.startswith("FDP-"):
                    protocol = "fdp"
                else:
                    protocol = "cdp"
                grouped_neighbors[(protocol, suffix)][tag] = str(entry.get("val", "") or "")
                grouped_neighbors[(protocol, suffix)]["suffix"] = suffix

            for (protocol, suffix), values in grouped_neighbors.items():
                suffix_parts = suffix.split(".") if suffix else []
                local_port_num = ""
                if protocol == "lldp":
                    if len(suffix_parts) >= 2:
                        local_port_num = suffix_parts[-2]
                    elif suffix_parts:
                        local_port_num = suffix_parts[0]
                else:
                    local_port_num = suffix_parts[0] if suffix_parts else ""

                local_fields = lldp_local_ports.get(local_port_num, {}) if protocol == "lldp" else {}
                candidate_port_id, resolution_state = resolve_local_neighbor_port_id(
                    device_id=device_id,
                    local_port_num=local_port_num,
                    lldp_local_fields=local_fields,
                    bridge_port_map=bridge_port_map,
                    ports=ports,
                    protocol=protocol,
                )

                remote_address = decode_cdp_address(values.get("CDP-AddressType", ""), values.get("CDP-Address", ""))
                raw_remote_port = (
                    values.get("LLDP-RemPortId", "")
                    or values.get("CDP-DevicePort", "")
                    or values.get("FDP-DevicePort", "")
                )
                remote_port_subtype = values.get("LLDP-RemPortIdSubtype", "") or ("5" if values.get("FDP-DevicePort", "") else "")
                decoded_remote_port, _ = decode_lldp_port_id(remote_port_subtype, raw_remote_port)
                remote_chassis_id = (
                    decode_lldp_chassis_id(values.get("LLDP-RemChassisIdSubtype", ""), values.get("LLDP-RemChassisId", ""))
                    or values.get("CDP-DeviceId", "")
                    or values.get("FDP-DeviceId", "")
                )

                observation = NeighborObservation(
                    source_device_id=device_id,
                    local_port_id=candidate_port_id,
                    local_port_num=local_port_num,
                    protocol=protocol,
                    evidence_key=f"{device_id}:{protocol}:{suffix}",
                    remote_system_name=(
                        values.get("LLDP-RemSysName", "")
                        or values.get("CDP-SysName", "")
                        or values.get("CDP-DeviceId", "")
                        or values.get("FDP-DeviceId", "")
                    ),
                    remote_chassis_id=remote_chassis_id,
                    remote_port_id=decoded_remote_port,
                    remote_port_subtype=remote_port_subtype,
                    remote_port_value=raw_remote_port,
                    remote_port_desc=values.get("LLDP-RemPortDesc", ""),
                    remote_address=remote_address,
                    resolution_state=resolution_state,
                    raw_remote_fields={
                        **lldp_local_ports.get(local_port_num, {}),
                        **values,
                    },
                )
                neighbors.append(observation)

    return {
        "devices": [device.to_dict() for device in devices.values()],
        "ports": [port.to_dict() for port in ports.values()],
        "neighbor_observations": [item.to_dict() for item in neighbors],
        "arp_observations": [item.to_dict() for item in arp_observations],
        "fdb_observations": [item.to_dict() for item in fdb_observations],
        "errors": errors,
    }


def _index_ports(normalized: dict[str, Any]) -> dict[str, NormalizedPort]:
    ports: dict[str, NormalizedPort] = {}
    for item in normalized.get("ports", []):
        if not isinstance(item, dict):
            continue
        port = NormalizedPort(
            device_id=str(item.get("device_id", "")),
            port_id=str(item.get("port_id", "")),
            ifindex=str(item.get("ifindex", "")),
            ifname=str(item.get("ifname", "")),
            ifalias=str(item.get("ifalias", "")),
            ifdescr=str(item.get("ifdescr", "")),
            mac=str(item.get("mac", "")),
        )
        ports[port.port_id] = port
    return ports


def _index_devices(normalized: dict[str, Any]) -> dict[str, dict[str, Any]]:
    devices: dict[str, dict[str, Any]] = {}
    for item in normalized.get("devices", []):
        if not isinstance(item, dict):
            continue
        devices[str(item.get("device_id", ""))] = item
    return devices


def infer_topology(normalized: dict[str, Any]) -> dict[str, Any]:
    ports = _index_ports(normalized)
    devices = _index_devices(normalized)
    mac_to_port = build_unique_mac_port_index({port_id: port for port_id, port in ports.items() if is_l2_candidate_port(port)})
    unique_device_labels, device_labels = build_device_label_indexes(devices, ports)
    mac_to_devices: dict[str, set[str]] = defaultdict(set)
    for port in ports.values():
        if not port.mac or not is_l2_candidate_port(port):
            continue
        mac_to_devices[port.mac].add(port.device_id)

    authoritative: list[LinkCandidate] = []
    inferred: list[LinkCandidate] = []
    unresolved: list[dict[str, Any]] = []

    for entry in normalized.get("neighbor_observations", []):
        if not isinstance(entry, dict):
            continue
        source_port = ports.get(str(entry.get("local_port_id", "")))
        if source_port is None:
            unresolved.append(
                build_unresolved_neighbor_entry(
                    observation=entry,
                    source_port=None,
                    resolution_state="unresolved_local_port",
                    decision_reason="Could not map the local neighbor port to a normalized interface.",
                    confidence=20,
                    supporting_signals=[str(entry.get("protocol", "neighbor")), "local_port_missing"],
                )
            )
            continue
        remote_system_name = str(entry.get("remote_system_name", "") or "")
        remote_chassis_id = str(entry.get("remote_chassis_id", "") or "")
        remote_name = remote_system_name or remote_chassis_id
        remote_port_id = str(entry.get("remote_port_id", ""))
        remote_port_value = str(entry.get("remote_port_value", ""))
        remote_port_desc = str(entry.get("remote_port_desc", ""))
        remote_candidates = set()
        remote_candidates.update(build_interface_name_candidates(remote_port_id))
        remote_candidates.update(build_interface_name_candidates(remote_port_value))
        remote_candidates.update(build_interface_name_candidates(remote_port_desc))
        target_device = (
            unique_device_labels.get(str(entry.get("remote_address", "")))
            or unique_device_labels.get(remote_chassis_id)
            or unique_device_labels.get(remote_system_name)
        )
        if target_device is None and str(entry.get("protocol", "")) == "lldp" and remote_candidates:
            candidate_devices = {
                port.device_id
                for port in ports.values()
                if remote_candidates & build_port_match_candidates(port)
            }
            chassis_devices = mac_to_devices.get(remote_chassis_id, set()) if remote_chassis_id else set()
            if len(candidate_devices) == 1 and len(chassis_devices) == 1 and candidate_devices == chassis_devices:
                target_device = next(iter(candidate_devices))
        target_port = None
        if target_device and remote_port_id:
            target_port = next(
                (
                    port
                    for port in ports.values()
                    if port.device_id == target_device
                    and (
                        remote_candidates & build_port_match_candidates(port)
                    )
                ),
                None,
            )

        if target_device is None:
            identifier_quality = get_neighbor_identifier_quality(
                str(entry.get("protocol", "")),
                str(entry.get("remote_port_subtype", "")),
                str(entry.get("remote_port_value", "")),
            )
            unresolved.append(
                build_unresolved_neighbor_entry(
                    observation=entry,
                    source_port=source_port,
                    resolution_state="unresolved_remote",
                    decision_reason="Resolved the local port but could not match the remote device.",
                    confidence=40 + identifier_quality,
                    supporting_signals=[
                        str(entry.get("protocol", "neighbor")),
                        "local_port_resolved",
                        f"remote_port_subtype:{entry.get('remote_port_subtype', '') or 'unknown'}",
                    ],
                )
            )
            continue

        if target_port is None:
            unresolved.append(
                build_unresolved_neighbor_entry(
                    observation=entry,
                    source_port=source_port,
                    resolution_state="resolved_device_only",
                    decision_reason="Matched the remote device but could not resolve the remote interface.",
                    confidence=60
                    + get_neighbor_identifier_quality(
                        str(entry.get("protocol", "")),
                        str(entry.get("remote_port_subtype", "")),
                        str(entry.get("remote_port_value", "")),
                    ),
                    supporting_signals=[
                        str(entry.get("protocol", "neighbor")),
                        "local_port_resolved",
                        "remote_device_resolved",
                        f"remote_port_subtype:{entry.get('remote_port_subtype', '') or 'unknown'}",
                    ],
                )
            )
            continue

        confidence = min(
            100,
            80
            + get_neighbor_identifier_quality(
                str(entry.get("protocol", "")),
                str(entry.get("remote_port_subtype", "")),
                str(entry.get("remote_port_value", "")),
            )
            + 10,
        )

        relationship_id = f"auth:{source_port.port_id}:{entry.get('protocol', '')}:{entry.get('remote_port_id', '')}"
        authoritative.append(
            LinkCandidate(
                relationship_id=relationship_id,
                relationship_type="authoritative",
                evidence_source=str(entry.get("protocol", "lldp")),
                confidence=confidence,
                source_device=source_port.device_id,
                source_port_id=source_port.port_id,
                source_inst_name=make_interface_inst_name(source_port.device_id, source_port),
                target_device=target_device,
                target_port_id=target_port.port_id if target_port else None,
                target_inst_name=make_interface_inst_name(target_device or remote_name or "unknown", target_port)
                if (target_device or target_port)
                else None,
                remote_device_name=remote_name or None,
                remote_port_name=str(entry.get("remote_port_id", "")) or None,
                provenance=[
                    {
                        "type": "neighbor",
                        "evidence_key": entry.get("evidence_key"),
                        "protocol": entry.get("protocol"),
                        "remote_port_subtype": entry.get("remote_port_subtype"),
                        "remote_port_value": entry.get("remote_port_value"),
                        "remote_address": entry.get("remote_address"),
                        "resolution_state": entry.get("resolution_state"),
                    }
                ],
            )
        )

    for entry in normalized.get("arp_observations", []):
        if not isinstance(entry, dict):
            continue
        source_port = ports.get(str(entry.get("local_port_id", "")))
        target_port = mac_to_port.get(str(entry.get("mac", "")))
        if (
            source_port is None
            or not is_l2_candidate_port(source_port)
            or target_port is None
            or target_port.device_id == source_port.device_id
        ):
            continue
        relationship_id = f"inf:{source_port.port_id}:{target_port.port_id}:arp"
        inferred.append(
            LinkCandidate(
                relationship_id=relationship_id,
                relationship_type="inferred",
                evidence_source="arp",
                confidence=50,
                source_device=source_port.device_id,
                source_port_id=source_port.port_id,
                source_inst_name=make_interface_inst_name(source_port.device_id, source_port),
                target_device=target_port.device_id,
                target_port_id=target_port.port_id,
                target_inst_name=make_interface_inst_name(target_port.device_id, target_port),
                remote_device_name=target_port.device_id,
                remote_port_name=target_port.display_name,
                provenance=[{"type": "arp", "evidence_key": entry.get("evidence_key"), "mac": entry.get("mac"), "ip": entry.get("ip_address")}],
            )
        )

    for entry in normalized.get("fdb_observations", []):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status", "")) not in {"3", "learned", "learned(3)"}:
            continue
        source_port = ports.get(str(entry.get("local_port_id", "")))
        target_port = mac_to_port.get(str(entry.get("mac", "")))
        if source_port is None or target_port is None or target_port.device_id == source_port.device_id:
            continue
        vlan = str(entry.get("vlan", "") or "")
        confidence, vlan_signals = infer_fdb_confidence(vlan)
        vlan_suffix = vlan or "none"
        relationship_id = f"inf:{source_port.port_id}:{target_port.port_id}:fdb:{vlan_suffix}"
        inferred.append(
            LinkCandidate(
                relationship_id=relationship_id,
                relationship_type="inferred",
                evidence_source="fdb",
                confidence=confidence,
                source_device=source_port.device_id,
                source_port_id=source_port.port_id,
                source_inst_name=make_interface_inst_name(source_port.device_id, source_port),
                target_device=target_port.device_id,
                target_port_id=target_port.port_id,
                target_inst_name=make_interface_inst_name(target_port.device_id, target_port),
                remote_device_name=target_port.device_id,
                remote_port_name=target_port.display_name,
                vlan=vlan or None,
                provenance=[
                    {
                        "type": "fdb",
                        "evidence_key": entry.get("evidence_key"),
                        "mac": entry.get("mac"),
                        "status": entry.get("status"),
                        "vlan": entry.get("vlan"),
                        "signals": vlan_signals,
                    }
                ],
            )
        )

    return {
        "authoritative_links": [candidate.to_dict() for candidate in authoritative],
        "inferred_links": [candidate.to_dict() for candidate in inferred],
        "unresolved_neighbors": unresolved,
        "device_labels": {device_id: sorted(labels) for device_id, labels in device_labels.items()},
    }


def _canonical_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def _relationship_identity(item: dict[str, Any]) -> tuple[str, str]:
    source_port = str(item.get("source_port_id", "") or "")
    target_port = str(item.get("target_port_id", "") or "")
    if source_port and target_port:
        return _canonical_pair(source_port, target_port)

    identity_left = f"{source_port}|{item.get('source_device', '')}"
    identity_right = f"{item.get('remote_device_name', '')}|{item.get('remote_port_name', '')}"
    return _canonical_pair(identity_left, identity_right)


def _relationship_identity_with_vlan(item: dict[str, Any]) -> tuple[tuple[str, str], str]:
    return _relationship_identity(item), str(item.get("vlan", "") or "")


def _snapshot_identity(item: dict[str, Any]) -> tuple[tuple[str, str], str]:
    relationship_type = str(item.get("relationship_type", ""))
    if relationship_type == "inferred" and str(item.get("evidence_source", "")) == "fdb":
        return _relationship_identity(item), str(item.get("vlan", "") or "")
    return _relationship_identity(item), ""


def sort_vlan_values(vlans: set[str]) -> list[str]:
    def vlan_sort_key(value: str) -> tuple[int, int | str]:
        if value.isdigit():
            return (0, int(value))
        return (1, value)

    return sorted(vlans, key=vlan_sort_key)


def build_multi_vlan_corroboration_summary(
    current_links: list[dict[str, Any]],
    unresolved_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    conflict_counts: dict[str, int] = defaultdict(int)
    for unresolved in unresolved_candidates:
        if not isinstance(unresolved, dict):
            continue
        relationship_id = str(unresolved.get("conflicts_with_relationship_id", "") or "")
        if relationship_id:
            conflict_counts[relationship_id] += 1

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for link in current_links:
        if not isinstance(link, dict):
            continue
        pair_key = _relationship_identity(link)
        group = grouped.setdefault(
            pair_key,
            {
                "anchors": {},
                "fdb_entries": [],
            },
        )
        relationship_id = str(link.get("relationship_id", "") or "")
        if relationship_id:
            group["anchors"][relationship_id] = link

        if str(link.get("evidence_source", "")) == "fdb" and str(link.get("vlan", "") or ""):
            group["fdb_entries"].append(
                {
                    "relationship_id": relationship_id,
                    "vlan": str(link.get("vlan", "") or ""),
                    "source": "current",
                }
            )

        for supporting in link.get("supporting_evidence", []):
            if not isinstance(supporting, dict):
                continue
            if str(supporting.get("evidence_source", "")) != "fdb":
                continue
            vlan = str(supporting.get("vlan", "") or "")
            if not vlan:
                continue
            group["fdb_entries"].append(
                {
                    "relationship_id": str(supporting.get("relationship_id", "") or ""),
                    "vlan": vlan,
                    "source": str(supporting.get("disposition", "supporting") or "supporting"),
                }
            )

    summaries: list[dict[str, Any]] = []
    for pair_key, payload in grouped.items():
        fdb_entries = payload["fdb_entries"]
        vlan_ids = {str(entry.get("vlan", "") or "") for entry in fdb_entries if str(entry.get("vlan", "") or "")}
        if len(vlan_ids) < 2:
            continue
        unique_evidence_keys = {
            (
                str(entry.get("relationship_id", "") or ""),
                str(entry.get("vlan", "") or ""),
            )
            for entry in fdb_entries
            if str(entry.get("vlan", "") or "")
        }

        anchors = list(payload["anchors"].values())
        if not anchors:
            continue
        anchor = max(anchors, key=winner_priority)
        anchor_relationship_id = str(anchor.get("relationship_id", "") or "")
        summaries.append(
            {
                "corroboration_scope": "multi_vlan",
                "anchor_relationship_id": anchor_relationship_id,
                "relationship_type": anchor.get("relationship_type"),
                "source_device": anchor.get("source_device"),
                "source_port_id": anchor.get("source_port_id"),
                "target_device": anchor.get("target_device") or anchor.get("remote_device_name"),
                "target_port_id": anchor.get("target_port_id"),
                "vlan_ids": sort_vlan_values(vlan_ids),
                "evidence_count": len(unique_evidence_keys),
                "fdb_relationship_ids": sorted(
                    {str(entry.get("relationship_id", "") or "") for entry in fdb_entries if str(entry.get("relationship_id", "") or "")}
                ),
                "conflicting_observation_count": conflict_counts.get(anchor_relationship_id, 0),
                "explanation": (
                    f"Observed across VLANs {', '.join(sort_vlan_values(vlan_ids))}; "
                    "this pattern likely corroborates one shared trunk/uplink relationship."
                ),
            }
        )

    return summaries


def build_device_mac_correlations(
    normalized: dict[str, Any],
    ports: dict[str, NormalizedPort],
    devices: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    device_labels = {
        device_id: canonical_device_labels(device)
        for device_id, device in devices.items()
    }
    device_mac_sets = build_globally_unique_device_mac_sets(ports)
    non_l2_device_mac_sets = build_globally_unique_non_l2_device_mac_sets(ports)
    observed_device_mac_sets = build_observed_device_mac_sets(ports)
    stable_shared_device_mac_sets = build_stable_shared_device_mac_sets(normalized, ports)
    correlation_device_mac_sets = {
        device_id: set(device_mac_sets.get(device_id, set()))
        | set(non_l2_device_mac_sets.get(device_id, set()))
        | set(stable_shared_device_mac_sets.get(device_id, set()))
        for device_id in devices.keys()
    }

    arp_by_device_ip: dict[tuple[str, str], set[str]] = defaultdict(set)
    for entry in normalized.get("arp_observations", []):
        if not isinstance(entry, dict):
            continue
        source_device = str(entry.get("source_device_id", "") or "")
        ip_address = str(entry.get("ip_address", "") or "")
        mac = str(entry.get("mac", "") or "")
        if source_device and ip_address and mac:
            arp_by_device_ip[(source_device, ip_address)].add(mac)

    fdb_hits: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    port_seen_devices: dict[str, set[str]] = defaultdict(set)
    for entry in normalized.get("fdb_observations", []):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status", "")) not in {"3", "learned", "learned(3)"}:
            continue
        source_device = str(entry.get("source_device_id", "") or "")
        local_port_id = str(entry.get("local_port_id", "") or "")
        mac = str(entry.get("mac", "") or "")
        if not source_device or not local_port_id or not mac:
            continue
        local_port = ports.get(local_port_id)
        if local_port is None or not is_l2_candidate_port(local_port):
            continue
        for target_device, macs in observed_device_mac_sets.items():
            if target_device == source_device or mac not in macs:
                continue
            port_seen_devices[local_port_id].add(target_device)
        for target_device, macs in correlation_device_mac_sets.items():
            if target_device == source_device or mac not in macs:
                continue
            fdb_hits[(source_device, target_device)].append(
                {
                    "local_port_id": local_port_id,
                    "mac": mac,
                    "vlan": str(entry.get("vlan", "") or ""),
                    "evidence_key": str(entry.get("evidence_key", "") or ""),
                }
            )

    correlations: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for (left_device, right_device), left_hits in fdb_hits.items():
        pair_key = _canonical_pair(left_device, right_device)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        right_hits = fdb_hits.get((right_device, left_device), [])
        left_ports = {hit["local_port_id"] for hit in left_hits}
        right_ports = {hit["local_port_id"] for hit in right_hits}
        if len(left_ports) != 1 or len(right_ports) != 1:
            continue

        left_port_id = next(iter(left_ports))
        right_port_id = next(iter(right_ports))
        if len(port_seen_devices.get(left_port_id, set())) > 1 and len(port_seen_devices.get(right_port_id, set())) > 1:
            continue
        shared_third_party_devices = (
            port_seen_devices.get(left_port_id, set()) & port_seen_devices.get(right_port_id, set())
        ) - {left_device, right_device}
        if shared_third_party_devices:
            continue
        left_port = ports.get(left_port_id)
        right_port = ports.get(right_port_id)
        if left_port is None or right_port is None:
            continue

        left_device_ips = {label for label in device_labels.get(left_device, set()) if "." in label}
        right_device_ips = {label for label in device_labels.get(right_device, set()) if "." in label}
        left_arp_macs = set().union(*(arp_by_device_ip.get((left_device, ip), set()) for ip in right_device_ips)) if right_device_ips else set()
        right_arp_macs = set().union(*(arp_by_device_ip.get((right_device, ip), set()) for ip in left_device_ips)) if left_device_ips else set()

        right_candidate_macs = correlation_device_mac_sets.get(right_device, set())
        left_candidate_macs = correlation_device_mac_sets.get(left_device, set())
        left_seen_right = bool(left_arp_macs & right_candidate_macs)
        right_seen_left = bool(right_arp_macs & left_candidate_macs)
        if not (left_seen_right and right_seen_left):
            continue

        all_hits = left_hits + right_hits
        vlan_ids = {hit["vlan"] for hit in all_hits if hit["vlan"]}
        correlations.append(
            {
                "pair": (left_device, right_device),
                "left_port_id": left_port_id,
                "right_port_id": right_port_id,
                "left_port": left_port,
                "right_port": right_port,
                "left_hits": left_hits,
                "right_hits": right_hits,
                "vlan_ids": sort_vlan_values(vlan_ids),
            }
        )

    return correlations


def reconcile_topology(
    normalized: dict[str, Any],
    inferred: dict[str, Any],
    previous_links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    authoritative_candidates = list(inferred.get("authoritative_links", []))
    inferred_links = list(inferred.get("inferred_links", []))
    unresolved_candidates = list(inferred.get("unresolved_neighbors", []))
    device_labels = {
        str(device_id): set(labels)
        for device_id, labels in inferred.get("device_labels", {}).items()
        if isinstance(labels, list)
    }
    ports = _index_ports(normalized)
    devices = _index_devices(normalized)
    stale_links: list[dict[str, Any]] = []

    seen_authoritative: dict[tuple[str, str], dict[str, Any]] = {}
    for item in authoritative_candidates:
        key = _relationship_identity(item)
        existing = seen_authoritative.get(key)
        if existing is None:
            seen_authoritative[key] = item
            continue

        stale_item = dict(item)
        stale_item["status"] = "superseded"
        stale_item["reconciliation_role"] = "corroborating"
        append_supporting_evidence(existing, stale_item, disposition="corroborating")
        stale_links.append(stale_item)

    authoritative = list(seen_authoritative.values())
    authoritative_pairs = {_relationship_identity(item) for item in authoritative}

    deduped_inferred: dict[tuple[tuple[str, str], str], dict[str, Any]] = {}
    for item in inferred_links:
        source_port = str(item.get("source_port_id", ""))
        target_port = str(item.get("target_port_id", ""))
        if not source_port or not target_port:
            continue
        key = _relationship_identity(item)
        if key in authoritative_pairs:
            stale_item = dict(item)
            stale_item["status"] = "suppressed"
            stale_item["reconciliation_role"] = "corroborating"
            authoritative_winner = next((winner for winner in authoritative if _relationship_identity(winner) == key), None)
            if authoritative_winner is not None:
                append_supporting_evidence(authoritative_winner, stale_item, disposition="corroborating")
            stale_links.append(stale_item)
            continue
        scoped_key = _relationship_identity_with_vlan(item)
        existing = deduped_inferred.get(scoped_key)
        if existing is None or int(item.get("confidence", 0)) > int(existing.get("confidence", 0)):
            if existing is not None:
                stale_item = dict(existing)
                stale_item["status"] = "superseded"
                stale_item["reconciliation_role"] = "corroborating"
                append_supporting_evidence(item, stale_item, disposition="corroborating")
                stale_links.append(stale_item)
            deduped_inferred[scoped_key] = item
        else:
            stale_item = dict(item)
            stale_item["status"] = "superseded"
            stale_item["reconciliation_role"] = "corroborating"
            append_supporting_evidence(existing, stale_item, disposition="corroborating")
            stale_links.append(stale_item)

    for correlation in build_device_mac_correlations(normalized, ports, devices):
        left_device, right_device = correlation["pair"]
        left_port = correlation["left_port"]
        right_port = correlation["right_port"]
        bidirectional_id = f"inf-bidir:{left_port.port_id}:{right_port.port_id}"
        candidate = {
            "relationship_id": bidirectional_id,
            "relationship_type": "inferred",
            "evidence_source": "fdb+arp",
            "confidence": 95,
            "source_device": left_device,
            "source_port_id": left_port.port_id,
            "source_inst_name": make_interface_inst_name(left_device, left_port),
            "target_device": right_device,
            "target_port_id": right_port.port_id,
            "target_inst_name": make_interface_inst_name(right_device, right_port),
            "remote_device_name": right_device,
            "remote_port_name": right_port.display_name,
            "vlan": correlation["vlan_ids"][0] if len(correlation["vlan_ids"]) == 1 else None,
            "provenance": [
                {
                    "type": "bidirectional_mac_corroboration",
                    "left_fdb_hits": correlation["left_hits"],
                    "right_fdb_hits": correlation["right_hits"],
                    "vlan_ids": correlation["vlan_ids"],
                    "signals": ["bidirectional_fdb", "mutual_arp_visibility", "unique_port_pair"],
                }
            ],
            "supporting_evidence": [],
            "status": "current",
        }
        candidate_identity = _relationship_identity(candidate)
        if candidate_identity in authoritative_pairs:
            stale_item = dict(candidate)
            stale_item["status"] = "suppressed"
            stale_item["reconciliation_role"] = "corroborating"
            authoritative_winner = next((winner for winner in authoritative if _relationship_identity(winner) == candidate_identity), None)
            if authoritative_winner is not None:
                append_supporting_evidence(authoritative_winner, stale_item, disposition="corroborating")
            stale_links.append(stale_item)
            continue
        scoped_key = _relationship_identity_with_vlan(candidate)
        existing = deduped_inferred.get(scoped_key)
        generic_key = (_relationship_identity(candidate), "")
        generic_existing = deduped_inferred.get(generic_key)
        if generic_existing is not None and generic_existing is not existing:
            stale_item = dict(generic_existing)
            stale_item["status"] = "superseded"
            stale_item["reconciliation_role"] = "corroborating"
            append_supporting_evidence(candidate, stale_item, disposition="corroborating")
            stale_links.append(stale_item)
            deduped_inferred.pop(generic_key, None)
        if existing is None or winner_priority(candidate) > winner_priority(existing):
            if existing is not None:
                stale_item = dict(existing)
                stale_item["status"] = "superseded"
                stale_item["reconciliation_role"] = "corroborating"
                append_supporting_evidence(candidate, stale_item, disposition="corroborating")
                stale_links.append(stale_item)
            deduped_inferred[scoped_key] = candidate
        else:
            stale_item = dict(candidate)
            stale_item["status"] = "superseded"
            stale_item["reconciliation_role"] = "corroborating"
            append_supporting_evidence(existing, stale_item, disposition="corroborating")
            stale_links.append(stale_item)

    current_links = authoritative + list(deduped_inferred.values())
    current_by_source_port: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in current_links:
        source_port = str(item.get("source_port_id", ""))
        if source_port:
            current_by_source_port[source_port].append(item)

    for unresolved in unresolved_candidates:
        if not isinstance(unresolved, dict):
            continue
        source_port_id = str(unresolved.get("source_port_id", ""))
        candidates = current_by_source_port.get(source_port_id, [])
        if not candidates:
            continue
        winner = max(candidates, key=winner_priority)
        unresolved_remote = str(unresolved.get("remote_device_name", "") or "")
        unresolved_labels = {unresolved_remote} if unresolved_remote else set()
        winner_remote = str(winner.get("target_device") or winner.get("remote_device_name") or "")
        winner_labels = {winner_remote} if winner_remote else set()
        target_device = str(winner.get("target_device", "") or "")
        if target_device and target_device in device_labels:
            winner_labels.update(device_labels[target_device])
        if unresolved_remote and unresolved_remote not in winner_labels:
            signals = unresolved.get("conflicting_signals")
            if not isinstance(signals, list):
                signals = []
                unresolved["conflicting_signals"] = signals
            signals.append(f"competes_with:{winner_remote}")
            unresolved["conflicts_with_relationship_id"] = winner.get("relationship_id")

    previous_index = {
        _snapshot_identity(item): item
        for item in (previous_links or [])
        if isinstance(item, dict)
    }
    current_index = {
        _snapshot_identity(item): item
        for item in current_links
        if isinstance(item, dict)
    }

    for key, previous in previous_index.items():
        if key in current_index:
            continue
        stale_item = dict(previous)
        stale_item["status"] = "stale"
        stale_links.append(stale_item)

    relationship_views = []
    for item in current_links:
        relationship_views.append(
            {
                "source_device": item.get("source_device"),
                "target_device": item.get("target_device") or item.get("remote_device_name"),
                "source_inst_name": item.get("source_inst_name"),
                "target_inst_name": item.get("target_inst_name") or item.get("remote_port_name"),
                "model_id": item.get("model_id", "interface"),
                "asst_id": item.get("asst_id", "connect"),
                "model_asst_id": item.get("model_asst_id", "interface_connect_interface"),
                "relationship_type": item.get("relationship_type"),
                "evidence_source": item.get("evidence_source"),
                "confidence": item.get("confidence"),
                "vlan": item.get("vlan"),
                "status": item.get("status", "current"),
            }
        )

    multi_vlan_summary = build_multi_vlan_corroboration_summary(current_links, unresolved_candidates)

    return {
        "summary": {
            "devices": len(normalized.get("devices", [])),
            "ports": len(normalized.get("ports", [])),
            "authoritative_links": len(authoritative),
            "inferred_links": len(deduped_inferred),
            "stale_links": len(stale_links),
            "unresolved_neighbors": len(unresolved_candidates),
            "errors": len(normalized.get("errors", [])),
            "relationships": len(relationship_views),
        },
        "normalized": normalized,
        "topology": {
            "authoritative_links": authoritative,
            "inferred_links": list(deduped_inferred.values()),
            "stale_links": stale_links,
            "unresolved_neighbors": unresolved_candidates,
            "multi_vlan_corroboration_summary": multi_vlan_summary,
        },
        "relationships": relationship_views,
        "errors": normalized.get("errors", []),
    }


def parse_aggregate_result(aggregate: dict[str, Any], previous_links: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    normalized = normalize_topology_data(aggregate)
    inferred = infer_topology(normalized)
    return reconcile_topology(normalized, inferred, previous_links=previous_links)
