from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

DB_SYSTEM_KEYS = ("db.system.name", "db.system")
DB_NAME_KEYS = ("db.namespace", "db.name")
MESSAGING_SYSTEM_KEYS = ("messaging.system",)
RPC_SYSTEM_KEYS = ("rpc.system",)
RPC_SERVICE_KEYS = ("rpc.service",)
PEER_SERVICE_KEYS = ("peer.service",)
HOST_KEYS = ("server.address", "net.peer.name", "network.peer.address", "net.peer.ip")
PORT_KEYS = ("server.port", "net.peer.port", "network.peer.port")
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


def format_peer_endpoint(host: str, port: str) -> str:
    """只拼接 Span 里实际有的 host / port，缺端口时不加默认端口。"""

    if not host:
        return ""
    if not port:
        return host
    if ":" in host and not host.startswith("["):
        return f"[{host}]:{port}"
    return f"{host}:{port}"


@dataclass(frozen=True)
class InferredDownstream:
    fold_key: str
    system: str
    category: str
    host: str = ""
    port: str = ""
    db_name: str = ""

    @property
    def peer_address(self) -> str:
        return format_peer_endpoint(self.host, self.port)


def infer_downstream(attributes: Mapping[str, object]) -> InferredDownstream | None:
    """按产品折叠规则从 Client Span 属性推导未插桩下游。"""

    peer_service = span_attribute_text(attributes, PEER_SERVICE_KEYS)
    db_system = span_attribute_text(attributes, DB_SYSTEM_KEYS)
    messaging_system = span_attribute_text(attributes, MESSAGING_SYSTEM_KEYS)
    rpc_system = span_attribute_text(attributes, RPC_SYSTEM_KEYS)
    rpc_service = span_attribute_text(attributes, RPC_SERVICE_KEYS)
    host = span_attribute_text(attributes, HOST_KEYS)
    port = span_attribute_text(attributes, PORT_KEYS)
    db_name = span_attribute_text(attributes, DB_NAME_KEYS)
    extras = {"host": host, "port": port, "db_name": db_name}
    if peer_service:
        return InferredDownstream(peer_service, peer_service, "peer", **extras)
    if db_system:
        return InferredDownstream(db_system, db_system, "db", **extras)
    if messaging_system:
        return InferredDownstream(messaging_system, messaging_system, "messaging", **extras)
    if rpc_system:
        fold_key = rpc_service or rpc_system
        return InferredDownstream(fold_key, rpc_system, "rpc", **extras)
    if host:
        return InferredDownstream(host, host, "peer", **extras)
    return None
