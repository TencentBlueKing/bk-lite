from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Protocol

from apps.rpc.job_mgmt import JobMgmt
from apps.rpc.node_mgmt import NodeMgmt

SUPPORTED_SOURCES = {"node_mgmt", "job_mgmt"}


class TargetResolutionError(ValueError):
    pass


class TargetDependencyUnavailable(RuntimeError):
    pass


class TargetGateway(Protocol):
    def resolve(self, source: str, source_ids: list[str]) -> list[dict[str, Any]]:
        ...


class RpcTargetGateway:
    def __init__(
        self,
        *,
        team: int,
        permission_data: dict[str, Any],
        node_client: NodeMgmt | None = None,
        job_client: JobMgmt | None = None,
    ):
        self.team = team
        self.permission_data = permission_data
        self.node_client = node_client or NodeMgmt(is_local_client=True)
        self.job_client = job_client or JobMgmt(is_local_client=True)
        self.actor_context = {
            "username": str(permission_data.get("username") or ""),
            "domain": str(permission_data.get("domain") or "domain.com"),
            "authorized_team_ids": [team],
        }

    def resolve(self, source: str, source_ids: list[str]) -> list[dict[str, Any]]:
        if source == "node_mgmt":
            try:
                nodes = self.node_client.get_authorized_execution_targets_by_ids(source_ids, self.permission_data) or []
            except Exception as error:
                raise TargetDependencyUnavailable("节点管理目标校验暂时不可用") from error
            return [
                {
                    "id": f"node:{node['id']}",
                    "source": "node_mgmt",
                    "source_id": str(node["id"]),
                    "name": node.get("name", ""),
                    "ip": node.get("ip", ""),
                    "operating_system": node.get("operating_system", ""),
                    "cloud_region_id": node.get("cloud_region_id"),
                    "connected": node.get("active") if isinstance(node.get("active"), bool) else None,
                }
                for node in nodes
            ]
        if source == "job_mgmt":
            try:
                target_ids = [int(source_id) for source_id in source_ids]
            except (TypeError, ValueError) as error:
                raise TargetResolutionError("作业平台目标 ID 非法") from error
            try:
                response = (
                    self.job_client.list_automation_targets(
                        {"target_ids": target_ids, "page": 1, "page_size": 100},
                        self.actor_context,
                    )
                    or {}
                )
            except Exception as error:
                raise TargetDependencyUnavailable("作业平台目标校验暂时不可用") from error
            if not response.get("result"):
                raise TargetDependencyUnavailable(str(response.get("message") or "无法校验作业平台目标"))
            return [
                {
                    "id": f"manual:{target['target_id']}",
                    "source": "job_mgmt",
                    "source_id": str(target["target_id"]),
                    "name": target.get("name", ""),
                    "ip": target.get("ip", ""),
                    "operating_system": target.get("os_type", ""),
                    "cloud_region_id": target.get("cloud_region_id"),
                    "connected": None,
                }
                for target in (response.get("data") or {}).get("items", [])
            ]
        raise TargetResolutionError(f"不支持的目标来源: {source}")


@dataclass(frozen=True)
class TargetResolution:
    inputs: dict[str, Any]
    snapshot: dict[str, Any]
    offline_targets: list[dict[str, Any]]
    unique_total: int


def _parse_reference(reference: Any, allowed_sources: set[str]) -> tuple[str, str, str]:
    value = str(reference)
    if value.startswith("node:") and value[5:]:
        source, source_id = "node_mgmt", value[5:]
    elif value.startswith("manual:") and value[7:].isdigit():
        source, source_id = "job_mgmt", value[7:]
    else:
        raise TargetResolutionError(f"非法目标引用: {value}")
    if source not in allowed_sources:
        raise TargetResolutionError(f"目标来源不允许: {value}")
    return value, source, source_id


def _identity_key(target: dict[str, Any]) -> tuple[str, str] | None:
    ip = str(target.get("ip") or "").strip().lower()
    if not ip:
        return None
    return str(target.get("cloud_region_id") or ""), ip


def _snapshot_item(target: dict[str, Any]) -> dict[str, Any]:
    connected = target.get("connected")
    return {
        "id": target["id"],
        "source": target["source"],
        "source_id": str(target["source_id"]),
        "name": str(target.get("name") or ""),
        "ip": str(target.get("ip") or ""),
        "operating_system": str(target.get("operating_system") or "").lower(),
        "cloud_region_id": target.get("cloud_region_id"),
        "connected": connected if isinstance(connected, bool) else None,
    }


