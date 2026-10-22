"""资产总览取数：分类实例合计，以及云区域主机经关联和标签补充后的模型计数。"""

from __future__ import annotations

from typing import Any

from apps.cmdb.constants.constants import INSTANCE, INSTANCE_ASSOCIATION, MODEL_ASSOCIATION
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.application_system import query_association_edges
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.model_visibility import BusinessModelVisibility

HOST_MODEL_ID = "host"
_EDGE_BATCH_SIZE = 200


class AssetOverviewQueryError(ValueError):
    """配置无法执行时抛出。空结果不能用来表示配置错误。"""


def normalize_text_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    raw_items = value if isinstance(value, (list, tuple)) else [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item).strip() if item is not None else ""
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def normalize_cloud_region_ids(value: Any) -> list[int]:
    if value is None or value == "":
        raise AssetOverviewQueryError("云区域不能为空")
    raw_items = value if isinstance(value, (list, tuple)) else [value]
    result: list[int] = []
    seen: set[int] = set()
    for item in raw_items:
        if isinstance(item, bool) or item is None or item == "":
            raise AssetOverviewQueryError("云区域 ID 无效")
        if isinstance(item, int):
            cloud_id = item
        elif isinstance(item, str) and item.strip().lstrip("-").isdigit():
            cloud_id = int(item.strip())
        else:
            raise AssetOverviewQueryError("云区域 ID 无效")
        if cloud_id in seen:
            continue
        seen.add(cloud_id)
        result.append(cloud_id)
    if not result:
        raise AssetOverviewQueryError("云区域不能为空")
    return result


def resolve_supplement_tag(tag_key: Any, tag_value: Any) -> str | None:
    key = "" if tag_key is None else str(tag_key).strip()
    value = "" if tag_value is None else str(tag_value).strip()
    if not key or not value:
        return None
    return f"{key}:{value}"


def peer_model_id(association: dict[str, Any], host_model_id: str = HOST_MODEL_ID) -> str:
    src = str(association.get("src_model_id") or "")
    dst = str(association.get("dst_model_id") or "")
    if src == host_model_id and dst and dst != host_model_id:
        return dst
    if dst == host_model_id and src and src != host_model_id:
        return src
    model_asst_id = association.get("model_asst_id") or ""
    raise AssetOverviewQueryError(f"模型关联必须连接主机和其他模型: {model_asst_id}")


def _chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _instance_uuid(instance: dict[str, Any]) -> str:
    return str(instance.get("inst_uuid") or "").strip()


def assemble_resource_rows(
    *,
    host_uuids: list[str],
    ordered_peer_models: list[str],
    peers_by_model: dict[str, set[str]],
    tag_instances: list[tuple[str, str]],
    host_associated_uuids: set[str],
    model_names: dict[str, str],
    host_model_id: str = HOST_MODEL_ID,
) -> list[dict[str, Any]]:
    """按关联选择顺序、标签补充模型、主机的顺序计数。同一实例只计入第一次出现的模型。"""
    hosts: list[str] = []
    seen_hosts: set[str] = set()
    for raw in host_uuids:
        inst_uuid = str(raw or "").strip()
        if not inst_uuid or inst_uuid in seen_hosts:
            continue
        seen_hosts.add(inst_uuid)
        hosts.append(inst_uuid)

    assigned: dict[str, str] = {inst_uuid: host_model_id for inst_uuid in hosts}
    counted: dict[str, set[str]] = {model_id: set() for model_id in ordered_peer_models}
    for model_id in ordered_peer_models:
        for inst_uuid in peers_by_model.get(model_id, set()):
            if not inst_uuid or inst_uuid in assigned:
                continue
            assigned[inst_uuid] = model_id
            counted[model_id].add(inst_uuid)

    tag_only: dict[str, set[str]] = {}
    for inst_uuid, model_id in tag_instances:
        inst_uuid = str(inst_uuid or "").strip()
        model_id = str(model_id or "").strip()
        if not inst_uuid or not model_id or model_id == host_model_id:
            continue
        if inst_uuid in host_associated_uuids or inst_uuid in assigned:
            continue
        assigned[inst_uuid] = model_id
        if model_id in counted:
            counted[model_id].add(inst_uuid)
            continue
        tag_only.setdefault(model_id, set()).add(inst_uuid)

    rows: list[dict[str, Any]] = []
    for model_id in ordered_peer_models:
        rows.append(_count_row(model_id, len(counted[model_id]), model_names))
    for model_id in sorted(tag_only, key=lambda item: (model_names.get(item) or item, item)):
        rows.append(_count_row(model_id, len(tag_only[model_id]), model_names))
    rows.append(_count_row(host_model_id, len(hosts), model_names))
    return rows


