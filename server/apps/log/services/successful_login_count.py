"""按主机判定登录采集覆盖，并把 VictoriaLogs stats 合并为成功登录次数。"""

from __future__ import annotations

import json

WINDOWS_OS_TYPE = "2"
WINDOWS_COLLECT_TYPES = frozenset({"winlogbeat"})
LINUX_COLLECT_TYPES = frozenset({"file", "filebeat"})

WINDOWS_SUCCESS_LOGIN_QUERY = "collect_type:winlogbeat AND event_id:4624"
LINUX_SUCCESS_LOGIN_QUERY = (
    '(message:"Accepted password" OR message:"Accepted publickey" OR message:"session opened")' ' AND NOT Failed AND NOT "Invalid user"'
)
STATS_BY_HOST_SUFFIX = "stats by (host) count() as entry_count"


def build_host_match_clause(hosts) -> str:
    """把本批 counted 主机的 host_name / ip 编成 LogSQL OR 子句；无名则返回空串。"""
    terms: list[str] = []
    seen: set[str] = set()
    for host in hosts or []:
        row = host if isinstance(host, dict) else {}
        for raw in (row.get("host_name"), row.get("ip")):
            if raw in (None, ""):
                continue
            value = str(raw).strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            quoted = json.dumps(value)
            terms.append(f"host:{quoted}")
            terms.append(f"hostname:{quoted}")
    if not terms:
        return ""
    return f"({' OR '.join(terms)})"


def _build_login_stats_query(base_query: str, hosts) -> str:
    clause = build_host_match_clause(hosts)
    if not clause:
        return ""
    return f"({base_query}) AND {clause} | {STATS_BY_HOST_SUFFIX}"


def build_windows_login_stats_query(hosts) -> str:
    return _build_login_stats_query(WINDOWS_SUCCESS_LOGIN_QUERY, hosts)


def build_linux_login_stats_query(hosts) -> str:
    return _build_login_stats_query(LINUX_SUCCESS_LOGIN_QUERY, hosts)


def _normalized_node_id(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _collect_type_name(instance) -> str:
    collect_type = getattr(instance, "collect_type", None)
    name = getattr(collect_type, "name", None)
    if name is None:
        return ""
    return str(name).strip()


def _instance_node_ids(collect_instances, collect_types: frozenset[str]) -> set[str]:
    node_ids: set[str] = set()
    for instance in collect_instances or []:
        if _collect_type_name(instance) not in collect_types:
            continue
        node_id = _normalized_node_id(getattr(instance, "node_id", None))
        if node_id is None:
            continue
        node_ids.add(node_id)
    return node_ids


def is_windows_os(os_type) -> bool:
    if os_type is None:
        return False
    return str(os_type).strip() == WINDOWS_OS_TYPE


def classify_login_coverage(hosts, collect_instances):
    """为每台主机打上 counted / uncollected；login_count 在合并 stats 前保持 None。"""
    instances = list(collect_instances or [])
    windows_nodes = _instance_node_ids(instances, WINDOWS_COLLECT_TYPES)
    linux_nodes = _instance_node_ids(instances, LINUX_COLLECT_TYPES)
    covered = []
    for host in hosts or []:
        row = dict(host) if isinstance(host, dict) else {}
        node_id = _normalized_node_id(row.get("node_id"))
        wanted = windows_nodes if is_windows_os(row.get("os_type")) else linux_nodes
        counted = node_id is not None and node_id in wanted
        row["login_status"] = "counted" if counted else "uncollected"
        row["login_count"] = None
        covered.append(row)
    return covered


def _stats_row_key(row: dict) -> str:
    for field in ("value", "host", "hostname"):
        raw = row.get(field)
        if raw in (None, ""):
            continue
        key = str(raw).strip().lower()
        if key:
            return key
    return ""


def _stats_row_count(row: dict) -> int:
    raw = row.get("count", row.get("entry_count"))
    if raw in (None, ""):
        return 0
    try:
        return int(float(str(raw)))
    except (TypeError, ValueError):
        return 0


def normalize_stats_rows(rows) -> list[dict]:
    """把 VL `{host, entry_count}` 或已规范化 `{value, count}` 收成统一键。"""
    normalized = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = _stats_row_key(row)
        if not key:
            continue
        normalized.append({"value": key, "count": _stats_row_count(row)})
    return normalized


def merge_login_counts(covered, stats_rows):
    """counted 主机按 host_name（大小写不敏感）再按 ip 对齐 stats；未命中记 0。uncollected 保持 None。"""
    lookup: dict[str, int] = {}
    for row in normalize_stats_rows(stats_rows):
        lookup.setdefault(row["value"], row["count"])

    merged = []
    for host in covered or []:
        row = dict(host) if isinstance(host, dict) else {}
        if row.get("login_status") != "counted":
            row["login_status"] = row.get("login_status") or "uncollected"
            row["login_count"] = None
            merged.append(row)
            continue

        host_name = str(row.get("host_name") or "").strip().lower()
        ip = str(row.get("ip") or "").strip().lower()
        count = lookup.get(host_name) if host_name else None
        if count is None and ip:
            count = lookup.get(ip)
        row["login_status"] = "counted"
        row["login_count"] = 0 if count is None else count
        merged.append(row)
    return merged
