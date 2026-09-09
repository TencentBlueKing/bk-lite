"""应用系统选项行，以及 system → application → host 展开。"""

from __future__ import annotations

from typing import Any, Callable

from apps.cmdb.constants.constants import INSTANCE_ASSOCIATION
from apps.cmdb.graph.drivers.graph_client import GraphClient

SYSTEM_CONTAINS_APPLICATION = "system_contains_application"
APPLICATION_RUN_HOST = "application_run_host"
ASSOCIATION_EDGE_BATCH_SIZE = 200

AssociationLoader = Callable[[str, str], list[dict[str, Any]]]
EdgeLoader = Callable[[str, list[str]], list[dict[str, Any]]]


def _nonempty_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_application_system_row(entity: dict[str, Any] | None) -> dict[str, Any] | None:
    data = dict(entity or {})
    inst_uuid = _nonempty_text(data.get("inst_uuid"))
    if not inst_uuid:
        return None
    inst_name = "" if data.get("inst_name") is None else str(data.get("inst_name"))
    return {
        "inst_uuid": inst_uuid,
        "inst_name": inst_name,
        "display_name": inst_name or inst_uuid,
    }


def _peer_uuids(associations: list[dict[str, Any]] | None, asst_id: str, peer_model_id: str) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for assoc in associations or []:
        if not isinstance(assoc, dict):
            continue
        if assoc.get("model_asst_id") != asst_id:
            continue
        for peer in assoc.get("inst_list") or []:
            if not isinstance(peer, dict):
                continue
            if peer.get("model_id") != peer_model_id:
                continue
            inst_uuid = _nonempty_text(peer.get("inst_uuid"))
            if not inst_uuid or inst_uuid in seen:
                continue
            seen.add(inst_uuid)
            ordered.append(inst_uuid)
    return ordered


def _chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _flatten_association_edge(item: dict[str, Any] | None) -> dict[str, Any]:
    data = item if isinstance(item, dict) else {}
    if "edge" not in data and ("src_inst_uuid" in data or "dst_inst_uuid" in data):
        return data
    edge = dict(data.get("edge") or {})
    src = data.get("src") or {}
    dst = data.get("dst") or {}
    if not edge.get("src_inst_uuid") and src.get("inst_uuid"):
        edge["src_inst_uuid"] = src.get("inst_uuid")
    if not edge.get("dst_inst_uuid") and dst.get("inst_uuid"):
        edge["dst_inst_uuid"] = dst.get("inst_uuid")
    if not edge.get("src_model_id") and src.get("model_id"):
        edge["src_model_id"] = src.get("model_id")
    if not edge.get("dst_model_id") and dst.get("model_id"):
        edge["dst_model_id"] = dst.get("model_id")
    return edge


def query_association_edges(
    model_asst_id: str,
    instance_uuids,
    graph: GraphClient | None = None,
) -> list[dict[str, Any]]:
    """按 model_asst_id + uuid 批量查关联边，避免逐台查询及全图回退。"""
    uuids: list[str] = []
    seen: set[str] = set()
    for raw in instance_uuids or []:
        inst_uuid = _nonempty_text(raw)
        if not inst_uuid or inst_uuid in seen:
            continue
        seen.add(inst_uuid)
        uuids.append(inst_uuid)
    if not uuids:
        return []

    def _query(ag: GraphClient) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for batch in _chunks(uuids, ASSOCIATION_EDGE_BATCH_SIZE):
            for field in ("src_inst_uuid", "dst_inst_uuid"):
                found = (
                    ag.query_edge(
                        INSTANCE_ASSOCIATION,
                        [
                            {"field": "model_asst_id", "type": "str=", "value": model_asst_id},
                            {"field": field, "type": "str[]", "value": batch},
                        ],
                        return_entity=True,
                    )
                    or []
                )
                edges.extend(_flatten_association_edge(item) for item in found if isinstance(item, dict))
        return edges

    if graph is not None:
        return _query(graph)
    with GraphClient() as ag:
        return _query(ag)


