"""CMDB/log seams for the zombie host report NATS handler.

Handler tests patch these names on `apps.monitor.nats.monitor`.

Nested CMDB/log lookups run in-process. The report already occupies a NATS
worker; sending request-reply back into the same four-worker queue deadlocks
until the 60s timeout.
"""

from __future__ import annotations

import importlib
from typing import Any

from apps.cmdb.services.monitored_host import build_monitored_host_row
from apps.core.utils.current_team_scope import _normalize_organization_ids
from apps.monitor.services.zombie_host_report import MAX_HOSTS
from apps.rpc.cmdb import CMDB
from apps.system_mgmt.models import Group

_CMDB_HOSTS_MODULES = (
    "apps.cmdb.nats.zombie_overlay",
    "apps.cmdb.nats.nats",
)
_LOGIN_COUNT_MODULES = (
    "apps.log.nats.zombie_overlay",
    "apps.log.nats.log",
)


class ZombieHostQueryError(Exception):
    """CMDB/log seam failure that must fail the whole report request."""


def _organization_ids_from_user_info(user_info: dict | None) -> list[int]:
    if not isinstance(user_info, dict):
        return []
    raw = user_info.get("allowed_org_ids")
    if raw is None:
        team = user_info.get("team")
        if team in (None, ""):
            return []
        raw = team if isinstance(team, (list, tuple)) else [team]
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    try:
        return list(_normalize_organization_ids(raw))
    except Exception:
        return []


def _unwrap_rpc_payload(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("result"), bool):
        if not payload["result"]:
            raise ZombieHostQueryError(str(payload.get("message") or "查询失败"))
        return payload.get("data")
    return payload


def _iter_cmdb_entities(payload: Any) -> list[dict]:
    data = _unwrap_rpc_payload(payload)
    if data is None:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [item for item in data.values() if isinstance(item, dict)]
    raise ZombieHostQueryError("CMDB 查询结果格式错误")


def _authorized_inst_uuids(payload: Any) -> set[str]:
    data = _unwrap_rpc_payload(payload)
    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        raw = data.get("items")
        if isinstance(raw, list):
            items = raw
    authorized: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        inst_uuid = str(item.get("inst_uuid") or "").strip()
        monitor_id = str(item.get("monitor_id") or "").strip()
        if inst_uuid and monitor_id:
            authorized.add(inst_uuid)
    return authorized


def _org_ids_from_entities(entities: list[dict]) -> set:
    org_ids: set = set()
    for entity in entities:
        raw = entity.get("organization")
        if raw in (None, ""):
            continue
        if isinstance(raw, (list, tuple)):
            org_ids.update(item for item in raw if item not in (None, ""))
        else:
            org_ids.add(raw)
    return org_ids


def _org_names_for_entities(entities: list[dict]) -> dict:
    org_ids = _org_ids_from_entities(entities)
    if not org_ids:
        return {}
    return {group["id"]: group["name"] for group in Group.objects.filter(id__in=org_ids).values("id", "name")}


def run_inprocess_handler(module_paths: tuple[str, ...], method_name: str, **kwargs):
    """Call a registered NATS handler in this process; skip missing overlay modules."""
    for path in module_paths:
        try:
            module = importlib.import_module(path)
        except ImportError:
            continue
        fn = getattr(module, method_name, None)
        if callable(fn):
            return fn(**kwargs)
    raise ZombieHostQueryError(f"未找到本地接口 {method_name}")


def load_selected_hosts(inst_uuids, user_info):
    """Resolve selected CMDB hosts with non-empty monitor_id, preserving request order."""
    requested = [str(item) for item in (inst_uuids or [])]
    cmdb = CMDB(is_local_client=True)
    payload = cmdb.search_instances_batch(
        protocol_version=2,
        model_id="host",
        inst_uuids=requested,
        organization_ids=_organization_ids_from_user_info(user_info),
    )
    entities = _iter_cmdb_entities(payload)
    authorized = _authorized_inst_uuids(cmdb.get_monitor_ids_by_inst_uuids(inst_uuids=requested, user_info=user_info))
    org_names = _org_names_for_entities(entities)
    wanted = set(requested)
    by_uuid: dict[str, dict] = {}
    for entity in entities:
        row = build_monitored_host_row(entity, org_names=org_names)
        if row is None:
            continue
        inst_uuid = row["inst_uuid"]
        if inst_uuid not in wanted or inst_uuid not in authorized:
            continue
        by_uuid[inst_uuid] = row
    return [by_uuid[item] for item in requested if item in by_uuid]


def load_host_uuids_for_systems(system_uuids, user_info):
    """Expand authorized application systems to host UUIDs via CMDB NATS."""
    cmdb = CMDB(is_local_client=True)
    payload = cmdb.list_host_uuids_for_systems(system_uuids=list(system_uuids or []), user_info=user_info)
    data = _unwrap_rpc_payload(payload)
    if data is None:
        return []
    if isinstance(data, dict):
        data = data.get("items") if isinstance(data.get("items"), list) else data.get("data")
    if data is None:
        return []
    if not isinstance(data, list):
        raise ZombieHostQueryError("CMDB 应用系统主机查询结果格式错误")
    host_uuids: list[str] = []
    seen: set[str] = set()
    for item in data:
        if isinstance(item, dict):
            text = str(item.get("inst_uuid") or "").strip()
        else:
            text = "" if item is None else str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        host_uuids.append(text)
    return host_uuids


def load_hosts_for_systems(system_uuids, user_info):
    """一次拉取应用系统下已监控主机行；展开台数仍受 100 上限约束。"""
    payload = run_inprocess_handler(
        _CMDB_HOSTS_MODULES,
        "list_monitored_hosts_for_systems",
        system_uuids=list(system_uuids or []),
        user_info=user_info,
    )
    data = _unwrap_rpc_payload(payload)
    if data is None:
        return []
    if isinstance(data, list):
        items = data
        expanded_host_count = len(items)
    elif isinstance(data, dict):
        items = data.get("items")
        if items is None:
            items = []
        if not isinstance(items, list):
            raise ZombieHostQueryError("CMDB 应用系统主机查询结果格式错误")
        raw_count = data.get("expanded_host_count", len(items))
        try:
            expanded_host_count = int(raw_count)
        except (TypeError, ValueError) as exc:
            raise ZombieHostQueryError("CMDB 应用系统主机查询结果格式错误") from exc
    else:
        raise ZombieHostQueryError("CMDB 应用系统主机查询结果格式错误")
    if expanded_host_count > MAX_HOSTS:
        raise ValueError("一次最多查询 100 台主机")
    return [item for item in items if isinstance(item, dict)]


def count_successful_logins(hosts, time_range, user_info=None):
    """In-process successful-login counts; pass RFC3339 pair as time_range."""
    return run_inprocess_handler(
        _LOGIN_COUNT_MODULES,
        "count_successful_logins_by_host",
        hosts=hosts,
        time_range=time_range,
        user_info=user_info,
    )
