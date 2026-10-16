from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

DB_SYSTEM_KEYS = ("db.system.name", "db.system")
CACHE_DB_SYSTEMS = frozenset({"redis", "memcached", "valkey"})
DB_NAME_KEYS = ("db.namespace", "db.name")
DB_STATEMENT_KEYS = ("db.statement", "db.query.text")
MESSAGING_SYSTEM_KEYS = ("messaging.system",)
RPC_SYSTEM_KEYS = ("rpc.system",)
RPC_SERVICE_KEYS = ("rpc.service",)
PEER_SERVICE_KEYS = ("peer.service",)
HOST_KEYS = ("server.address", "net.peer.name", "network.peer.address", "net.peer.ip")
PORT_KEYS = ("server.port", "net.peer.port", "network.peer.port")
HTTP_ENTRY_KEYS = ("http.request.method", "http.method", "http.route", "url.path")
HTTP_CLIENT_METHOD_KEYS = ("http.request.method", "http.method")
HTTP_ROUTE_KEYS = ("http.route",)
CLIENT_SPAN_KINDS = frozenset({"client", "producer"})
ENTRY_SPAN_KINDS = frozenset({"server", "consumer"})
SERVER_SPAN_KIND = "server"


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


def is_user_request_entry(kind: str, attributes: Mapping[str, object]) -> bool:
    """判定 Span 是否由外部 HTTP/RPC 请求触发（用户请求入口）。

    只认 server 类 Span；消息消费（consumer）与无 HTTP/RPC 语义属性的
    根 Span（定时任务等）不算用户请求。父 Span 归属由拓扑构图判断。
    """

    if kind != SERVER_SPAN_KIND:
        return False
    return bool(span_attribute_text(attributes, HTTP_ENTRY_KEYS) or span_attribute_text(attributes, RPC_SYSTEM_KEYS))


def classify_client_db_rollup(attributes: Mapping[str, object]) -> tuple[str, str] | None:
    """把带数据库系统的 Client Span 分成语句或缓存出站。

    系统名按 db.system.name、db.system 的顺序取值。redis / memcached / valkey
    归出站，其余数据库系统归语句。没有数据库系统时返回空，服务间 HTTP 不进这张表。
    """

    system = span_attribute_text(attributes, DB_SYSTEM_KEYS)
    if not system:
        return None
    channel = "outbound" if system.lower() in CACHE_DB_SYSTEMS else "database"
    return channel, system


def client_db_statement(attributes: Mapping[str, object], name: str = "") -> str:
    """优先用探针采到的 SQL/命令文本，缺省才回落到 Span 名（通常只是 SELECT/GET）。"""

    return span_attribute_text(attributes, DB_STATEMENT_KEYS) or str(name or "").strip()


def classify_client_http_rollup(attributes: Mapping[str, object], name: str = "") -> tuple[str, str, str] | None:
    """把无数据库系统的 HTTP Client Span 归到出站 HTTP。

    服务间调用也会留下 http.method；产品要把这些操作列在「出站调用 / HTTP」。
    未接入对端用 peer.service 当系统名，已接入对端没有该字段时系统名为 http。
    有 http.route 时用「方法 + 路由」做语句，避免 Span 名只剩 GET/POST。
    """

    if classify_client_db_rollup(attributes) is not None:
        return None
    method = span_attribute_text(attributes, HTTP_CLIENT_METHOD_KEYS)
    if not method:
        return None
    route = span_attribute_text(attributes, HTTP_ROUTE_KEYS)
    peer = span_attribute_text(attributes, PEER_SERVICE_KEYS)
    if route:
        statement = f"{method} {route}".strip()
    else:
        statement = str(name or "").strip() or method
    return "http", peer or "http", statement[:256]


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