def _count_row(model_id: str, count: int, model_names: dict[str, str]) -> dict[str, Any]:
    model_name = model_names.get(model_id) or model_id
    return {
        "model_id": model_id,
        "model_name": model_name,
        "label": model_name,
        "value": count,
    }


def build_classification_count_items(
    classification_ids: list[str],
    classifications: list[dict[str, Any]],
    models: list[dict[str, Any]],
    model_counts: dict[str, int],
) -> list[dict[str, Any]]:
    names = {
        str(item.get("classification_id")): item.get("classification_name") or str(item.get("classification_id"))
        for item in classifications
        if item.get("classification_id")
    }
    missing = [item for item in classification_ids if item not in names]
    if missing:
        raise AssetOverviewQueryError(f"分类不存在或不可见: {', '.join(missing)}")

    totals = {item: 0 for item in classification_ids}
    for model in models:
        classification_id = str(model.get("classification_id") or "")
        if classification_id not in totals:
            continue
        totals[classification_id] += int(model_counts.get(str(model.get("model_id")), 0) or 0)

    return [
        {
            "classification_id": classification_id,
            "classification_name": names[classification_id],
            "label": names[classification_id],
            "value": totals[classification_id],
        }
        for classification_id in classification_ids
    ]


def build_association_option_items(associations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    seen: set[str] = set()
    for association in associations:
        model_asst_id = str(association.get("model_asst_id") or "").strip()
        if not model_asst_id or model_asst_id in seen:
            continue
        seen.add(model_asst_id)
        relation = str(association.get("asst_name") or association.get("asst_id") or "").strip()
        src_name = association.get("src_model_name") or association.get("src_model_id") or ""
        dst_name = association.get("dst_model_name") or association.get("dst_model_id") or ""
        items.append(
            {
                "model_asst_id": model_asst_id,
                "label": f"{src_name} —{relation}— {dst_name}",
                "src_model_id": association.get("src_model_id") or "",
                "dst_model_id": association.get("dst_model_id") or "",
                "asst_name": relation,
            }
        )
    items.sort(key=lambda item: (item["label"], item["model_asst_id"]))
    return items


def _query_instances(graph: GraphClient, params: list[dict[str, Any]], permission_map: dict) -> list[dict[str, Any]]:
    rows, _ = graph.query_entity(
        INSTANCE,
        params,
        format_permission_dict=InstanceManage._build_format_permission_dict(permission_map),
    )
    return [row for row in rows or [] if isinstance(row, dict)]


def _uuids_linked_to_host(graph: GraphClient, inst_uuids: list[str], host_model_id: str = HOST_MODEL_ID) -> set[str]:
    linked: set[str] = set()
    pending = [inst_uuid for inst_uuid in inst_uuids if inst_uuid]
    if not pending:
        return linked
    for batch in _chunks(pending, _EDGE_BATCH_SIZE):
        for field, other_model_field, self_field in (
            ("src_inst_uuid", "dst_model_id", "src_inst_uuid"),
            ("dst_inst_uuid", "src_model_id", "dst_inst_uuid"),
        ):
            found = (
                graph.query_edge(
                    INSTANCE_ASSOCIATION,
                    [{"field": field, "type": "str[]", "value": batch}],
                    return_entity=True,
                )
                or []
            )
            for item in found:
                edge = _edge_with_models(item)
                if edge.get(other_model_field) == host_model_id and edge.get(self_field):
                    linked.add(str(edge[self_field]))
    return linked


def _edge_with_models(item: dict[str, Any]) -> dict[str, Any]:
    if "src_inst_uuid" in item or "dst_inst_uuid" in item:
        edge = dict(item)
    else:
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


def _peer_uuids(edges: list[dict[str, Any]], host_uuids: set[str], peer_model_id_value: str, host_model_id: str) -> list[str]:
    peers: list[str] = []
    seen: set[str] = set()
    for edge in edges:
        src_uuid = str(edge.get("src_inst_uuid") or "")
        dst_uuid = str(edge.get("dst_inst_uuid") or "")
        src_model = str(edge.get("src_model_id") or "")
        dst_model = str(edge.get("dst_model_id") or "")
        peer = ""
        if src_uuid in host_uuids and dst_uuid not in host_uuids:
            if (not src_model or src_model == host_model_id) and (not dst_model or dst_model == peer_model_id_value):
                peer = dst_uuid
        elif dst_uuid in host_uuids and src_uuid not in host_uuids:
            if (not dst_model or dst_model == host_model_id) and (not src_model or src_model == peer_model_id_value):
                peer = src_uuid
        if not peer or peer in seen or peer in host_uuids:
            continue
        seen.add(peer)
        peers.append(peer)
    return peers


def query_cloud_region_resource_counts(
    cloud_region_ids: Any,
    model_asst_ids: Any,
    supplement_tag_key: Any = None,
    supplement_tag_value: Any = None,
    *,
    instance_permission_map: dict,
    visible_models: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cloud_ids = normalize_cloud_region_ids(cloud_region_ids)
    association_ids = normalize_text_list(model_asst_ids)
    if not association_ids:
        raise AssetOverviewQueryError("模型关联不能为空")
    tag = resolve_supplement_tag(supplement_tag_key, supplement_tag_value)

    model_names = {
        str(model.get("model_id")): model.get("model_name") or str(model.get("model_id")) for model in visible_models if model.get("model_id")
    }
    if HOST_MODEL_ID not in model_names:
        raise AssetOverviewQueryError("主机模型不可见")

    associations = []
    ordered_peer_models: list[str] = []
    for model_asst_id in association_ids:
        association = ModelManage.model_association_info_search(model_asst_id)
        if not association:
            raise AssetOverviewQueryError(f"模型关联不存在: {model_asst_id}")
        association = dict(association)
        association["model_asst_id"] = model_asst_id
        target_model_id = peer_model_id(association)
        if target_model_id not in model_names:
            raise AssetOverviewQueryError(f"目标模型不可见: {target_model_id}")
        associations.append((model_asst_id, target_model_id))
        if target_model_id not in ordered_peer_models:
            ordered_peer_models.append(target_model_id)

    with GraphClient() as graph:
        hosts = _query_instances(
            graph,
            [
                {"field": "model_id", "type": "str=", "value": HOST_MODEL_ID},
                {"field": "cloud", "type": "int[]", "value": cloud_ids},
            ],
            instance_permission_map,
        )
        host_uuids = [_instance_uuid(item) for item in hosts if _instance_uuid(item)]
        host_uuid_set = set(host_uuids)
        peers_by_model: dict[str, set[str]] = {model_id: set() for model_id in ordered_peer_models}
        if host_uuids:
            for model_asst_id, target_model_id in associations:
                edges = query_association_edges(model_asst_id, host_uuids, graph=graph)
                for inst_uuid in _peer_uuids(edges, host_uuid_set, target_model_id, HOST_MODEL_ID):
                    peers_by_model[target_model_id].add(inst_uuid)

        visible_peers: dict[str, set[str]] = {model_id: set() for model_id in ordered_peer_models}
        for model_id, peer_uuids in peers_by_model.items():
            visible_ids: set[str] = set()
            for batch in _chunks(sorted(peer_uuids), _EDGE_BATCH_SIZE):
                visible = _query_instances(
                    graph,
                    [
                        {"field": "model_id", "type": "str=", "value": model_id},
                        {"field": "inst_uuid", "type": "str[]", "value": batch},
                    ],
                    instance_permission_map,
                )
                visible_ids.update(_instance_uuid(item) for item in visible if _instance_uuid(item))
            visible_peers[model_id] = visible_ids

        tag_instances: list[tuple[str, str]] = []
        host_associated: set[str] = set()
        if tag:
            tagged = _query_instances(
                graph,
                [{"field": "tag", "type": "list[]", "value": [tag]}],
                instance_permission_map,
            )
            candidates = [(_instance_uuid(item), str(item.get("model_id") or "")) for item in tagged if _instance_uuid(item)]
            candidate_uuids = [
                inst_uuid for inst_uuid, model_id in candidates if model_id and model_id != HOST_MODEL_ID and inst_uuid not in host_uuid_set
            ]
            host_associated = _uuids_linked_to_host(graph, candidate_uuids)
            tag_instances = [(inst_uuid, model_id) for inst_uuid, model_id in candidates if model_id in model_names]

    return assemble_resource_rows(
        host_uuids=host_uuids,
        ordered_peer_models=ordered_peer_models,
        peers_by_model=visible_peers,
        tag_instances=tag_instances,
        host_associated_uuids=host_associated,
        model_names=model_names,
    )


def select_model_endpoint_associations(associations: list[dict[str, Any]], model_id: Any) -> list[dict[str, Any]]:
    anchor = str(model_id).strip() if model_id is not None else ""
    if not anchor:
        raise AssetOverviewQueryError("模型不能为空")
    selected = []
    for association in associations:
        src = str(association.get("src_model_id") or "")
        dst = str(association.get("dst_model_id") or "")
        if (src == anchor) == (dst == anchor):
            continue
        selected.append(association)
    return selected


def list_model_association_options(language: str, model_id: Any) -> list[dict[str, Any]]:
    with GraphClient() as graph:
        edges = graph.query_edge(MODEL_ASSOCIATION, []) or []
    visible = BusinessModelVisibility.filter_associations(edges, language=language)
    return build_association_option_items(select_model_endpoint_associations(visible, model_id))
