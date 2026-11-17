"""事故影响拓扑：只沿 run / connect 把种子和共用上一跳拼成一张图。"""

from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from apps.cmdb.constants.constants import ASSOCIATION_TYPE, INSTANCE, INSTANCE_ASSOCIATION, MODEL
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.language.service import SettingLanguage
from apps.cmdb.services.app_topo_layer import resolve_app_topo_layer

SEED_LIMIT = 200
IMPACT_ASST_IDS = frozenset({"run", "connect"})
# 数字越小越靠上，也越适合当上一跳。基础设施和不分类不参与这场比较。
_LAYER_RANK = {"system": 0, "service": 1, "host": 2, "appService": 3}
_INFRASTRUCTURE = "infrastructure"
_EDGE_BATCH = 200
_ASST_NAME = {item["asst_id"]: item["asst_name"] for item in ASSOCIATION_TYPE}

GraphFactory = Callable[[], Any]
CanView = Callable[[dict[str, Any]], bool]


def assemble_incident_impact_topology(
    seed_uuids: list[str],
    instances: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """按已给定的实例和边组装节点。超过上限时不使用边。"""
    seeds = _unique(seed_uuids)
    if len(seeds) > SEED_LIMIT:
        return {
            "truncated": True,
            "nodes": [_seed_node(inst_uuid, None) for inst_uuid in seeds],
            "links": [],
        }

    seed_ids = set(seeds)
    usable = {inst_uuid for inst_uuid in seeds if _is_visible(instances.get(inst_uuid))}
    direct: list[dict[str, Any]] = []
    bridge_edges: dict[str, list[dict[str, Any]]] = {}
    seen_edges: set[tuple[str, str, str]] = set()

    for edge in edges:
        asst_id = str(edge.get("asst_id") or "")
        if asst_id not in IMPACT_ASST_IDS:
            continue
        src = str(edge.get("src_inst_uuid") or "")
        dst = str(edge.get("dst_inst_uuid") or "")
        model_asst_id = str(edge.get("model_asst_id") or "")
        edge_key = (src, dst, model_asst_id or asst_id)
        if not src or not dst or edge_key in seen_edges:
            continue
        src_usable = src in usable
        dst_usable = dst in usable
        if src_usable and dst_usable:
            seen_edges.add(edge_key)
            direct.append(_link(edge, _parent_uuid(edge, instances)))
            continue
        if src_usable == dst_usable:
            continue
        other_uuid = dst if src_usable else src
        other = instances.get(other_uuid)
        if other_uuid in seed_ids or not _is_visible(other) or other.get("layer") == _INFRASTRUCTURE:
            continue
        parent_uuid = _parent_uuid(edge, instances)
        if parent_uuid != other_uuid:
            continue
        seen_edges.add(edge_key)
        bridge_edges.setdefault(other_uuid, []).append(edge)

    links = list(direct)
    bridge_ids: list[str] = []
    for parent_uuid, parent_edges in bridge_edges.items():
        children: list[str] = []
        for edge in parent_edges:
            child = _other_end(edge, parent_uuid)
            if child in usable and child not in children:
                children.append(child)
        if len(children) < 2:
            continue
        bridge_ids.append(parent_uuid)
        child_set = set(children)
        for edge in parent_edges:
            if _other_end(edge, parent_uuid) in child_set:
                links.append(_link(edge, parent_uuid))

    nodes = [_seed_node(inst_uuid, instances.get(inst_uuid)) for inst_uuid in seeds]
    nodes.extend(_bridge_node(inst_uuid, instances[inst_uuid]) for inst_uuid in bridge_ids)
    return {"truncated": False, "nodes": nodes, "links": links}


def query_incident_impact_topology(
    inst_uuids,
    user_info=None,
    *,
    graph_factory: GraphFactory | None = None,
    can_view: CanView | None = None,
) -> dict[str, Any]:
    """加载种子、run/connect 边和模型层级，再交给组装函数。"""
    seeds = _prepare_seeds(inst_uuids)
    if len(seeds) > SEED_LIMIT:
        return {
            "truncated": True,
            "nodes": [_seed_node(inst_uuid, None) for inst_uuid in seeds],
            "links": [],
        }
    valid_ids = [inst_uuid for inst_uuid, valid in seeds if valid]
    if graph_factory is None:
        graph_factory = GraphClient
    viewer = can_view or _viewer(user_info or {})
    with graph_factory() as graph:
        entities = {item["inst_uuid"]: item for item in _load_instances(graph, valid_ids)}
        visible_ids = [inst_uuid for inst_uuid in valid_ids if viewer(entities.get(inst_uuid) or {})]
        raw_edges = _load_edges(graph, visible_ids) if visible_ids else []
        peer_ids = [inst_uuid for inst_uuid in _peer_ids(raw_edges, set(valid_ids)) if inst_uuid not in entities]
        for item in _load_instances(graph, peer_ids):
            entities[item["inst_uuid"]] = item
        model_ids = sorted({str(item.get("model_id") or "") for item in entities.values() if item.get("model_id")})
        models = {str(item.get("model_id")): item for item in _load_models(graph, model_ids)}
    instances = {inst_uuid: _instance_record(entity, models, viewer) for inst_uuid, entity in entities.items()}
    return assemble_incident_impact_topology([inst_uuid for inst_uuid, _valid in seeds], instances, _describe_edges(raw_edges, user_info or {}))


def _prepare_seeds(inst_uuids) -> list[tuple[str, bool]]:
    seeds: list[tuple[str, bool]] = []
    seen: set[str] = set()
    for value in inst_uuids or []:
        text = str(value or "").strip()
        if not text:
            continue
        key, valid = _seed_key(text)
        if key in seen:
            continue
        seen.add(key)
        seeds.append((key, valid))
    return seeds


def _seed_key(text: str) -> tuple[str, bool]:
    try:
        parsed = UUID(text)
    except (TypeError, ValueError, AttributeError):
        return text, False
    if parsed.version != 4:
        return text, False
    return str(parsed), True


def _unique(seed_uuids: list[str]) -> list[str]:
    seeds: list[str] = []
    seen: set[str] = set()
    for value in seed_uuids or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        seeds.append(text)
    return seeds


def _is_visible(instance: dict[str, Any] | None) -> bool:
    return bool(instance and instance.get("visible"))


def _parent_uuid(edge: dict[str, Any], instances: dict[str, dict[str, Any]]) -> str:
    src = str(edge.get("src_inst_uuid") or "")
    dst = str(edge.get("dst_inst_uuid") or "")
    src_rank = _LAYER_RANK.get(str((instances.get(src) or {}).get("layer") or ""))
    dst_rank = _LAYER_RANK.get(str((instances.get(dst) or {}).get("layer") or ""))
    if src_rank is not None and dst_rank is not None and src_rank != dst_rank:
        return src if src_rank < dst_rank else dst
    asst_id = str(edge.get("asst_id") or "")
    if asst_id == "run":
        return dst
    if asst_id == "connect":
        return src
    return ""


def _other_end(edge: dict[str, Any], inst_uuid: str) -> str:
    src = str(edge.get("src_inst_uuid") or "")
    dst = str(edge.get("dst_inst_uuid") or "")
    return dst if src == inst_uuid else src


def _link(edge: dict[str, Any], parent_uuid: str) -> dict[str, Any]:
    return {
        "src_inst_uuid": str(edge.get("src_inst_uuid") or ""),
        "dst_inst_uuid": str(edge.get("dst_inst_uuid") or ""),
        "model_asst_id": str(edge.get("model_asst_id") or ""),
        "asst_id": str(edge.get("asst_id") or ""),
        "asst_name": str(edge.get("asst_name") or ""),
        "parent_inst_uuid": parent_uuid,
    }


def _seed_node(inst_uuid: str, instance: dict[str, Any] | None) -> dict[str, Any]:
    visible = _is_visible(instance)
    source = instance if visible else {}
    return {
        "inst_uuid": inst_uuid,
        "inst_name": str((source or {}).get("inst_name") or ""),
        "model_id": str((source or {}).get("model_id") or ""),
        "model_name": str((source or {}).get("model_name") or ""),
        "layer": str((source or {}).get("layer") or "none"),
        "role": "seed",
        "found": visible,
    }


def _bridge_node(inst_uuid: str, instance: dict[str, Any]) -> dict[str, Any]:
    node = _seed_node(inst_uuid, instance)
    node["role"] = "bridge"
    return node


def _viewer(user_info: dict[str, Any]) -> CanView:
    cache: dict[str, Any] = {}

    def can_view(entity: dict[str, Any]) -> bool:
        if not entity or not entity.get("inst_uuid"):
            return False
        model_id = str(entity.get("model_id") or "")
        if model_id not in cache:
            cache[model_id] = _permission_map(user_info, model_id)
        permission_map = cache[model_id]
        if not permission_map:
            return False
        from apps.cmdb.nats.nats import _normalize_permission_user
        from apps.cmdb.services.instance import InstanceManage

        user = _normalize_permission_user(user_info.get("user"), domain=user_info.get("domain"))
        return InstanceManage._has_topology_view_permission(entity, permission_map, user=user)

    return can_view


def _permission_map(user_info: dict[str, Any], model_id: str):
    from apps.cmdb.nats.nats import _build_nats_permission_map

    return _build_nats_permission_map(user_info, model_id=model_id)


def _load_instances(graph, inst_uuids: list[str]) -> list[dict[str, Any]]:
    if not inst_uuids:
        return []
    rows, _count = graph.query_entity(INSTANCE, [{"field": "inst_uuid", "type": "str[]", "value": inst_uuids}])
    return [item for item in rows or [] if isinstance(item, dict)]


def _load_models(graph, model_ids: list[str]) -> list[dict[str, Any]]:
    if not model_ids:
        return []
    rows, _count = graph.query_entity(MODEL, [{"field": "model_id", "type": "str[]", "value": model_ids}])
    return [item for item in rows or [] if isinstance(item, dict)]


def _load_edges(graph, inst_uuids: list[str]) -> list[dict[str, Any]]:
    if not inst_uuids:
        return []
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for asst_id in ("run", "connect"):
        for field in ("src_inst_uuid", "dst_inst_uuid"):
            for batch in _chunks(inst_uuids, _EDGE_BATCH):
                rows = graph.query_edge(
                    INSTANCE_ASSOCIATION,
                    [
                        {"field": "asst_id", "type": "str=", "value": asst_id},
                        {"field": field, "type": "str[]", "value": batch},
                    ],
                    return_entity=True,
                )
                for item in rows or []:
                    edge = _flatten_edge(item)
                    key = (
                        str(edge.get("src_inst_uuid") or ""),
                        str(edge.get("dst_inst_uuid") or ""),
                        str(edge.get("model_asst_id") or ""),
                    )
                    if not key[0] or not key[1] or key in seen:
                        continue
                    if str(edge.get("asst_id") or "") not in IMPACT_ASST_IDS:
                        continue
                    seen.add(key)
                    found.append(edge)
    return found


def _flatten_edge(item: dict[str, Any] | None) -> dict[str, Any]:
    data = item if isinstance(item, dict) else {}
    if "edge" not in data and ("src_inst_uuid" in data or "dst_inst_uuid" in data):
        return dict(data)
    edge = dict(data.get("edge") or {})
    src = data.get("src") or {}
    dst = data.get("dst") or {}
    edge.setdefault("src_inst_uuid", src.get("inst_uuid"))
    edge.setdefault("dst_inst_uuid", dst.get("inst_uuid"))
    edge.setdefault("src_model_id", src.get("model_id"))
    edge.setdefault("dst_model_id", dst.get("model_id"))
    return edge


def _peer_ids(edges: list[dict[str, Any]], seed_ids: set[str]) -> list[str]:
    peers: list[str] = []
    seen: set[str] = set()
    for edge in edges:
        for field in ("src_inst_uuid", "dst_inst_uuid"):
            inst_uuid = str(edge.get(field) or "")
            if not inst_uuid or inst_uuid in seed_ids or inst_uuid in seen:
                continue
            seen.add(inst_uuid)
            peers.append(inst_uuid)
    return peers


def _instance_record(entity: dict[str, Any], models: dict[str, dict[str, Any]], viewer: CanView) -> dict[str, Any]:
    inst_uuid = str(entity.get("inst_uuid") or "")
    visible = viewer(entity)
    if not visible:
        return {
            "inst_uuid": inst_uuid,
            "inst_name": "",
            "model_id": "",
            "model_name": "",
            "layer": "none",
            "visible": False,
        }
    model_id = str(entity.get("model_id") or "")
    model = models.get(model_id) or {}
    layer = resolve_app_topo_layer(model_id, model.get("app_topo_layer"), str(model.get("classification_id") or ""))
    return {
        "inst_uuid": inst_uuid,
        "inst_name": "" if entity.get("inst_name") is None else str(entity.get("inst_name")),
        "model_id": model_id,
        "model_name": str(model.get("model_name") or model_id),
        "layer": layer,
        "visible": True,
    }


def _describe_edges(edges: list[dict[str, Any]], user_info: dict[str, Any]) -> list[dict[str, Any]]:
    language = SettingLanguage(str(user_info.get("locale") or "zh-Hans"))
    described = []
    for edge in edges:
        asst_id = str(edge.get("asst_id") or "")
        translated = language.get_val("ASSOCIATION_TYPE", asst_id) if asst_id else ""
        described.append({**edge, "asst_name": translated or _ASST_NAME.get(asst_id, asst_id)})
    return described


def _chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]
