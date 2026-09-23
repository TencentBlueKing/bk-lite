"""CMDB 服务树：系统 → 应用 → 主机。

组织脊柱是树；主机只挂应用，且可多归属。系统与应用之间可以有用户自建的
自定义中间模型，但不预置业务分组。旧的两跳展开仍由
`application_system.expand_systems_to_host_uuids` 负责，本模块不得改它。
"""

from __future__ import annotations

from typing import Any, Callable, Iterable
from uuid import uuid4

from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.application_system import (
    APPLICATION_RUN_HOST,
    SYSTEM_CONTAINS_APPLICATION,
    _nonempty_text,
    _peer_uuids_from_edges,
    query_association_edges,
)
from apps.cmdb.services.instance import InstanceManage
from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.logger import cmdb_logger as logger

APPLICATION_MODEL = "application"
SYSTEM_MODEL = "system"
HOST_MODEL = "host"

EdgeLoader = Callable[[str, list[str]], list[dict[str, Any]]]

IMPORT_SYSTEM_KEYS = ("system", "应用系统", "系统")
IMPORT_APP_KEYS = ("application", "应用")
IMPORT_HOST_KEYS = ("host", "主机标识", "主机")


def _cell(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if key in row:
            return _nonempty_text(row.get(key))
    return ""


def _model_is_pre(model: dict[str, Any] | None) -> bool:
    if not model or "is_pre" not in model:
        return True
    value = model.get("is_pre")
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return value is True or value == 1


def _contains_adj(associations: Iterable[dict[str, Any]] | None) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for item in associations or []:
        if not isinstance(item, dict) or str(item.get("asst_id") or "") != "contains":
            continue
        src = str(item.get("src_model_id") or "")
        dst = str(item.get("dst_model_id") or "")
        if not src or not dst or dst == HOST_MODEL:
            continue
        bucket = adj.setdefault(src, [])
        if dst not in bucket:
            bucket.append(dst)
    return adj


def _can_reach_application(adj: dict[str, list[str]], start: str) -> bool:
    if start == APPLICATION_MODEL:
        return True
    seen = {start}
    stack = [start]
    while stack:
        current = stack.pop()
        for nxt in adj.get(current, []):
            if nxt in seen:
                continue
            if nxt == APPLICATION_MODEL:
                return True
            seen.add(nxt)
            stack.append(nxt)
    return False


def custom_layer_models(
    associations: Iterable[dict[str, Any]] | None,
    models: Iterable[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """系统到应用之间、用户自建的中间模型。内置模型不算。"""
    adj = _contains_adj(associations)
    by_id = {str(item.get("model_id") or ""): item for item in models or [] if isinstance(item, dict)}
    ordered: list[str] = []
    seen = {SYSTEM_MODEL}
    queue = [SYSTEM_MODEL]
    while queue:
        current = queue.pop(0)
        for nxt in adj.get(current, []):
            if nxt in seen:
                continue
            seen.add(nxt)
            ordered.append(nxt)
            queue.append(nxt)
    result: list[dict[str, str]] = []
    for model_id in ordered:
        if model_id in {SYSTEM_MODEL, APPLICATION_MODEL, HOST_MODEL}:
            continue
        if not _can_reach_application(adj, model_id):
            continue
        model = by_id.get(model_id) or {}
        if _model_is_pre(model):
            continue
        result.append({"model_id": model_id, "model_name": str(model.get("model_name") or model_id)})
    return result


def create_layer_models(
    parent_model_id: str,
    associations: Iterable[dict[str, Any]] | None,
    models: Iterable[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    layers = {item["model_id"]: item for item in custom_layer_models(associations, models)}
    result: list[dict[str, str]] = []
    for dst in _contains_adj(associations).get(str(parent_model_id or ""), []):
        item = layers.get(dst)
        if item and item not in result:
            result.append(item)
    return result


def can_create_application_model(parent_model_id: str, associations: Iterable[dict[str, Any]] | None) -> bool:
    parent = str(parent_model_id or "")
    if not parent or parent == APPLICATION_MODEL:
        return False
    return APPLICATION_MODEL in _contains_adj(associations).get(parent, [])


def contains_model_asst_id(
    parent_model_id: str,
    child_model_id: str,
    associations: Iterable[dict[str, Any]] | None,
) -> str:
    parent = str(parent_model_id or "")
    child = str(child_model_id or "")
    for item in associations or []:
        if not isinstance(item, dict) or str(item.get("asst_id") or "") != "contains":
            continue
        if str(item.get("src_model_id") or "") == parent and str(item.get("dst_model_id") or "") == child:
            return str(item.get("model_asst_id") or "")
    return ""


def layer_schema_from(
    associations: Iterable[dict[str, Any]] | None,
    models: Iterable[dict[str, Any]] | None,
) -> dict[str, Any]:
    model_list = [item for item in models or [] if isinstance(item, dict)]
    assoc_list = [item for item in associations or [] if isinstance(item, dict)]
    layers = custom_layer_models(assoc_list, model_list)
    layer_ids = {item["model_id"] for item in layers}
    names = {str(item.get("model_id") or ""): str(item.get("model_name") or item.get("model_id") or "") for item in model_list}
    create_layers_by_model: dict[str, list[dict[str, str]]] = {}
    can_create_app: dict[str, bool] = {}
    parents = {SYSTEM_MODEL, *layer_ids}
    for parent in parents:
        create_layers_by_model[parent] = create_layer_models(parent, assoc_list, model_list)
        can_create_app[parent] = can_create_application_model(parent, assoc_list)
    can_create_app[APPLICATION_MODEL] = False
    org_specs: list[tuple[str, str, str]] = []
    for item in assoc_list:
        if str(item.get("asst_id") or "") != "contains":
            continue
        src = str(item.get("src_model_id") or "")
        dst = str(item.get("dst_model_id") or "")
        asst = str(item.get("model_asst_id") or "")
        if not asst:
            continue
        if src in layer_ids or dst in layer_ids:
            org_specs.append((asst, src, dst))
    run_model_asst_id = APPLICATION_RUN_HOST
    run_src_model = APPLICATION_MODEL
    for item in assoc_list:
        if str(item.get("asst_id") or "") != "run":
            continue
        src = str(item.get("src_model_id") or "")
        dst = str(item.get("dst_model_id") or "")
        asst = str(item.get("model_asst_id") or "")
        if not asst or {src, dst} != {APPLICATION_MODEL, HOST_MODEL}:
            continue
        run_model_asst_id = asst
        run_src_model = src
        break
    return {
        "associations": assoc_list,
        "models": model_list,
        "create_layers_by_model": create_layers_by_model,
        "can_create_application_by_model": can_create_app,
        "org_specs": org_specs,
        "model_names": names,
        "layer_ids": layer_ids,
        "run_model_asst_id": run_model_asst_id,
        "run_src_model": run_src_model,
    }


def _layer_schema() -> dict[str, Any]:
    from apps.cmdb.language.service import SettingLanguage
    from apps.cmdb.services.model import ModelManage

    pending = [SYSTEM_MODEL]
    seen: set[str] = set()
    associations: list[dict[str, Any]] = []
    seen_assts: set[str] = set()
    while pending:
        model_id = pending.pop(0)
        if model_id in seen:
            continue
        seen.add(model_id)
        for edge in ModelManage.model_association_search(model_id) or []:
            asst = str(edge.get("model_asst_id") or "")
            if asst in seen_assts:
                continue
            seen_assts.add(asst)
            associations.append(edge)
            if str(edge.get("asst_id") or "") != "contains":
                continue
            for peer in (str(edge.get("src_model_id") or ""), str(edge.get("dst_model_id") or "")):
                if peer and peer not in seen and peer != HOST_MODEL:
                    pending.append(peer)
    language = SettingLanguage("zh-Hans")
    models = []
    for model_id in seen:
        info = ModelManage.search_model_info(model_id) or {}
        if not info:
            continue
        info = dict(info)
        info["model_name"] = language.get_val("MODEL", model_id) or info.get("model_name") or model_id
        models.append(info)
    return layer_schema_from(associations, models)


def _unique(values: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _nonempty_text(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def collect_service_tree_application_uuids(
    system_uuids,
    edge_loader: EdgeLoader | None = None,
) -> list[str]:
    """沿服务树收集应用 UUID，保留系统输入顺序，应用去重。"""
    loader = edge_loader or query_association_edges
    systems = _unique(system_uuids)
    if not systems:
        return []

    return _unique(
        _peer_uuids_from_edges(
            loader(SYSTEM_CONTAINS_APPLICATION, systems),
            systems,
            SYSTEM_MODEL,
            APPLICATION_MODEL,
        )
    )


def applications_by_system(system_uuids, edge_loader: EdgeLoader | None = None) -> dict[str, list[str]]:
    """每个系统沿服务树得到的应用 UUID 列表。"""
    loader = edge_loader or query_association_edges
    systems = _unique(system_uuids)
    result = {uuid: [] for uuid in systems}
    if not systems:
        return result
    edges: list[dict[str, Any]] = []
    edges.extend(loader(SYSTEM_CONTAINS_APPLICATION, systems))
    children = _children_by_parent(edges)
    for system_uuid in systems:
        apps: list[str] = []

        def walk(uuid: str) -> None:
            for kind, child_uuid in children.get(uuid, []):
                if kind == APPLICATION_MODEL:
                    apps.append(child_uuid)
                else:
                    walk(child_uuid)

        walk(system_uuid)
        result[system_uuid] = _unique(apps)
    return result


def expand_systems_to_host_uuids_via_service_tree(
    system_uuids,
    edge_loader: EdgeLoader | None = None,
) -> list[str]:
    """系统 → 应用 → 主机。不改旧两跳函数。"""
    loader = edge_loader or query_association_edges
    app_uuids = collect_service_tree_application_uuids(system_uuids, edge_loader=loader)
    if not app_uuids:
        return []
    return _peer_uuids_from_edges(
        loader(APPLICATION_RUN_HOST, app_uuids),
        app_uuids,
        APPLICATION_MODEL,
        HOST_MODEL,
    )


def _is_run_edge(edge: dict[str, Any]) -> bool:
    asst_id = str(edge.get("asst_id") or "")
    model_asst = str(edge.get("model_asst_id") or "")
    if asst_id == "run" or model_asst == APPLICATION_RUN_HOST or "_run_" in model_asst or model_asst.endswith("_run"):
        return True
    src_model = str(edge.get("src_model_id") or "")
    dst_model = str(edge.get("dst_model_id") or "")
    return {src_model, dst_model} == {APPLICATION_MODEL, HOST_MODEL}


def _parse_host_edge(edge: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(edge, dict) or not _is_run_edge(edge):
        return "", ""
    src_model = str(edge.get("src_model_id") or "")
    dst_model = str(edge.get("dst_model_id") or "")
    src = _nonempty_text(edge.get("src_inst_uuid"))
    dst = _nonempty_text(edge.get("dst_inst_uuid"))
    if src_model == APPLICATION_MODEL and dst_model == HOST_MODEL:
        return src, dst
    if dst_model == APPLICATION_MODEL and src_model == HOST_MODEL:
        return dst, src
    return "", ""


def _hosts_by_application(edges: Iterable[dict[str, Any]] | None) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}
    for edge in edges or []:
        app_uuid, host_uuid = _parse_host_edge(edge)
        if not app_uuid or not host_uuid:
            continue
        seen.setdefault(app_uuid, set())
        mapping.setdefault(app_uuid, [])
        if host_uuid in seen[app_uuid]:
            continue
        seen[app_uuid].add(host_uuid)
        mapping[app_uuid].append(host_uuid)
    return mapping


DEFAULT_ORG_SPECS = ((SYSTEM_CONTAINS_APPLICATION, SYSTEM_MODEL, APPLICATION_MODEL),)


def _org_specs(extra_specs: Iterable[tuple[str, str, str]] | None = None) -> tuple[tuple[str, str, str], ...]:
    specs = list(DEFAULT_ORG_SPECS)
    seen = {item[0] for item in specs}
    for spec in extra_specs or []:
        if spec and spec[0] and spec[0] not in seen:
            specs.append(spec)
            seen.add(spec[0])
    return tuple(specs)


def _org_models(extra_specs: Iterable[tuple[str, str, str]] | None = None) -> set[str]:
    models = {SYSTEM_MODEL, APPLICATION_MODEL}
    for spec in _org_specs(extra_specs):
        if spec[1]:
            models.add(spec[1])
        if spec[2]:
            models.add(spec[2])
    models.discard(HOST_MODEL)
    return models


def _is_contains_edge(edge: dict[str, Any]) -> bool:
    asst_id = str(edge.get("asst_id") or "")
    model_asst = str(edge.get("model_asst_id") or "")
    return asst_id == "contains" or "_contains_" in model_asst


def _parse_org_child(
    edge: dict[str, Any],
    extra_specs: Iterable[tuple[str, str, str]] | None = None,
) -> tuple[str, str, str]:
    """Return (parent_uuid, child_uuid, child_kind) for an org-spine edge."""
    if not isinstance(edge, dict):
        return "", "", ""
    asst = edge.get("model_asst_id")
    src = _nonempty_text(edge.get("src_inst_uuid"))
    dst = _nonempty_text(edge.get("dst_inst_uuid"))
    src_model = str(edge.get("src_model_id") or "")
    dst_model = str(edge.get("dst_model_id") or "")
    specs = _org_specs(extra_specs)
    for asst_id, parent_model, child_model in specs:
        if asst != asst_id:
            continue
        if src_model == parent_model and dst_model == child_model:
            return src, dst, child_model
        if dst_model == parent_model and src_model == child_model:
            return dst, src, child_model
    if not src or not dst or not _is_contains_edge(edge):
        return "", "", ""
    org_models = _org_models(extra_specs)
    if src_model in org_models and src_model != APPLICATION_MODEL and dst_model in org_models:
        return src, dst, dst_model
    if dst_model in org_models and dst_model != APPLICATION_MODEL and src_model in org_models:
        return dst, src, src_model
    return "", "", ""


def _children_by_parent(
    edges: Iterable[dict[str, Any]] | None,
    extra_specs: Iterable[tuple[str, str, str]] | None = None,
) -> dict[str, list[tuple[str, str]]]:
    """parent_uuid -> [(kind, child_uuid), ...]"""
    mapping: dict[str, list[tuple[str, str]]] = {}
    seen: dict[str, set[str]] = {}
    for edge in edges or []:
        parent_uuid, child_uuid, child_kind = _parse_org_child(edge, extra_specs)
        if not parent_uuid or not child_uuid:
            continue
        seen.setdefault(parent_uuid, set())
        mapping.setdefault(parent_uuid, [])
        if child_uuid in seen[parent_uuid]:
            continue
        seen[parent_uuid].add(child_uuid)
        mapping[parent_uuid].append((child_kind, child_uuid))
    return mapping


def build_service_tree(
    *,
    system: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    edges: Iterable[dict[str, Any]] | None,
    visible_uuids: set[str] | None = None,
    create_layers_by_model: dict[str, list[dict[str, str]]] | None = None,
    can_create_application_by_model: dict[str, bool] | None = None,
    model_names: dict[str, str] | None = None,
    extra_specs: Iterable[tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    children_map = _children_by_parent(edges, extra_specs=extra_specs)
    hosts_by_app = _hosts_by_application(edges)
    layers_by_model = create_layers_by_model or {}
    create_app_by_model = can_create_application_by_model or {}
    names = model_names or {}

    def _host_count_for_apps(app_uuids: list[str]) -> int:
        seen: set[str] = set()
        for app_uuid in app_uuids:
            for host_uuid in hosts_by_app.get(app_uuid, []):
                seen.add(host_uuid)
        return len(seen)

    def _walk(kind: str, uuid: str, depth: int) -> dict[str, Any]:
        entity = nodes.get(uuid) or {}
        if kind == SYSTEM_MODEL:
            entity = system
        child_nodes = []
        descendant_apps: list[str] = []
        for child_kind, child_uuid in children_map.get(uuid, []):
            if visible_uuids is not None and child_uuid not in visible_uuids:
                continue
            child = _walk(child_kind, child_uuid, depth + 1)
            child_nodes.append(child)
            if child_kind == APPLICATION_MODEL:
                descendant_apps.append(child_uuid)
            else:
                descendant_apps.extend(child.get("_apps") or [])
        host_count = _host_count_for_apps(descendant_apps if kind != APPLICATION_MODEL else [uuid])
        node = {
            "inst_uuid": uuid,
            "inst_name": str(entity.get("inst_name") or uuid),
            "kind": kind,
            "model_name": names.get(kind) or str(entity.get("model_name") or kind),
            "depth": depth,
            "host_count": host_count if kind != APPLICATION_MODEL else len(hosts_by_app.get(uuid, [])),
            "create_layers": list(layers_by_model.get(kind) or []),
            "can_create_application": bool(create_app_by_model[kind] if kind in create_app_by_model else kind == SYSTEM_MODEL),
            "children": child_nodes,
        }
        if kind != APPLICATION_MODEL:
            node["_apps"] = descendant_apps
        return node

    root = _walk(SYSTEM_MODEL, _nonempty_text(system.get("inst_uuid")), 0)
    root.pop("_apps", None)
    for child in root.get("children") or []:
        _strip_private(child)
    return root


def _strip_private(node: dict[str, Any]) -> None:
    node.pop("_apps", None)
    for child in node.get("children") or []:
        _strip_private(child)


def assign_host_plan(application_uuid: str, host_uuids: list[str], existing: Iterable[dict[str, Any]] | None) -> dict[str, list[tuple[str, str]]]:
    application_uuid = _nonempty_text(application_uuid)
    wanted = _unique(host_uuids)
    already = set(hosts_by_app.get(application_uuid, []) if (hosts_by_app := _hosts_by_application(existing)) else [])
    create = [(application_uuid, host_uuid) for host_uuid in wanted if host_uuid not in already]
    return {"create": create, "delete": []}


def transfer_host_plan(
    *,
    source_app: str,
    target_app: str,
    host_uuids: list[str],
    existing: Iterable[dict[str, Any]] | None,
) -> dict[str, list[tuple[str, str]]]:
    source_app = _nonempty_text(source_app)
    target_app = _nonempty_text(target_app)
    if not source_app or not target_app:
        raise ValidationAppException("转移需要指定源应用和目标应用")
    if source_app == target_app:
        return {"create": [], "delete": []}
    wanted = _unique(host_uuids)
    hosts_by_app = _hosts_by_application(existing)
    source_hosts = set(hosts_by_app.get(source_app, []))
    target_hosts = set(hosts_by_app.get(target_app, []))
    delete = [(source_app, host_uuid) for host_uuid in wanted if host_uuid in source_hosts]
    create = [(target_app, host_uuid) for host_uuid in wanted if host_uuid not in target_hosts]
    return {"create": create, "delete": delete}


def unbind_host_plan(
    application_uuid: str,
    host_uuids: list[str],
    existing: Iterable[dict[str, Any]] | None,
) -> dict[str, list[tuple[str, str]]]:
    application_uuid = _nonempty_text(application_uuid)
    if not application_uuid:
        raise ValidationAppException("解除挂靠需要指定应用")
    wanted = _unique(host_uuids)
    source_hosts = set(_hosts_by_application(existing).get(application_uuid, []))
    return {"delete": [(application_uuid, host_uuid) for host_uuid in wanted if host_uuid in source_hosts]}


def parse_import_row(row: dict[str, Any], *, expected_system_name: str) -> dict[str, str]:
    system_name = _cell(row, IMPORT_SYSTEM_KEYS)
    application = _cell(row, IMPORT_APP_KEYS)
    host = _cell(row, IMPORT_HOST_KEYS)
    expected = _nonempty_text(expected_system_name)
    if expected and system_name and system_name != expected:
        raise ValidationAppException("导入行的应用系统与当前系统不一致")
    if expected and not system_name:
        system_name = expected
    if not application:
        raise ValidationAppException("导入行缺少应用")
    if not host:
        raise ValidationAppException("导入行缺少主机标识")
    return {
        "system": system_name,
        "application": application,
        "host": host,
    }


def match_host(identifier: str, hosts: Iterable[dict[str, Any]] | None) -> dict[str, Any]:
    key = _nonempty_text(identifier)
    if not key:
        raise ValidationAppException("导入行缺少主机标识")
    by_uuid: dict[str, dict[str, Any]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    by_ip: dict[str, list[dict[str, Any]]] = {}
    for host in hosts or []:
        if not isinstance(host, dict):
            continue
        uuid = _nonempty_text(host.get("inst_uuid"))
        if uuid:
            by_uuid[uuid] = host
            by_name.setdefault(_nonempty_text(host.get("inst_name")), []).append(host)
            by_ip.setdefault(_nonempty_text(host.get("ip_addr")), []).append(host)
    if key in by_uuid:
        return by_uuid[key]
    name_hits = [item for item in by_name.get(key, []) if _nonempty_text(item.get("inst_uuid"))]
    if len(name_hits) == 1:
        return name_hits[0]
    if len(name_hits) > 1:
        raise ValidationAppException("主机标识匹配不唯一")
    ip_hits = [item for item in by_ip.get(key, []) if _nonempty_text(item.get("inst_uuid"))]
    if len(ip_hits) == 1:
        return ip_hits[0]
    if len(ip_hits) > 1:
        raise ValidationAppException("主机标识匹配不唯一")
    raise ValidationAppException("找不到对应的主机")


def _app_key(application: str) -> str:
    return f"a:/{application}"


def plan_import_rows(
    *,
    system_name: str,
    system_uuid: str,
    rows: Iterable[dict[str, Any]],
    existing_tree: dict[str, Any],
    hosts: Iterable[dict[str, Any]] | None,
) -> dict[str, Any]:
    existing_apps: dict[str, str] = dict(existing_tree.get("apps") or {})
    create_nodes: list[dict[str, Any]] = []
    created_keys: set[str] = set()
    assign: list[dict[str, str]] = []
    errors: list[dict[str, Any]] = []

    for index, raw in enumerate(rows or [], start=1):
        try:
            parsed = parse_import_row(raw, expected_system_name=system_name)
            host = match_host(parsed["host"], hosts)
            app_key = _app_key(parsed["application"])
            if app_key not in existing_apps and app_key not in created_keys:
                create_nodes.append(
                    {
                        "key": app_key,
                        "model_id": APPLICATION_MODEL,
                        "inst_name": parsed["application"],
                        "parent_key": system_uuid,
                        "parent_kind": SYSTEM_MODEL,
                    }
                )
                created_keys.add(app_key)
            assign.append({"app_key": existing_apps.get(app_key, app_key), "host_uuid": host["inst_uuid"]})
        except ValidationAppException as exc:
            errors.append({"row": index, "message": exc.message})

    return {"create_nodes": create_nodes, "assign": assign, "errors": errors}


def _run_bind(app_uuid: str, host_uuid: str, schema: dict[str, Any] | None = None) -> tuple[str, str, str]:
    schema = schema or _layer_schema()
    asst = str(schema.get("run_model_asst_id") or APPLICATION_RUN_HOST)
    if str(schema.get("run_src_model") or APPLICATION_MODEL) == HOST_MODEL:
        return host_uuid, app_uuid, asst
    return app_uuid, host_uuid, asst


def _create_run_association(app_uuid: str, host_uuid: str, operator: str, schema: dict[str, Any] | None = None) -> None:
    src, dst, asst = _run_bind(app_uuid, host_uuid, schema)
    _create_association(src, dst, asst, operator)


def _delete_run_association(
    app_uuid: str,
    host_uuid: str,
    operator: str,
    existing: Iterable[dict[str, Any]] | None = None,
    schema: dict[str, Any] | None = None,
) -> None:
    for edge in existing or []:
        found_app, found_host = _parse_host_edge(edge)
        if found_app != app_uuid or found_host != host_uuid:
            continue
        src = _nonempty_text(edge.get("src_inst_uuid"))
        dst = _nonempty_text(edge.get("dst_inst_uuid"))
        asst = str(edge.get("model_asst_id") or "")
        if src and dst and asst:
            _delete_association(src, dst, asst, operator)
            return
    src, dst, asst = _run_bind(app_uuid, host_uuid, schema)
    _delete_association(src, dst, asst, operator)


def _system_for_application(
    app_uuid: str,
    list_loader: Callable[[str, str], list[dict[str, Any]]] | None = None,
    extra_specs: Iterable[tuple[str, str, str]] | None = None,
) -> dict[str, str]:
    loader = list_loader or _association_list_loader
    pending: list[tuple[str, str]] = [(app_uuid, APPLICATION_MODEL)]
    scanned: set[str] = set()
    while pending:
        uuid, kind = pending.pop(0)
        if not uuid or uuid in scanned:
            continue
        scanned.add(uuid)
        listed = loader(kind, uuid) or []
        names: dict[str, str] = {}
        for item in listed:
            if not isinstance(item, dict):
                continue
            for peer in item.get("inst_list") or []:
                if not isinstance(peer, dict):
                    continue
                peer_uuid = _nonempty_text(peer.get("inst_uuid"))
                if peer_uuid:
                    names[peer_uuid] = str(peer.get("inst_name") or peer_uuid)
        for edge in edges_from_association_list(uuid, kind, listed):
            parent_uuid, child_uuid, _child_kind = _parse_org_child(edge, extra_specs)
            if child_uuid != uuid or not parent_uuid:
                continue
            parent_model = (
                str(edge.get("src_model_id") or "")
                if parent_uuid == _nonempty_text(edge.get("src_inst_uuid"))
                else str(edge.get("dst_model_id") or "")
            )
            parent_name = names.get(parent_uuid) or parent_uuid
            if parent_model == SYSTEM_MODEL:
                return {"inst_uuid": parent_uuid, "inst_name": parent_name}
            pending.append((parent_uuid, parent_model))
    return {}


def _create_association(src_uuid: str, dst_uuid: str, model_asst_id: str, operator: str) -> None:
    try:
        InstanceManage.instance_association_create_by_uuid(
            src_inst_uuid=src_uuid,
            dst_inst_uuid=dst_uuid,
            model_asst_id=model_asst_id,
            operator=operator,
        )
    except Exception as exc:
        message = str(getattr(exc, "message", "") or exc)
        if "repetition" in message or "已存在" in message:
            return
        raise


def _delete_association(src_uuid: str, dst_uuid: str, model_asst_id: str, operator: str) -> None:
    InstanceManage.instance_association_delete_by_key(
        src_inst_uuid=src_uuid,
        dst_inst_uuid=dst_uuid,
        model_asst_id=model_asst_id,
        operator=operator,
    )


def _org_child_uuid(
    edge: dict[str, Any],
    scanned: set[str],
    extra_specs: Iterable[tuple[str, str, str]] | None = None,
) -> str:
    parent_uuid, child_uuid, _kind = _parse_org_child(edge, extra_specs)
    if parent_uuid in scanned and child_uuid:
        return child_uuid
    return ""


def edges_from_association_list(center_uuid: str, center_model: str, groups: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """把列表/应用拓扑用的关联分组转成服务树边。"""
    edges: list[dict[str, Any]] = []
    center_uuid = _nonempty_text(center_uuid)
    center_model = str(center_model or "")
    if not center_uuid or not center_model:
        return edges
    for item in groups or []:
        if not isinstance(item, dict):
            continue
        src_model = str(item.get("src_model_id") or "")
        dst_model = str(item.get("dst_model_id") or "")
        model_asst = str(item.get("model_asst_id") or "")
        asst_id = str(item.get("asst_id") or "")
        for peer in item.get("inst_list") or []:
            if not isinstance(peer, dict):
                continue
            peer_uuid = _nonempty_text(peer.get("inst_uuid"))
            peer_model = str(peer.get("model_id") or "")
            if not peer_uuid:
                continue
            if center_model == src_model:
                src_uuid, dst_uuid = center_uuid, peer_uuid
                if not dst_model:
                    dst_model = peer_model
            else:
                src_uuid, dst_uuid = peer_uuid, center_uuid
                if not src_model:
                    src_model = peer_model
            edges.append(
                {
                    "model_asst_id": model_asst,
                    "asst_id": asst_id,
                    "src_model_id": src_model,
                    "dst_model_id": dst_model,
                    "src_inst_uuid": src_uuid,
                    "dst_inst_uuid": dst_uuid,
                }
            )
    return edges


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(edge.get("model_asst_id") or ""),
        _nonempty_text(edge.get("src_inst_uuid")),
        _nonempty_text(edge.get("dst_inst_uuid")),
        str(edge.get("dst_model_id") or ""),
    )


def _host_edges_for_apps(
    app_uuids: list[str],
    list_loader: Callable[[str, str], list[dict[str, Any]]] | None = None,
    seen: set[tuple[str, str, str, str]] | None = None,
    schema: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen_keys = seen if seen is not None else set()

    def _append_host_edge(edge: dict[str, Any]) -> None:
        app_uuid, host_uuid = _parse_host_edge(edge)
        if not app_uuid or not host_uuid:
            return
        key = _edge_key(edge)
        if key in seen_keys:
            return
        seen_keys.add(key)
        edges.append(edge)

    targets = _unique(app_uuids)
    if not targets:
        return edges
    assts = [APPLICATION_RUN_HOST]
    catalog_asst = str((schema or {}).get("run_model_asst_id") or "")
    if catalog_asst and catalog_asst not in assts:
        assts.append(catalog_asst)
    for asst in assts:
        for edge in query_association_edges(asst, targets):
            _append_host_edge(edge)
    if list_loader:
        for app_uuid in targets:
            listed = list_loader(APPLICATION_MODEL, app_uuid) or []
            for edge in edges_from_association_list(app_uuid, APPLICATION_MODEL, listed):
                _append_host_edge(edge)
    return edges


def _load_tree_edges(
    system_uuid: str,
    extra_uuids: list[str] | None = None,
    extra_specs: Iterable[tuple[str, str, str]] | None = None,
    list_loader: Callable[[str, str], list[dict[str, Any]]] | None = None,
    include_hosts: bool = True,
    host_app_uuids: list[str] | None = None,
) -> list[dict[str, Any]]:
    system_uuid = _nonempty_text(system_uuid)
    specs = _org_specs(extra_specs)
    org_assts = tuple(spec[0] for spec in specs)
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    pending = [system_uuid]
    scanned: set[str] = set()
    model_of = {system_uuid: SYSTEM_MODEL}

    def _remember(edge: dict[str, Any]) -> str:
        child = _org_child_uuid(edge, scanned, extra_specs=extra_specs)
        if not child:
            return ""
        key = _edge_key(edge)
        if key in seen:
            return child
        seen.add(key)
        edges.append(edge)
        parent_uuid, child_uuid, child_kind = _parse_org_child(edge, extra_specs)
        if child_uuid:
            model_of.setdefault(child_uuid, child_kind)
        if parent_uuid:
            model_of.setdefault(parent_uuid, str(edge.get("src_model_id") or SYSTEM_MODEL) if parent_uuid != child_uuid else child_kind)
        return child

    while pending:
        batch = [uuid for uuid in pending if uuid not in scanned]
        pending = []
        if not batch:
            break
        scanned.update(batch)
        for asst in org_assts:
            for edge in query_association_edges(asst, batch):
                child = _remember(edge)
                if child and child not in scanned:
                    pending.append(child)
        if list_loader:
            for uuid in batch:
                kind = model_of.get(uuid) or SYSTEM_MODEL
                if kind == APPLICATION_MODEL:
                    continue
                listed = list_loader(kind, uuid) or []
                for edge in edges_from_association_list(uuid, kind, listed):
                    child = _remember(edge)
                    if child and child not in scanned:
                        pending.append(child)
    children = _children_by_parent(edges, extra_specs=extra_specs)
    app_uuids: list[str] = []

    def walk(uuid: str) -> None:
        for kind, child_uuid in children.get(uuid, []):
            if kind == APPLICATION_MODEL:
                app_uuids.append(child_uuid)
            else:
                walk(child_uuid)

    walk(system_uuid)
    app_uuids = _unique([*app_uuids, *(extra_uuids or [])])
    if include_hosts:
        targets = host_app_uuids if host_app_uuids is not None else app_uuids
        edges.extend(_host_edges_for_apps(targets, list_loader=list_loader, seen=seen))
    return edges


def _association_list_loader(model_id: str, inst_uuid: str) -> list[dict[str, Any]]:
    return InstanceManage.instance_association_instance_list_by_uuid(model_id, inst_uuid) or []


def _index_nodes(uuids: list[str]) -> dict[str, dict[str, Any]]:
    if not uuids:
        return {}
    entities = InstanceManage.query_entity_by_uuids(uuids) or []
    return {_nonempty_text(item.get("inst_uuid")): item for item in entities if _nonempty_text(item.get("inst_uuid"))}


def _visible_tree(
    system: dict[str, Any],
    edges: list[dict[str, Any]],
    is_visible: Callable[[dict[str, Any]], bool] | None,
    schema: dict[str, Any],
) -> dict[str, Any]:
    system_uuid = _nonempty_text(system.get("inst_uuid"))
    extra_specs = schema.get("org_specs") or []
    host_uuids = {host_uuid for _, host_uuid in (_parse_host_edge(edge) for edge in edges) if host_uuid}
    node_uuids = []
    for edge in edges:
        for uuid in (_nonempty_text(edge.get("src_inst_uuid")), _nonempty_text(edge.get("dst_inst_uuid"))):
            if uuid and uuid != system_uuid and uuid not in host_uuids:
                node_uuids.append(uuid)
    nodes = _index_nodes(_unique(node_uuids))
    if is_visible:
        nodes = {uuid: item for uuid, item in nodes.items() if is_visible(item)}
    return build_service_tree(
        system=system,
        nodes=nodes,
        edges=edges,
        visible_uuids=set(nodes) if is_visible else None,
        create_layers_by_model=schema.get("create_layers_by_model"),
        can_create_application_by_model=schema.get("can_create_application_by_model"),
        model_names=schema.get("model_names"),
        extra_specs=extra_specs,
    )


class ServiceTreeService:
    @classmethod
    def get_tree(cls, system: dict[str, Any], is_visible: Callable[[dict[str, Any]], bool] | None = None) -> dict[str, Any]:
        schema = _layer_schema()
        edges = _load_tree_edges(
            _nonempty_text(system.get("inst_uuid")),
            extra_specs=schema.get("org_specs") or [],
            list_loader=_association_list_loader,
        )
        return _visible_tree(system, edges, is_visible, schema)

    @classmethod
    def get_org_tree(
        cls,
        system: dict[str, Any],
        is_visible: Callable[[dict[str, Any]], bool] | None = None,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        schema = schema or _layer_schema()
        edges = _load_tree_edges(
            _nonempty_text(system.get("inst_uuid")),
            extra_specs=schema.get("org_specs") or [],
            list_loader=_association_list_loader,
            include_hosts=False,
        )
        return _visible_tree(system, edges, is_visible, schema)

    @classmethod
    def _require_application(
        cls,
        system: dict[str, Any],
        application_uuid: str,
        is_visible: Callable[[dict[str, Any]], bool] | None,
        message: str,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        node = _find_tree_node(cls.get_org_tree(system, is_visible=is_visible, schema=schema), application_uuid)
        if node is None or node["kind"] != APPLICATION_MODEL:
            raise ValidationAppException(message)
        return node

    @classmethod
    def list_node_hosts(
        cls,
        system: dict[str, Any],
        node_uuid: str,
        is_visible: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        schema = _layer_schema()
        extra_specs = schema.get("org_specs") or []
        org_edges = _load_tree_edges(
            _nonempty_text(system.get("inst_uuid")),
            extra_specs=extra_specs,
            list_loader=_association_list_loader,
            include_hosts=False,
        )
        tree = _visible_tree(system, org_edges, is_visible, schema)
        node = _find_tree_node(tree, _nonempty_text(node_uuid) or _nonempty_text(system.get("inst_uuid")))
        if node is None:
            raise ValidationAppException("节点不在当前服务树中")
        app_uuids = _descendant_app_uuids(node)
        edges = _host_edges_for_apps(app_uuids, list_loader=_association_list_loader)
        hosts_by_app = _hosts_by_application(edges)
        host_uuids = []
        apps_by_host: dict[str, list[str]] = {}
        app_nodes = {item["inst_uuid"]: item for item in _iter_tree_nodes(tree) if item["kind"] == APPLICATION_MODEL}
        for app_uuid in app_uuids:
            for host_uuid in hosts_by_app.get(app_uuid, []):
                apps_by_host.setdefault(host_uuid, [])
                if app_uuid not in apps_by_host[host_uuid]:
                    apps_by_host[host_uuid].append(app_uuid)
                if host_uuid not in host_uuids:
                    host_uuids.append(host_uuid)
        hosts = _index_nodes(host_uuids)
        if is_visible:
            host_uuids = [uuid for uuid in host_uuids if is_visible(hosts.get(uuid) or {"inst_uuid": uuid, "model_id": HOST_MODEL})]
        host_rows = []
        for host_uuid in host_uuids[:500]:
            host = hosts.get(host_uuid) or {"inst_uuid": host_uuid, "inst_name": host_uuid}
            host_rows.append(
                {
                    "inst_uuid": host_uuid,
                    "inst_name": str(host.get("inst_name") or host_uuid),
                    "ip_addr": str(host.get("ip_addr") or ""),
                    "applications": [
                        {
                            "inst_uuid": app_uuid,
                            "inst_name": (app_nodes.get(app_uuid) or {}).get("inst_name") or app_uuid,
                        }
                        for app_uuid in apps_by_host.get(host_uuid, [])
                    ],
                }
            )
        children = [
            {
                "inst_uuid": child["inst_uuid"],
                "inst_name": child["inst_name"],
                "kind": child["kind"],
                "model_name": child.get("model_name") or child["kind"],
                "host_count": child["host_count"],
            }
            for child in node.get("children") or []
        ]
        return {
            "node": {key: node[key] for key in ("inst_uuid", "inst_name", "kind", "depth", "host_count")},
            "children": children,
            "hosts": host_rows,
        }

    @classmethod
    def systems_for_applications(cls, app_uuids: list[str]) -> dict[str, dict[str, str]]:
        extra_specs = _layer_schema().get("org_specs") or []
        result: dict[str, dict[str, str]] = {}
        for app_uuid in _unique(app_uuids):
            system = _system_for_application(app_uuid, extra_specs=extra_specs)
            if system:
                result[app_uuid] = system
        return result

    @classmethod
    def create_child(
        cls,
        *,
        system: dict[str, Any],
        parent_uuid: str,
        kind: str,
        inst_name: str,
        operator: str,
        allowed_org_ids: list | None = None,
        is_visible: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        parent_uuid = _nonempty_text(parent_uuid)
        inst_name = _nonempty_text(inst_name)
        kind = _nonempty_text(kind)
        if not inst_name:
            raise ValidationAppException("名称不能为空")
        tree = cls.get_tree(system, is_visible=is_visible)
        parent = _find_tree_node(tree, parent_uuid)
        if parent is None:
            raise ValidationAppException("父节点不在当前服务树中")
        if kind == APPLICATION_MODEL:
            if parent["kind"] == SYSTEM_MODEL:
                asst = SYSTEM_CONTAINS_APPLICATION
            else:
                schema = _layer_schema()
                asst = contains_model_asst_id(parent["kind"], APPLICATION_MODEL, schema.get("associations"))
                if not asst:
                    raise ValidationAppException("应用只能挂在系统或服务树中间层下")
            created = _create_instance(
                APPLICATION_MODEL,
                {
                    "inst_name": inst_name,
                    "organization": system.get("organization"),
                    "app_id": f"st-{uuid4().hex[:12]}",
                },
                operator,
                allowed_org_ids,
            )
        else:
            schema = _layer_schema()
            allowed = {item["model_id"] for item in create_layer_models(parent["kind"], schema.get("associations"), schema.get("models"))}
            if kind not in allowed:
                raise ValidationAppException("服务树只能新建当前路径上的自定义模型或应用")
            asst = contains_model_asst_id(parent["kind"], kind, schema.get("associations"))
            if not asst:
                raise ValidationAppException("服务树只能新建当前路径上的自定义模型或应用")
            created = _create_instance(
                kind,
                {"inst_name": inst_name, "organization": system.get("organization")},
                operator,
                allowed_org_ids,
            )
        _create_association(parent["inst_uuid"], created["inst_uuid"], asst, operator)
        logger.info(
            "event=service_tree_child_created system_uuid=%s parent_uuid=%s child_uuid=%s kind=%s",
            system.get("inst_uuid"),
            parent["inst_uuid"],
            created.get("inst_uuid"),
            kind,
        )
        return {"inst_uuid": created["inst_uuid"], "inst_name": inst_name, "kind": kind}

    @classmethod
    def rename_node(
        cls,
        *,
        system: dict[str, Any],
        node_uuid: str,
        inst_name: str,
        operator: str,
        user_groups: list,
        roles: list,
        allowed_org_ids: list | None = None,
        is_visible: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        node_uuid = _nonempty_text(node_uuid)
        inst_name = _nonempty_text(inst_name)
        if not inst_name:
            raise ValidationAppException("名称不能为空")
        tree = cls.get_tree(system, is_visible=is_visible)
        node = _find_tree_node(tree, node_uuid)
        if node is None or node["kind"] == SYSTEM_MODEL:
            raise ValidationAppException("不能在服务树中重命名该节点")
        InstanceManage.instance_update_by_uuid(
            user_groups,
            roles,
            node_uuid,
            {"inst_name": inst_name},
            operator,
            allowed_org_ids=allowed_org_ids,
        )
        return {"inst_uuid": node_uuid, "inst_name": inst_name, "kind": node["kind"]}

    @classmethod
    def delete_node(
        cls,
        *,
        system: dict[str, Any],
        node_uuid: str,
        operator: str,
        user_groups: list,
        roles: list,
        is_visible: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        node_uuid = _nonempty_text(node_uuid)
        tree = cls.get_tree(system, is_visible=is_visible)
        node = _find_tree_node(tree, node_uuid)
        if node is None or node["kind"] == SYSTEM_MODEL:
            raise ValidationAppException("不能删除该节点")
        InstanceManage.instance_batch_delete_by_uuids(user_groups, roles, [node_uuid], operator)
        logger.info(
            "event=service_tree_node_deleted system_uuid=%s node_uuid=%s kind=%s",
            system.get("inst_uuid"),
            node_uuid,
            node["kind"],
        )

    @classmethod
    def assign_hosts(
        cls,
        *,
        system: dict[str, Any],
        application_uuid: str,
        host_uuids: list[str],
        operator: str,
        is_visible: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        application_uuid = _nonempty_text(application_uuid)
        schema = _layer_schema()
        cls._require_application(system, application_uuid, is_visible, "只能在应用上添加主机", schema)
        hosts = _require_hosts(host_uuids)
        edges = _host_edges_for_apps([application_uuid], list_loader=_association_list_loader, schema=schema)
        plan = assign_host_plan(application_uuid, host_uuids, edges)
        for app_uuid, host_uuid in plan["create"]:
            _create_run_association(app_uuid, host_uuid, operator, schema)
        return {"assigned": [host["inst_uuid"] for host in hosts], "created": len(plan["create"])}

    @classmethod
    def transfer_hosts(
        cls,
        *,
        system: dict[str, Any],
        source_app: str,
        target_app: str,
        host_uuids: list[str],
        operator: str,
        target_visible: bool,
        is_visible: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        if not target_visible:
            raise ValidationAppException("目标应用不可见")
        schema = _layer_schema()
        cls._require_application(system, _nonempty_text(source_app), is_visible, "只能从当前树上的应用转移主机", schema)
        target = InstanceManage.query_entity_by_uuid(target_app)
        if not target or target.get("model_id") != APPLICATION_MODEL:
            raise ValidationAppException("目标应用不存在")
        _require_hosts(host_uuids)
        edges = _host_edges_for_apps(
            [_nonempty_text(source_app), _nonempty_text(target_app)],
            list_loader=_association_list_loader,
            schema=schema,
        )
        plan = transfer_host_plan(source_app=source_app, target_app=target_app, host_uuids=host_uuids, existing=edges)
        for app_uuid, host_uuid in plan["delete"]:
            _delete_run_association(app_uuid, host_uuid, operator, existing=edges, schema=schema)
        for app_uuid, host_uuid in plan["create"]:
            _create_run_association(app_uuid, host_uuid, operator, schema)
        return {"transferred": _unique(host_uuids), "target_app": _nonempty_text(target_app)}

    @classmethod
    def unbind_hosts(
        cls,
        *,
        system: dict[str, Any],
        application_uuid: str,
        host_uuids: list[str],
        operator: str,
        is_visible: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        application_uuid = _nonempty_text(application_uuid)
        schema = _layer_schema()
        cls._require_application(system, application_uuid, is_visible, "只能从当前树上的应用解除挂靠", schema)
        _require_hosts(host_uuids)
        edges = _host_edges_for_apps([application_uuid], list_loader=_association_list_loader, schema=schema)
        plan = unbind_host_plan(application_uuid, host_uuids, edges)
        for app_uuid, host_uuid in plan["delete"]:
            _delete_run_association(app_uuid, host_uuid, operator, existing=edges, schema=schema)
        return {"unbound": [host_uuid for _, host_uuid in plan["delete"]]}

    @classmethod
    def import_rows(
        cls,
        *,
        system: dict[str, Any],
        rows: list[dict[str, Any]],
        operator: str,
        allowed_org_ids: list | None = None,
        host_lookup: list[dict[str, Any]] | None = None,
        is_visible: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        system_uuid = _nonempty_text(system.get("inst_uuid"))
        tree = cls.get_tree(system, is_visible=is_visible)
        existing = _existing_tree_index(tree)
        hosts = host_lookup if host_lookup is not None else _lookup_hosts_for_rows(rows)
        plan = plan_import_rows(
            system_name=str(system.get("inst_name") or ""),
            system_uuid=system_uuid,
            rows=rows,
            existing_tree=existing,
            hosts=hosts,
        )
        created_ids: dict[str, str] = {system_uuid: system_uuid}
        for name, uuid in (existing.get("apps") or {}).items():
            created_ids[name] = uuid
        for node in plan["create_nodes"]:
            parent_uuid = created_ids.get(node["parent_key"], node["parent_key"])
            created = _create_instance(
                APPLICATION_MODEL,
                {
                    "inst_name": node["inst_name"],
                    "organization": system.get("organization"),
                    "app_id": f"st-{uuid4().hex[:12]}",
                },
                operator,
                allowed_org_ids,
            )
            _create_association(parent_uuid, created["inst_uuid"], SYSTEM_CONTAINS_APPLICATION, operator)
            created_ids[node["key"]] = created["inst_uuid"]
            created_ids[node["inst_name"]] = created["inst_uuid"]
        assigned = 0
        for item in plan["assign"]:
            app_uuid = created_ids.get(item["app_key"], existing.get("apps", {}).get(item["app_key"], item["app_key"]))
            if not _nonempty_text(app_uuid):
                continue
            _create_run_association(app_uuid, item["host_uuid"], operator)
            assigned += 1
        logger.info(
            "event=service_tree_import_finished system_uuid=%s created_nodes=%s assigned=%s failed_rows=%s",
            system_uuid,
            len(plan["create_nodes"]),
            assigned,
            len(plan["errors"]),
        )
        return {
            "created": len(plan["create_nodes"]),
            "assigned": assigned,
            "errors": plan["errors"],
        }

    @classmethod
    def export_rows(cls, system: dict[str, Any], is_visible: Callable[[dict[str, Any]], bool] | None = None) -> list[dict[str, str]]:
        tree = cls.get_tree(system, is_visible=is_visible)
        edges = _load_tree_edges(_nonempty_text(system.get("inst_uuid")))
        hosts_by_app = _hosts_by_application(edges)
        host_index = _index_nodes([host_uuid for hosts in hosts_by_app.values() for host_uuid in hosts])
        rows: list[dict[str, str]] = []
        system_name = str(system.get("inst_name") or "")

        def walk(node: dict[str, Any]):
            if node["kind"] == APPLICATION_MODEL:
                hosts = hosts_by_app.get(node["inst_uuid"], [])
                if not hosts:
                    return
                for host_uuid in hosts:
                    host = host_index.get(host_uuid) or {}
                    identifier = str(host.get("inst_name") or host.get("ip_addr") or host_uuid)
                    rows.append(
                        {
                            "应用系统": system_name,
                            "应用": node["inst_name"],
                            "主机标识": identifier,
                        }
                    )
                return
            for child in node.get("children") or []:
                walk(child)

        walk(tree)
        return rows


def _existing_tree_index(tree: dict[str, Any]) -> dict[str, Any]:
    apps: dict[str, str] = {}
    for node in _iter_tree_nodes(tree):
        if node["kind"] == APPLICATION_MODEL:
            apps[_app_key(node["inst_name"])] = node["inst_uuid"]
    return {"apps": apps}


def _iter_tree_nodes(node: dict[str, Any]):
    yield node
    for child in node.get("children") or []:
        yield from _iter_tree_nodes(child)


def _find_tree_node(node: dict[str, Any], uuid: str) -> dict[str, Any] | None:
    if node.get("inst_uuid") == uuid:
        return node
    for child in node.get("children") or []:
        found = _find_tree_node(child, uuid)
        if found is not None:
            return found
    return None


def _descendant_app_uuids(node: dict[str, Any]) -> list[str]:
    if node.get("kind") == APPLICATION_MODEL:
        return [node["inst_uuid"]]
    apps: list[str] = []
    for child in node.get("children") or []:
        apps.extend(_descendant_app_uuids(child))
    return apps


def _create_instance(model_id: str, instance_info: dict[str, Any], operator: str, allowed_org_ids: list | None) -> dict[str, Any]:
    return InstanceManage.instance_create(
        model_id,
        dict(instance_info),
        operator,
        allowed_org_ids=allowed_org_ids,
    )


def _require_hosts(host_uuids: list[str]) -> list[dict[str, Any]]:
    wanted = _unique(host_uuids)
    if not wanted:
        raise ValidationAppException("请选择主机")
    hosts = InstanceManage.query_entity_by_uuids(wanted) or []
    found = {_nonempty_text(item.get("inst_uuid")): item for item in hosts}
    missing = [uuid for uuid in wanted if uuid not in found or found[uuid].get("model_id") != HOST_MODEL]
    if missing:
        raise ValidationAppException("主机不存在")
    return [found[uuid] for uuid in wanted]


def _lookup_hosts_for_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    identifiers = []
    for row in rows or []:
        try:
            parsed = parse_import_row(row, expected_system_name=_cell(row, IMPORT_SYSTEM_KEYS))
        except ValidationAppException:
            continue
        identifiers.append(parsed["host"])
    if not identifiers:
        return []
    by_name = InstanceManage.search_inst_batch(HOST_MODEL, inst_names=identifiers) or {}
    by_uuid = InstanceManage.search_inst_batch(HOST_MODEL, inst_uuids=identifiers) or {}
    hosts = list({item["inst_uuid"]: item for item in list(by_name.values()) + list(by_uuid.values()) if item.get("inst_uuid")}.values())
    missing_ips = [value for value in identifiers if value not in by_name and value not in by_uuid]
    if missing_ips:
        with GraphClient() as graph:
            extra, _ = graph.query_entity(
                INSTANCE,
                [
                    {"field": "model_id", "type": "str=", "value": HOST_MODEL},
                    {"field": "ip_addr", "type": "str[]", "value": missing_ips},
                ],
            )
        for item in extra or []:
            if item.get("inst_uuid"):
                hosts.append(item)
    return hosts
