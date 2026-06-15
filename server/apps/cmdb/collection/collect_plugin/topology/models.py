# 移植自 snmp_topo_tool/topology_models.py（独立工具，已真机验证）。
# 修改时需与工具侧保持同步。
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class NormalizedDevice:
    device_id: str
    host: str
    sys_name: str = ""
    ips: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NormalizedPort:
    device_id: str
    port_id: str
    ifindex: str
    ifname: str = ""
    ifalias: str = ""
    ifdescr: str = ""
    mac: str = ""

    @property
    def display_name(self) -> str:
        return self.ifname or self.ifalias or self.ifdescr or self.port_id

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["display_name"] = self.display_name
        return payload


@dataclass(slots=True)
class NeighborObservation:
    source_device_id: str
    local_port_id: str
    protocol: str
    evidence_key: str
    local_port_num: str = ""
    remote_system_name: str = ""
    remote_chassis_id: str = ""
    remote_port_id: str = ""
    remote_port_subtype: str = ""
    remote_port_value: str = ""
    remote_port_desc: str = ""
    remote_address: str = ""
    resolution_state: str = "resolved"
    raw_remote_fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ArpObservation:
    source_device_id: str
    local_port_id: str
    ip_address: str
    mac: str
    evidence_key: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FdbObservation:
    source_device_id: str
    local_port_id: str
    mac: str
    evidence_key: str
    status: str = ""
    vlan: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LinkCandidate:
    relationship_id: str
    relationship_type: str
    evidence_source: str
    confidence: int
    source_device: str
    source_port_id: str
    source_inst_name: str
    target_device: str | None = None
    target_port_id: str | None = None
    target_inst_name: str | None = None
    remote_device_name: str | None = None
    remote_port_name: str | None = None
    vlan: str | None = None
    model_id: str = "interface"
    asst_id: str = "connect"
    model_asst_id: str = "interface_connect_interface"
    provenance: list[dict[str, Any]] = field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)
    status: str = "current"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
