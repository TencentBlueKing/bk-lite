"""已监控 CMDB 主机选项行：只保留 monitor_id 非空的 host。"""

from __future__ import annotations

from typing import Any

OS_TYPE_LABELS = {"1": "Linux", "2": "Windows", "3": "AIX", "4": "Unix"}


def normalize_zombie_whitelist(value: Any) -> str:
    items = value if isinstance(value, (list, tuple)) else [value]
    for item in items:
        if isinstance(item, str) and item.strip() == "yes":
            return "yes"
    return "no"


def _scalar_cmdb_text(value: Any) -> str:
    current = value
    while isinstance(current, (list, tuple)):
        if not current:
            return ""
        current = current[0]
    if current is None:
        return ""
    return str(current).strip()


def _os_type_label(os_type: Any) -> str:
    key = _scalar_cmdb_text(os_type)
    return OS_TYPE_LABELS.get(key, "Other")


def _lookup_org_name(org_id: Any, org_names: dict[Any, str]) -> str:
    if org_id in org_names:
        return str(org_names[org_id] or "")
    try:
        as_int = int(org_id)
    except (TypeError, ValueError):
        as_int = None
    if as_int is not None and as_int in org_names:
        return str(org_names[as_int] or "")
    as_str = str(org_id)
    if as_str in org_names:
        return str(org_names[as_str] or "")
    return ""


def _biz_name(entity: dict[str, Any], org_names: dict[Any, str] | None) -> str:
    names_map = org_names or {}
    raw = entity.get("organization") or []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    labels = [label for org_id in raw if (label := _lookup_org_name(org_id, names_map))]
    return "、".join(labels)


def _nonempty_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_monitored_host_row(
    entity: dict[str, Any] | None,
    org_names: dict[Any, str] | None = None,
) -> dict[str, Any] | None:
    data = dict(entity or {})
    inst_uuid = _nonempty_text(data.get("inst_uuid"))
    monitor_id = _nonempty_text(data.get("monitor_id"))
    if not inst_uuid or not monitor_id:
        return None

    host_name = "" if data.get("inst_name") is None else str(data.get("inst_name"))
    ip = "" if data.get("ip_addr") is None else str(data.get("ip_addr"))
    os_type = _scalar_cmdb_text(data.get("os_type"))
    row: dict[str, Any] = {
        "inst_uuid": inst_uuid,
        "monitor_id": monitor_id,
        "display_name": f"{host_name} ({ip})",
        "host_name": host_name,
        "ip": ip,
        "os_type": os_type,
        "os_type_label": _os_type_label(os_type),
        "biz_name": _biz_name(data, org_names),
        "zombie_whitelist": normalize_zombie_whitelist(data.get("zombie_whitelist")),
    }
    node_id = data.get("node_id")
    if node_id not in (None, ""):
        row["node_id"] = node_id
    return row
