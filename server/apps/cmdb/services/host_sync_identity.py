"""节点拉同步与节点→CMDB ingest 共用的 host 身份规则。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from apps.node_mgmt.services.module_push_contract import LINK_CONFLICT

Finder = Callable[..., dict[str, Any] | None]


def normalize_link_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def build_host_inst_name(*, ip: str, cloud_name: Any = None, cloud_id: Any = None) -> str:
    """主机实例名：`{ip}[{云区域名}]`，无名称时用云区域 ID。"""
    ip_str = str(ip or "").strip()
    if not ip_str:
        return ""
    label = str(cloud_name or "").strip()
    if not label and cloud_id not in (None, ""):
        label = str(cloud_id).strip()
    if not label:
        return ip_str
    return f"{ip_str}[{label}]"


def host_lookup_key(*, ip_addr: Any, cloud: Any) -> tuple[str, int | None]:
    ip = str(ip_addr or "").strip()
    try:
        normalized_cloud = int(cloud) if cloud not in (None, "") else None
    except (TypeError, ValueError):
        normalized_cloud = None
    return ip, normalized_cloud


@dataclass
class HostIdentityMatch:
    instance: dict[str, Any] | None = None
    conflict: str | None = None
    skipped: bool = False
    via: str | None = None


def resolve_host_identity(
    *,
    node_id: Any,
    cmdb_id: Any,
    ip: Any,
    cloud: Any,
    find_by_node_id: Finder,
    find_by_cmdb_id: Finder,
    find_by_ip_cloud: Finder,
) -> HostIdentityMatch:
    """按 node_id → cmdb_id → ip+cloud 认同一台 host。

    有 node_id 时不回落到 cmdb_id。认领对象已绑定其它 node_id 则 conflict。
    缺少 ip 或 cloud 且 ID 未命中则 skipped（拉同步应跳过新建）。
    """
    incoming_node_id = normalize_link_id(node_id)
    incoming_cmdb_id = normalize_link_id(cmdb_id)
    ip_str, cloud_id = host_lookup_key(ip_addr=ip, cloud=cloud)

    if incoming_node_id:
        found = find_by_node_id(incoming_node_id) or None
        if found:
            return HostIdentityMatch(instance=found, via="node_id")
    elif incoming_cmdb_id:
        found = find_by_cmdb_id(incoming_cmdb_id) or None
        if found:
            return HostIdentityMatch(instance=found, via="cmdb_id")

    if not ip_str or cloud_id is None:
        return HostIdentityMatch(skipped=True)

    found = find_by_ip_cloud(ip_str, cloud_id) or None
    if not found:
        return HostIdentityMatch(instance=None)

    existing_node_id = normalize_link_id(found.get("node_id"))
    if incoming_node_id and existing_node_id and existing_node_id != incoming_node_id:
        return HostIdentityMatch(instance=found, conflict=LINK_CONFLICT, via="ip_cloud")
    return HostIdentityMatch(instance=found, via="ip_cloud")


def is_node_mgmt_sidecar_id(value: Any) -> bool:
    """Sidecar 节点 ID 为 uuid4().hex（32 位小写十六进制），与 IPMI/RPC 合成 ID 区分。"""
    text = normalize_link_id(value)
    if not text or len(text) != 32:
        return False
    return all(ch in "0123456789abcdef" for ch in text)


def node_id_to_write(existing: dict[str, Any] | None, incoming_node_id: Any) -> str | None:
    """空则补、相同则不动、冲突由 resolve 拦截后不会走到这里。"""
    incoming = normalize_link_id(incoming_node_id)
    if not incoming:
        return None
    current = normalize_link_id((existing or {}).get("node_id"))
    if current:
        return None
    return incoming


def is_unique_conflict(exc: BaseException) -> bool:
    if getattr(exc, "reason", None) == "unique_conflict":
        return True
    message = str(getattr(exc, "message", "") or exc).lower()
    return "exist" in message or "重复" in message or "唯一" in message
