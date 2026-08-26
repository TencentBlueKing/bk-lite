from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

DB_SYSTEM_KEYS = ("db.system.name", "db.system")
DB_NAME_KEYS = ("db.namespace", "db.name")
MESSAGING_SYSTEM_KEYS = ("messaging.system",)
RPC_SYSTEM_KEYS = ("rpc.system",)
RPC_SERVICE_KEYS = ("rpc.service",)
PEER_SERVICE_KEYS = ("peer.service",)
SERVER_ADDRESS_KEYS = ("server.address",)
CLIENT_SPAN_KINDS = frozenset({"client", "producer"})
ENTRY_SPAN_KINDS = frozenset({"server", "consumer"})


def span_attribute_text(attributes: Mapping[str, object], keys: tuple[str, ...]) -> str:
    """同时认探针源码键与 VictoriaTraces `span_attr:` 存储前缀。"""

    for key in keys:
        for candidate in (key, f"span_attr:{key}"):
            value = attributes.get(candidate)
            if value is None or value is False:
                continue
            text = str(value).strip()
            if text:
                return text
    return ""


@dataclass(frozen=True)
class InferredDownstream:
    fold_key: str
    system: str
    category: str
    peer_address: str


def infer_downstream(attributes: Mapping[str, object]) -> InferredDownstream | None:
    """按产品折叠规则从 Client Span 属性推导未插桩下游。"""

    peer_service = span_attribute_text(attributes, PEER_SERVICE_KEYS)
    db_system = span_attribute_text(attributes, DB_SYSTEM_KEYS)
    messaging_system = span_attribute_text(attributes, MESSAGING_SYSTEM_KEYS)
    rpc_system = span_attribute_text(attributes, RPC_SYSTEM_KEYS)
    rpc_service = span_attribute_text(attributes, RPC_SERVICE_KEYS)
    server_address = span_attribute_text(attributes, SERVER_ADDRESS_KEYS)
    db_name = span_attribute_text(attributes, DB_NAME_KEYS)
    if peer_service:
        return InferredDownstream(peer_service, peer_service, "peer", server_address)
    if db_system:
        return InferredDownstream(db_system, db_system, "db", server_address or db_name)
    if messaging_system:
        return InferredDownstream(messaging_system, messaging_system, "messaging", server_address)
    if rpc_system:
        fold_key = rpc_service or rpc_system
        return InferredDownstream(fold_key, rpc_system, "rpc", server_address)
    if server_address:
        return InferredDownstream(server_address, server_address, "peer", server_address)
    return None
