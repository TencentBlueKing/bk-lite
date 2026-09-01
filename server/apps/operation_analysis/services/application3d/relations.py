from __future__ import annotations

from typing import Any, Iterable

from apps.cmdb.constants.constants import INSTANCE_ASSOCIATION
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.operation_analysis.services.application3d.constants import (
    APPLICATION3D_RELATION_BATCH_SIZE,
    APPLICATION_RUN_HOST_ASST,
    SYSTEM_CONTAINS_APPLICATION_ASST,
)


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _normalize_association_row(item: dict[str, Any]) -> dict[str, Any]:
    """
    GraphClient.query_edge(return_entity=True) returns
    ``{edge, src, dst}``; flatten to edge props and fill missing endpoint
    model/uuid from entity nodes (stock edges may omit model_id on the edge).
    Flat edge dicts (tests / return_entity=False) pass through.
    """
    if "edge" not in item and ("src_inst_uuid" in item or "dst_inst_uuid" in item):
        return item
    edge = dict(item.get("edge") or {})
    src = item.get("src") or {}
    dst = item.get("dst") or {}
    if not edge.get("src_inst_uuid") and src.get("inst_uuid"):
        edge["src_inst_uuid"] = src.get("inst_uuid")
    if not edge.get("dst_inst_uuid") and dst.get("inst_uuid"):
        edge["dst_inst_uuid"] = dst.get("inst_uuid")
    if not edge.get("src_model_id") and src.get("model_id"):
        edge["src_model_id"] = src.get("model_id")
    if not edge.get("dst_model_id") and dst.get("model_id"):
        edge["dst_model_id"] = dst.get("model_id")
    return edge


def _query_edges_by_asst(
    *,
    model_asst_id: str,
    instance_uuids: list[str],
) -> list[dict[str, Any]]:
    if not instance_uuids:
        return []
    edges: list[dict[str, Any]] = []
    with GraphClient() as graph:
        for batch in _chunks(instance_uuids, APPLICATION3D_RELATION_BATCH_SIZE):
            # Entity may sit on src or dst; query both orientations and dedupe.
            for field in ("src_inst_uuid", "dst_inst_uuid"):
                found = (
                    graph.query_edge(
                        INSTANCE_ASSOCIATION,
                        [
                            {"field": "model_asst_id", "type": "str=", "value": model_asst_id},
                            {"field": field, "type": "str[]", "value": batch},
                        ],
                        return_entity=True,
                    )
                    or []
                )
                edges.extend(_normalize_association_row(item) for item in found)
    return edges


def project_application_hosts(
    application_uuids: list[str],
) -> dict[str, list[str]]:
    """
    Exact application_run_host projection: app_uuid -> unique host uuids.

    Wrong-peer edges under this asst are omitted from the host list. Callers
    must still aggregate remaining legitimate hosts; an empty host union is
    unknown/no_host, not whole-system unavailable.
    """
    result: dict[str, list[str]] = {uuid: [] for uuid in application_uuids}
    seen: dict[str, set[str]] = {uuid: set() for uuid in application_uuids}
    app_set = set(application_uuids)

    for edge in _query_edges_by_asst(
        model_asst_id=APPLICATION_RUN_HOST_ASST,
        instance_uuids=application_uuids,
    ):
        src_model = str(edge.get("src_model_id") or "")
        dst_model = str(edge.get("dst_model_id") or "")
        src_uuid = str(edge.get("src_inst_uuid") or "")
        dst_uuid = str(edge.get("dst_inst_uuid") or "")

        if src_uuid in app_set and src_model == "application":
            if dst_model != "host":
                continue
            if dst_uuid and dst_uuid not in seen[src_uuid]:
                seen[src_uuid].add(dst_uuid)
                result[src_uuid].append(dst_uuid)
            continue

        if dst_uuid in app_set and dst_model == "application":
            if src_model != "host":
                continue
            if src_uuid and src_uuid not in seen[dst_uuid]:
                seen[dst_uuid].add(src_uuid)
                result[dst_uuid].append(src_uuid)
            continue

    return result


def project_system_applications(
    system_uuids: list[str],
) -> dict[str, list[str]]:
    """Exact system_contains_application: system_uuid -> unique application uuids."""
    result: dict[str, list[str]] = {uuid: [] for uuid in system_uuids}
    seen: dict[str, set[str]] = {uuid: set() for uuid in system_uuids}
    system_set = set(system_uuids)

    for edge in _query_edges_by_asst(
        model_asst_id=SYSTEM_CONTAINS_APPLICATION_ASST,
        instance_uuids=system_uuids,
    ):
        src_model = str(edge.get("src_model_id") or "")
        dst_model = str(edge.get("dst_model_id") or "")
        src_uuid = str(edge.get("src_inst_uuid") or "")
        dst_uuid = str(edge.get("dst_inst_uuid") or "")

        if src_uuid in system_set and src_model == "system" and dst_model == "application" and dst_uuid:
            if dst_uuid not in seen[src_uuid]:
                seen[src_uuid].add(dst_uuid)
                result[src_uuid].append(dst_uuid)
            continue

        if dst_uuid in system_set and dst_model == "system" and src_model == "application" and src_uuid:
            if src_uuid not in seen[dst_uuid]:
                seen[dst_uuid].add(src_uuid)
                result[dst_uuid].append(src_uuid)

    return result
