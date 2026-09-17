"""Permission-visible System → Application → Host tree for 部署架构.

Compose service-tree contains edges plus `application_run_host`.
Callers pass already-visible instances; this module never invents
system→host edges and never emits hidden identities.
"""

from __future__ import annotations

from typing import Any

from apps.operation_analysis.services.application3d.constants import (
    APPLICATION_RUN_HOST_ASST,
    BIZ_GROUP_CONTAINS_APPLICATION_ASST,
    BIZ_GROUP_CONTAINS_BIZ_GROUP_ASST,
    SYSTEM_CONTAINS_APPLICATION_ASST,
    SYSTEM_CONTAINS_BIZ_GROUP_ASST,
)

ARCHITECTURE_NODE_SYSTEM = "system"
ARCHITECTURE_NODE_BIZ_GROUP = "biz_group"
ARCHITECTURE_NODE_APPLICATION = "application"
ARCHITECTURE_NODE_HOST = "host"


def compose_architecture_tree(
    *,
    system_id: str,
    system_name: str,
    system_health: dict[str, Any],
    application_ids: list[str],
    applications: dict[str, dict[str, Any]],
    hosts_by_application: dict[str, list[str]],
    hosts: dict[str, dict[str, Any]],
    group_ids: list[str] | None = None,
    groups: dict[str, dict[str, Any]] | None = None,
    group_parents: dict[str, str] | None = None,
    application_parents: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Build a directed tree for one System.

    - Root is always the System.
    - Optional业务分组 sit between system and applications.
    - Child applications keep input order; isolated apps (no host edges) stay.
    - Hosts are unique by inst_uuid; a shared host is one node with one edge
      from each parent application.
    - Invisible / wrong-peer identities must already be omitted by the caller.
    """
    groups = groups or {}
    group_ids = list(group_ids or [])
    group_parents = dict(group_parents or {})
    application_parents = dict(application_parents or {app_id: system_id for app_id in application_ids})

    children: dict[str, list[tuple[str, str]]] = {}
    for group_id in group_ids:
        if group_id not in groups:
            continue
        parent_id = group_parents.get(group_id, system_id)
        children.setdefault(parent_id, []).append((ARCHITECTURE_NODE_BIZ_GROUP, group_id))
    for application_id in application_ids:
        parent_id = application_parents.get(application_id, system_id)
        children.setdefault(parent_id, []).append((ARCHITECTURE_NODE_APPLICATION, application_id))

    nodes: list[dict[str, Any]] = [
        _node(
            node_id=system_id,
            kind=ARCHITECTURE_NODE_SYSTEM,
            name=system_name,
            health=system_health,
        )
    ]
    edges: list[dict[str, Any]] = []
    seen_hosts: set[str] = set()
    visible_ids = {system_id}

    def _relation(parent_id: str, child_kind: str) -> str:
        parent_is_group = parent_id in groups
        if child_kind == ARCHITECTURE_NODE_BIZ_GROUP:
            return BIZ_GROUP_CONTAINS_BIZ_GROUP_ASST if parent_is_group else SYSTEM_CONTAINS_BIZ_GROUP_ASST
        if parent_is_group:
            return BIZ_GROUP_CONTAINS_APPLICATION_ASST
        return SYSTEM_CONTAINS_APPLICATION_ASST

    def _emit_hosts(application_id: str) -> None:
        for host_id in hosts_by_application.get(application_id, []):
            host = hosts.get(host_id)
            if host is None:
                continue
            if host_id not in seen_hosts:
                seen_hosts.add(host_id)
                nodes.append(
                    _node(
                        node_id=host_id,
                        kind=ARCHITECTURE_NODE_HOST,
                        name=str(host.get("name") or host_id),
                        health=host.get("health"),
                        ip_addr=host.get("ip_addr"),
                        os_name=host.get("os_name"),
                    )
                )
            edges.append(
                _edge(
                    source_id=application_id,
                    target_id=host_id,
                    relation=APPLICATION_RUN_HOST_ASST,
                )
            )

    def walk(parent_id: str) -> None:
        for child_kind, child_id in children.get(parent_id, []):
            if child_kind == ARCHITECTURE_NODE_BIZ_GROUP:
                group = groups.get(child_id)
                if group is None or parent_id not in visible_ids:
                    continue
                nodes.append(
                    _node(
                        node_id=child_id,
                        kind=ARCHITECTURE_NODE_BIZ_GROUP,
                        name=str(group.get("name") or child_id),
                        health=group.get("health"),
                    )
                )
                edges.append(
                    _edge(
                        source_id=parent_id,
                        target_id=child_id,
                        relation=_relation(parent_id, child_kind),
                    )
                )
                visible_ids.add(child_id)
                walk(child_id)
                continue
            application = applications.get(child_id)
            if application is None or parent_id not in visible_ids:
                continue
            nodes.append(
                _node(
                    node_id=child_id,
                    kind=ARCHITECTURE_NODE_APPLICATION,
                    name=str(application.get("name") or child_id),
                    health=application.get("health"),
                )
            )
            edges.append(
                _edge(
                    source_id=parent_id,
                    target_id=child_id,
                    relation=_relation(parent_id, child_kind),
                )
            )
            visible_ids.add(child_id)
            _emit_hosts(child_id)

    walk(system_id)

    return {
        "systemId": system_id,
        "nodes": nodes,
        "edges": edges,
    }


def _node(
    *,
    node_id: str,
    kind: str,
    name: str,
    health: dict[str, Any] | None,
    ip_addr: str | None = None,
    os_name: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": node_id,
        "kind": kind,
        "name": name,
    }
    if health is not None:
        payload["health"] = health
    if ip_addr:
        payload["ip_addr"] = ip_addr
    if os_name:
        payload["os_name"] = os_name
    return payload


def _edge(*, source_id: str, target_id: str, relation: str) -> dict[str, Any]:
    return {
        "id": f"{relation}:{source_id}:{target_id}",
        "sourceId": source_id,
        "targetId": target_id,
        "relation": relation,
    }
