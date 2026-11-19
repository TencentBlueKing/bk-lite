"""事故影响拓扑：只沿 run / connect 把种子和共用上一跳拼成一张图。"""

from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from apps.cmdb.constants.constants import ASSOCIATION_TYPE, INSTANCE, INSTANCE_ASSOCIATION, MODEL, MODEL_ASSOCIATION
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.language.service import SettingLanguage
from apps.cmdb.services.app_topo_layer import resolve_app_topo_layer
from apps.cmdb.services.ci_context_policy import APPLICATION_MODEL
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info

SEED_LIMIT = 200
RELATED_CANDIDATE_LIMIT = 300
MEMBER_LIMIT = 1000
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
    """基础图仍只按 run/connect 桥接。另外返回种子模型全部关系的一层实例和应用归属。"""
    prepared = _prepare_seeds(inst_uuids)
    seed_ids = [inst_uuid for inst_uuid, _valid in prepared]
    if len(prepared) > SEED_LIMIT:
        return _with_related(
            {
                "truncated": True,
                "nodes": [_seed_node(inst_uuid, None) for inst_uuid in seed_ids],
                "links": [],
            }
        )
    valid_ids = [inst_uuid for inst_uuid, valid in prepared if valid]
    if graph_factory is None:
        graph_factory = GraphClient
    viewer = can_view or _viewer(user_info or {})
    user_info = user_info or {}
    with graph_factory() as graph:
        entities = {item["inst_uuid"]: item for item in _load_instances(graph, valid_ids)}
        visible_ids = [inst_uuid for inst_uuid in valid_ids if viewer(entities.get(inst_uuid) or {})]
        raw_edges = _load_edges(graph, visible_ids) if visible_ids else []
        for item in _load_instances(graph, [inst_uuid for inst_uuid in _peer_ids(raw_edges, set(valid_ids)) if inst_uuid not in entities]):
            entities[item["inst_uuid"]] = item
        seed_models = sorted(
            {
                str((entities.get(inst_uuid) or {}).get("model_id") or "")
                for inst_uuid in visible_ids
                if (entities.get(inst_uuid) or {}).get("model_id")
            }
        )
        associations = _load_model_associations(graph, seed_models)
        allowed = {str(item.get("model_asst_id") or "") for item in associations if item.get("model_asst_id")}
        touching = []
        if visible_ids and allowed:
            touching = [edge for edge in _load_touching_edges(graph, visible_ids) if str(edge.get("model_asst_id") or "") in allowed]
            extra_peers = [inst_uuid for inst_uuid in _peer_ids(touching, set()) if inst_uuid not in entities]
            for item in _load_instances(graph, extra_peers):
                entities[item["inst_uuid"]] = item
        model_ids = sorted({str(item.get("model_id") or "") for item in entities.values() if item.get("model_id")})
        models = {str(item.get("model_id")): item for item in _load_models(graph, model_ids)}
    instances = {inst_uuid: _instance_record(entity, models, viewer) for inst_uuid, entity in entities.items()}
    base = assemble_incident_impact_topology(seed_ids, instances, _describe_edges(raw_edges, user_info))
    occupied = {str(node.get("inst_uuid") or "") for node in base["nodes"]}
    link_keys = {
        (str(link.get("src_inst_uuid") or ""), str(link.get("dst_inst_uuid") or ""), str(link.get("model_asst_id") or "")) for link in base["links"]
    }
    related = collect_related_layer(
        [inst_uuid for inst_uuid in visible_ids if _is_visible(instances.get(inst_uuid))],
        instances,
        _describe_edges(touching, user_info),
        allowed,
        occupied,
        link_keys,
    )
    context_status = "ok"
    contexts: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    try:
        contexts, members, instances = _attach_context(
            instances,
            [inst_uuid for inst_uuid in occupied if _is_visible(instances.get(inst_uuid))]
            + [node["inst_uuid"] for node in related["related_candidates"]],
            user_info,
            graph_factory,
            models,
            viewer,
        )
    except Exception as exc:
        context_status = "unavailable"
        contexts = []
        members = []
        logger.warning(
            "event=incident_impact_context_unavailable failed_stage=context error_type=%s",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
    return _with_related(
        base,
        related_truncated=related["related_truncated"],
        related_candidates=related["related_candidates"],
        related_links=related["related_links"],
        contexts=contexts,
        application_members=members,
        context_status=context_status,
    )


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
        "origin": "relation",
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


def _with_related(result: dict[str, Any], **extra: Any) -> dict[str, Any]:
    result.setdefault("related_truncated", False)
    result.setdefault("context_status", "ok")
    result.setdefault("related_candidates", [])
    result.setdefault("related_links", [])
    result.setdefault("contexts", [])
    result.setdefault("application_members", [])
    result.update(extra)
    for link in result.get("links") or []:
        if isinstance(link, dict):
            link.setdefault("origin", "relation")
    return result


def collect_related_layer(seed_uuids, instances, edges, allowed_model_asst_ids, occupied_ids, occupied_link_keys) -> dict[str, Any]:
    """种子向外一层。只保留模型关系目录里的实例边，不从对端再展开。"""
    allowed = {str(item or "") for item in allowed_model_asst_ids if item}
    seeds = set(seed_uuids)
    occupied = set(occupied_ids)
    seen = set(occupied_link_keys)
    candidates: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []
    for edge in edges or []:
        model_asst_id = str(edge.get("model_asst_id") or "")
        if model_asst_id not in allowed:
            continue
        src = str(edge.get("src_inst_uuid") or "")
        dst = str(edge.get("dst_inst_uuid") or "")
        if not src or not dst or src == dst:
            continue
        src_seed = src in seeds and _is_visible(instances.get(src))
        dst_seed = dst in seeds and _is_visible(instances.get(dst))
        if not src_seed and not dst_seed:
            continue
        key = (src, dst, model_asst_id)
        if key in seen:
            continue
        peer = ""
        if src_seed and dst_seed:
            peer = ""
        else:
            peer = dst if src_seed else src
            if not _is_visible(instances.get(peer)):
                continue
        seen.add(key)
        links.append(_link(edge, _parent_uuid(edge, instances)))
        if peer and peer not in occupied and peer not in candidates:
            candidates[peer] = instances[peer]
    ordered = sorted(candidates)
    truncated = len(ordered) > RELATED_CANDIDATE_LIMIT
    if truncated:
        kept = set(ordered[:RELATED_CANDIDATE_LIMIT])
        links = [
            link
            for link in links
            if all(
                end in occupied or end in seeds or end in kept for end in (str(link.get("src_inst_uuid") or ""), str(link.get("dst_inst_uuid") or ""))
            )
        ]
        ordered = ordered[:RELATED_CANDIDATE_LIMIT]
    nodes = []
    for inst_uuid in ordered:
        node = _seed_node(inst_uuid, candidates[inst_uuid])
        node["role"] = "related"
        nodes.append(node)
    return {"related_truncated": truncated, "related_candidates": nodes, "related_links": links}


def _load_model_associations(graph, model_ids: list[str]) -> list[dict[str, Any]]:
    if not model_ids:
        return []
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    allowed_models = set(model_ids)
    for field in ("src_model_id", "dst_model_id"):
        rows = graph.query_edge(
            MODEL_ASSOCIATION,
            [{"field": field, "type": "str[]", "value": model_ids}],
            return_entity=False,
        )
        for item in rows or []:
            edge = _edge_props(item)
            model_asst_id = str(edge.get("model_asst_id") or "")
            src_model = str(edge.get("src_model_id") or "")
            dst_model = str(edge.get("dst_model_id") or "")
            if not model_asst_id or model_asst_id in seen:
                continue
            if src_model not in allowed_models and dst_model not in allowed_models:
                continue
            seen.add(model_asst_id)
            found.append(edge)
    return found


def _load_touching_edges(graph, inst_uuids: list[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for field in ("src_inst_uuid", "dst_inst_uuid"):
        for batch in _chunks(inst_uuids, _EDGE_BATCH):
            rows = graph.query_edge(
                INSTANCE_ASSOCIATION,
                [{"field": field, "type": "str[]", "value": batch}],
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
                seen.add(key)
                found.append(edge)
    return found


def _edge_props(item: dict[str, Any] | None) -> dict[str, Any]:
    data = item if isinstance(item, dict) else {}
    edge = data.get("edge")
    if isinstance(edge, dict):
        return edge
    return data


def _attach_context(instances, object_ids, user_info, graph_factory, models, viewer):
    organization_ids = _organization_ids(user_info)
    if not organization_ids or not object_ids:
        return [], [], instances
    bundle = _load_context_bundle(organization_ids, object_ids, instances)
    missing = [inst_uuid for inst_uuid in bundle["instance_ids"] if inst_uuid not in instances]
    if missing:
        with graph_factory() as graph:
            loaded = _load_instances(graph, missing)
            extra_model_ids = sorted(
                {str(item.get("model_id") or "") for item in loaded if item.get("model_id") and str(item.get("model_id")) not in models}
            )
            for item in _load_models(graph, extra_model_ids):
                models[str(item.get("model_id"))] = item
            for entity in loaded:
                instances[str(entity.get("inst_uuid") or "")] = _instance_record(entity, models, viewer)
    return _assemble_context(object_ids, instances, bundle), bundle["members"], instances


def _assemble_context(object_ids, instances, bundle) -> list[dict[str, Any]]:
    rows_by_ci = bundle["by_ci"]
    system_by_root = bundle["system_by_root"]
    contexts = []
    for inst_uuid in object_ids:
        apps = []
        seen: set[str] = set()
        rows = list(rows_by_ci.get(inst_uuid) or [])
        record = instances.get(inst_uuid) or {}
        if record.get("model_id") == APPLICATION_MODEL and _is_visible(record):
            rows.append({"root_uuid": inst_uuid, "system_uuid": system_by_root.get(inst_uuid)})
        for row in rows:
            root = str((row or {}).get("root_uuid") or "")
            if not root or root in seen:
                continue
            root_inst = instances.get(root)
            if not _is_visible(root_inst):
                continue
            seen.add(root)
            system_uuid = str((row or {}).get("system_uuid") or system_by_root.get(root) or "")
            system = None
            system_inst = instances.get(system_uuid) if system_uuid else None
            if system_uuid and _is_visible(system_inst):
                system = _context_node(system_uuid, system_inst)
            apps.append({**_context_node(root, root_inst), "system": system})
        if apps:
            contexts.append({"ci_uuid": inst_uuid, "applications": apps})
    return contexts


def _context_node(inst_uuid: str, instance: dict[str, Any] | None) -> dict[str, Any]:
    node = _seed_node(inst_uuid, instance)
    node.pop("role", None)
    node.pop("found", None)
    return node


def _load_context_bundle(organization_ids, object_ids, instances) -> dict[str, Any]:
    from apps.cmdb.models.ci_context import CmdbCiContext
    from apps.cmdb.services.ci_context import lookup_ci_context
    from apps.cmdb.services.ci_context_policy import CONTEXT_APPLICATION

    by_ci = lookup_ci_context(organization_ids, inst_uuids=list(object_ids)) or {}
    roots = []
    seen_roots: set[str] = set()
    for rows in by_ci.values():
        for row in rows or []:
            root = str((row or {}).get("root_uuid") or "")
            if root and root not in seen_roots:
                seen_roots.add(root)
                roots.append(root)
    for inst_uuid in object_ids:
        record = instances.get(inst_uuid) or {}
        if record.get("model_id") == APPLICATION_MODEL and inst_uuid not in seen_roots:
            seen_roots.add(inst_uuid)
            roots.append(inst_uuid)
    from apps.core.utils.viewset_utils import build_json_membership_query

    member_rows = []
    truncated = False
    if roots:
        member_base = CmdbCiContext.objects.filter(context=CONTEXT_APPLICATION, root_uuid__in=roots)
        org_match = build_json_membership_query(member_base, "organization", organization_ids)
        fetched = list(
            member_base.filter(org_match).order_by("root_uuid", "ci_uuid").values("root_uuid", "ci_uuid", "system_uuid")[: MEMBER_LIMIT + 1]
        )
        truncated = len(fetched) > MEMBER_LIMIT
        member_rows = fetched[:MEMBER_LIMIT]
    grouped: dict[str, list[str]] = {}
    system_by_root: dict[str, str] = {}
    for row in member_rows:
        root = str(row.get("root_uuid") or "")
        ci_uuid = str(row.get("ci_uuid") or "")
        if root and ci_uuid:
            grouped.setdefault(root, []).append(ci_uuid)
        system_uuid = str(row.get("system_uuid") or "")
        if root and system_uuid and root not in system_by_root:
            system_by_root[root] = system_uuid
    for rows in by_ci.values():
        for row in rows or []:
            root = str((row or {}).get("root_uuid") or "")
            system_uuid = str((row or {}).get("system_uuid") or "")
            if root and system_uuid and root not in system_by_root:
                system_by_root[root] = system_uuid
    members = [
        {
            "inst_uuid": root,
            "member_uuids": grouped.get(root, []),
            "member_truncated": truncated,
        }
        for root in roots
    ]
    instance_ids = []
    seen_ids: set[str] = set()
    for root in roots:
        if root not in seen_ids:
            seen_ids.add(root)
            instance_ids.append(root)
        system_uuid = system_by_root.get(root) or ""
        if system_uuid and system_uuid not in seen_ids:
            seen_ids.add(system_uuid)
            instance_ids.append(system_uuid)
    return {"by_ci": by_ci, "members": members, "system_by_root": system_by_root, "instance_ids": instance_ids}


def _organization_ids(user_info: dict[str, Any]) -> list[int]:
    if not isinstance(user_info, dict):
        return []
    team = user_info.get("team")
    user = user_info.get("user")
    if team in (None, "") or not user:
        return []
    try:
        current_team = int(team)
    except (TypeError, ValueError):
        return []
    from apps.cmdb.nats.nats import _get_authorized_team_ids, _normalize_permission_user
    from apps.system_mgmt.models import User

    user_obj = _normalize_permission_user(user, domain=user_info.get("domain"))
    filters = {"username": getattr(user_obj, "username", "") or ""}
    if getattr(user_obj, "domain", None):
        filters["domain"] = user_obj.domain
    if not filters["username"]:
        return []
    real_user = User.objects.filter(**filters).first()
    if real_user is None:
        return []
    raw = _get_authorized_team_ids(
        real_user,
        current_team,
        include_children=bool(user_info.get("include_children")),
    )
    found = []
    for item in raw or []:
        try:
            found.append(int(item))
        except (TypeError, ValueError):
            continue
    return found
