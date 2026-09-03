"""Permission-visible System → Application → Host tree for 部署架构.

Compose only exact `system_contains_application` and `application_run_host`
edges. Callers pass already-visible instances; this module never invents
system→host edges and never emits hidden identities.
"""

from __future__ import annotations

from typing import Any

from apps.operation_analysis.services.application3d.constants import APPLICATION_RUN_HOST_ASST, SYSTEM_CONTAINS_APPLICATION_ASST

ARCHITECTURE_NODE_SYSTEM = "system"
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
) -> dict[str, Any]:
    """
    Build a 3-rank directed tree for one System.

    - Root is always the System.
    - Child applications keep input order; isolated apps (no host edges) stay.
    - Hosts are unique by inst_uuid; a shared host is one node with one edge
      from each parent application.
    - Invisible / wrong-peer identities must already be omitted by the caller.
    """
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

    for application_id in application_ids:
        application = applications.get(application_id)
        if application is None:
            continue
        nodes.append(
            _node(
                node_id=application_id,
                kind=ARCHITECTURE_NODE_APPLICATION,
                name=str(application.get("name") or application_id),
                health=application.get("health"),
            )
        )
        edges.append(
            _edge(
                source_id=system_id,
                target_id=application_id,
                relation=SYSTEM_CONTAINS_APPLICATION_ASST,
            )
        )
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
                    )
                )
            edges.append(
                _edge(
                    source_id=application_id,
                    target_id=host_id,
                    relation=APPLICATION_RUN_HOST_ASST,
                )
            )

    return {
        "systemId": system_id,
        "nodes": nodes,
        "edges": edges,
    }


def _node(*, node_id: str, kind: str, name: str, health: dict[str, Any] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": node_id,
        "kind": kind,
        "name": name,
    }
    if health is not None:
        payload["health"] = health
    return payload


def _edge(*, source_id: str, target_id: str, relation: str) -> dict[str, Any]:
    return {
        "id": f"{relation}:{source_id}:{target_id}",
        "sourceId": source_id,
        "targetId": target_id,
        "relation": relation,
    }