def _peer_uuids_from_edges(
    edges: list[dict[str, Any]] | None,
    source_uuids: list[str],
    source_model_id: str,
    peer_model_id: str,
) -> list[str]:
    source_set = set(source_uuids)
    peers_by_source: dict[str, list[str]] = {uuid: [] for uuid in source_uuids}
    seen_by_source: dict[str, set[str]] = {uuid: set() for uuid in source_uuids}
    for edge in edges or []:
        if not isinstance(edge, dict):
            continue
        src_model = str(edge.get("src_model_id") or "")
        dst_model = str(edge.get("dst_model_id") or "")
        src_uuid = _nonempty_text(edge.get("src_inst_uuid"))
        dst_uuid = _nonempty_text(edge.get("dst_inst_uuid"))
        source_uuid = ""
        peer_uuid = ""
        if src_uuid in source_set and src_model == source_model_id and dst_model == peer_model_id:
            source_uuid, peer_uuid = src_uuid, dst_uuid
        elif dst_uuid in source_set and dst_model == source_model_id and src_model == peer_model_id:
            source_uuid, peer_uuid = dst_uuid, src_uuid
        if not source_uuid or not peer_uuid:
            continue
        seen_peers = seen_by_source.get(source_uuid)
        if seen_peers is None or peer_uuid in seen_peers:
            continue
        seen_peers.add(peer_uuid)
        peers_by_source[source_uuid].append(peer_uuid)

    ordered: list[str] = []
    seen: set[str] = set()
    for source_uuid in source_uuids:
        for peer_uuid in peers_by_source.get(source_uuid, []):
            if peer_uuid in seen:
                continue
            seen.add(peer_uuid)
            ordered.append(peer_uuid)
    return ordered


def _expand_with_loader(system_uuids, loader: AssociationLoader) -> list[str]:
    host_uuids: list[str] = []
    seen: set[str] = set()
    for raw in system_uuids or []:
        system_uuid = _nonempty_text(raw)
        if not system_uuid:
            continue
        app_uuids = _peer_uuids(
            loader("system", system_uuid),
            SYSTEM_CONTAINS_APPLICATION,
            "application",
        )
        for app_uuid in app_uuids:
            for host_uuid in _peer_uuids(
                loader("application", app_uuid),
                APPLICATION_RUN_HOST,
                "host",
            ):
                if host_uuid in seen:
                    continue
                seen.add(host_uuid)
                host_uuids.append(host_uuid)
    return host_uuids


def _expand_with_edges(system_uuids, edge_loader: EdgeLoader) -> list[str]:
    systems: list[str] = []
    seen: set[str] = set()
    for raw in system_uuids or []:
        system_uuid = _nonempty_text(raw)
        if not system_uuid or system_uuid in seen:
            continue
        seen.add(system_uuid)
        systems.append(system_uuid)
    if not systems:
        return []
    app_uuids = _peer_uuids_from_edges(
        edge_loader(SYSTEM_CONTAINS_APPLICATION, systems),
        systems,
        "system",
        "application",
    )
    if not app_uuids:
        return []
    return _peer_uuids_from_edges(
        edge_loader(APPLICATION_RUN_HOST, app_uuids),
        app_uuids,
        "application",
        "host",
    )


def expand_systems_to_host_uuids(
    system_uuids,
    association_loader: AssociationLoader | None = None,
    edge_loader: EdgeLoader | None = None,
) -> list[str]:
    """按 system_contains_application → application_run_host 展开已选应用系统下的主机 UUID。"""
    if association_loader is not None:
        return _expand_with_loader(system_uuids, association_loader)
    if edge_loader is not None:
        return _expand_with_edges(system_uuids, edge_loader)
    return _expand_with_edges(system_uuids, query_association_edges)