def resolve_target_fields(
    inputs: dict[str, Any],
    target_fields: list[dict[str, Any]],
    *,
    gateway: TargetGateway,
    total_limit: int = 100,
) -> TargetResolution:
    resolved_inputs = copy.deepcopy(inputs)
    parsed_fields: dict[str, list[tuple[str, str, str]]] = {}
    refs_by_source: dict[str, list[str]] = {"node_mgmt": [], "job_mgmt": []}
    all_references: set[str] = set()
    for field in target_fields:
        key = str(field.get("key") or "")
        raw_references = inputs.get(key, [])
        if not isinstance(raw_references, list):
            raise TargetResolutionError(f"目标字段 {key} 必须是数组")
        references = [str(value) for value in raw_references]
        if len(set(references)) != len(references):
            raise TargetResolutionError(f"目标字段 {key} 不能包含重复目标")
        min_count = int(field.get("min_count", 1 if field.get("required") else 0))
        max_count = int(field.get("max_count", total_limit))
        if not min_count <= len(references) <= max_count:
            raise TargetResolutionError(f"目标字段 {key} 必须选择 {min_count} 到 {max_count} 台主机")
        allowed_sources = set(field.get("allowed_sources") or [])
        if not allowed_sources or not allowed_sources <= SUPPORTED_SOURCES:
            raise TargetResolutionError(f"目标字段 {key} 的允许来源非法")
        parsed = [_parse_reference(reference, allowed_sources) for reference in references]
        parsed_fields[key] = parsed
        for reference, source, source_id in parsed:
            all_references.add(reference)
            if source_id not in refs_by_source[source]:
                refs_by_source[source].append(source_id)
    if len(all_references) > total_limit:
        raise TargetResolutionError(f"所有目标字段去重后的总数不能超过 {total_limit} 台")

    target_map: dict[str, dict[str, Any]] = {}
    for source, source_ids in refs_by_source.items():
        if not source_ids:
            continue
        for target in gateway.resolve(source, source_ids):
            item = _snapshot_item(target)
            target_map[item["id"]] = item
    missing = sorted(all_references - set(target_map))
    if missing:
        raise TargetResolutionError(f"目标不存在或无权访问: {', '.join(missing[:10])}")

    identities: dict[tuple[str, str], dict[str, Any]] = {}
    for reference in sorted(all_references):
        target = target_map[reference]
        identity = _identity_key(target)
        if identity is None:
            continue
        existing = identities.get(identity)
        if existing and existing["source"] != target["source"]:
            raise TargetResolutionError(f"跨来源目标身份冲突: {existing['id']} 与 {target['id']}")
        identities[identity] = target

    snapshot_fields: dict[str, Any] = {}
    offline_map: dict[str, dict[str, Any]] = {}
    for key, parsed in parsed_fields.items():
        items = [copy.deepcopy(target_map[reference]) for reference, _, _ in parsed]
        field = next(item for item in target_fields if str(item.get("key") or "") == key)
        allowed_operating_systems = set(field.get("allowed_operating_systems") or [])
        unsupported = sorted(
            {
                item["operating_system"] or "unknown"
                for item in items
                if allowed_operating_systems and item["operating_system"] not in allowed_operating_systems
            }
        )
        if unsupported:
            raise TargetResolutionError(f"目标字段 {key} 包含不支持的操作系统: {', '.join(unsupported)}")
        for item in items:
            if item["connected"] is False:
                offline_map[item["id"]] = copy.deepcopy(item)
        resolved_inputs[key] = items
        snapshot_fields[key] = {
            "items": copy.deepcopy(items),
            "count": len(items),
            "offline_count": sum(item["connected"] is False for item in items),
            "source_counts": {source: sum(item["source"] == source for item in items) for source in ("node_mgmt", "job_mgmt")},
            "operating_system_counts": {
                operating_system: sum(item["operating_system"] == operating_system for item in items) for operating_system in ("linux", "windows")
            },
        }
    snapshot = {
        "fields": snapshot_fields,
        "unique_total": len(all_references),
        "offline_count": len(offline_map),
    }
    return TargetResolution(
        inputs=resolved_inputs,
        snapshot=snapshot,
        offline_targets=list(offline_map.values()),
        unique_total=len(all_references),
    )
