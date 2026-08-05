"""Versioned Wiki directory structure reads and atomic governance saves."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from copy import deepcopy

from django.db import transaction
from django.db.models import Max
from jsonschema import Draft202012Validator

from apps.opspilot.models import (
    BuildRecord,
    KnowledgePage,
    Material,
    WikiDirectory,
    WikiGeneration,
    WikiGenerationPage,
    WikiKnowledgeBase,
    WikiStructureRevision,
)
from apps.opspilot.services.wiki.generation_service import GenerationServiceError, activate_generation, clone_base_snapshot, mark_generation_ready
from apps.opspilot.services.wiki.governance_api_schemas import SchemaName, get_schema
from apps.opspilot.services.wiki.purpose_schema_service import get_template_structure

STRUCTURE_SAVE_REQUEST = get_schema(SchemaName.STRUCTURE_SAVE_REQUEST)
STRUCTURE_SAVE_RESPONSE = get_schema(SchemaName.STRUCTURE_SAVE_RESPONSE)
UNCLASSIFIED_DIRECTORY_KEY = "__unclassified__"
UNCLASSIFIED_DIRECTORY_NAME = "待归类"
MAX_DIRECTORY_DEPTH = 8
GOVERNANCE_PIPELINE_VERSION = "wiki-structure-governance-v1"
NATIVE_RESTORE_PIPELINE_VERSION = "wiki-native-structure-restore-v1"
BOOTSTRAP_PIPELINE_VERSION = "wiki-knowledge-base-bootstrap-v1"
BOOTSTRAP_SOURCE_FINGERPRINTS = [
    {"kind": "wiki_knowledge_base_bootstrap", "version": 1},
]
NATIVE_DIRECTORY_KEY_RE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9._:-]{0,63}|__unclassified__)$")


class StructureServiceError(Exception):
    """Stable error returned by the structure API without leaking ORM details."""

    def __init__(self, code, message, *, status_code=422, retryable=False, details=None):
        self.code = str(code)
        self.status_code = int(status_code)
        self.retryable = bool(retryable)
        self.details = dict(details or {})
        super().__init__(message)


def _schema_path(error):
    return ".".join(str(part) for part in error.absolute_path) or "$"


def _validate_contract(payload, schema, *, request):
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
    )
    if not errors:
        return
    issues = [{"path": _schema_path(error), "message": error.message} for error in errors[:20]]
    if request:
        raise StructureServiceError(
            "structure_request_invalid",
            "目录结构请求不符合版本化契约",
            status_code=400,
            details={"issues": issues},
        )
    raise StructureServiceError(
        "structure_response_contract_invalid",
        "服务端目录结构快照不符合版本化契约",
        status_code=500,
        details={"issues": issues},
    )


def _normalize_text(value, field, *, allow_blank=False, collapse=True, max_length=None):
    normalized = unicodedata.normalize("NFKC", value)
    normalized = " ".join(normalized.split()) if collapse else normalized.strip()
    if not normalized and not allow_blank:
        raise StructureServiceError(
            "structure_text_blank",
            f"{field} 不能为空或仅包含空白",
            details={"field": field},
        )
    if max_length is not None and len(normalized) > max_length:
        raise StructureServiceError(
            "structure_text_too_long",
            f"{field} 超过最大长度 {max_length}",
            details={"field": field, "max_length": max_length},
        )
    return normalized


def _normalize_client_ref(value, field):
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise StructureServiceError(
            "client_ref_blank",
            "client_ref 不能为空或仅包含空白",
            details={"field": field},
        )
    if normalized != value:
        raise StructureServiceError(
            "client_ref_not_canonical",
            "client_ref 必须已使用 NFKC 且不能包含首尾空白",
            details={"field": field},
        )
    return normalized


def _normalize_type_list(values, field):
    normalized = []
    seen = set()
    for index, value in enumerate(values):
        item = _normalize_text(value, f"{field}.{index}", max_length=128)
        identity = item.casefold()
        if identity in seen:
            raise StructureServiceError(
                "page_type_duplicate",
                "page type 在 NFKC/空白规范化后重复",
                details={"field": field, "page_type": item},
            )
        seen.add(identity)
        normalized.append(item)
    return sorted(normalized, key=lambda item: (item.casefold(), item))


def _normalize_rules(rules, field, page_type_by_identity):
    allowed = _normalize_type_list(rules["allowed_page_types"], f"{field}.allowed_page_types")
    defaults = _normalize_type_list(rules["default_for_page_types"], f"{field}.default_for_page_types")

    def canonical(items, list_field):
        result = []
        for item in items:
            canonical_item = page_type_by_identity.get(item.casefold())
            if canonical_item is None:
                raise StructureServiceError(
                    "directory_rule_unknown_page_type",
                    "目录规则引用了 structure.page_types 之外的类型",
                    details={"field": list_field, "page_type": item},
                )
            result.append(canonical_item)
        return sorted(result, key=lambda value: (value.casefold(), value))

    allowed = canonical(allowed, f"{field}.allowed_page_types")
    defaults = canonical(defaults, f"{field}.default_for_page_types")
    if not set(defaults).issubset(set(allowed)):
        raise StructureServiceError(
            "directory_default_not_allowed",
            "default_for_page_types 必须是 allowed_page_types 的子集",
            details={"field": field, "defaults": defaults, "allowed": allowed},
        )
    return {"allowed_page_types": allowed, "default_for_page_types": defaults}


def _normalize_structure(structure):
    page_types = _normalize_type_list(structure["page_types"], "structure.page_types")
    page_type_by_identity = {page_type.casefold(): page_type for page_type in page_types}
    nodes = []
    nodes_by_token = {}
    existing_ids = set()
    existing_keys = set()
    client_refs = set()
    default_owners = {}

    for index, raw in enumerate(structure["directories"]):
        field = f"structure.directories.{index}"
        node = {
            "kind": raw["kind"],
            "name": _normalize_text(raw["name"], f"{field}.name", max_length=255),
            "description": _normalize_text(
                raw["description"],
                f"{field}.description",
                allow_blank=True,
                collapse=False,
                max_length=2000,
            ),
            "order": raw["order"],
            "rules": _normalize_rules(raw["rules"], f"{field}.rules", page_type_by_identity),
            "raw_parent": raw["parent"],
            "field": field,
        }
        if raw["kind"] == "existing":
            if raw["id"] in existing_ids:
                raise StructureServiceError(
                    "directory_identity_duplicate",
                    "完整结构中 existing directory id 重复",
                    details={"directory_id": raw["id"]},
                )
            if raw["key"] in existing_keys:
                raise StructureServiceError(
                    "directory_key_duplicate",
                    "完整结构中 existing directory key 重复",
                    details={"directory_key": raw["key"]},
                )
            existing_ids.add(raw["id"])
            existing_keys.add(raw["key"])
            token = ("existing", raw["id"])
            node.update(
                {
                    "token": token,
                    "id": raw["id"],
                    "key": raw["key"],
                    "origin": raw["origin"],
                    "status": raw["status"],
                }
            )
        else:
            client_ref = _normalize_client_ref(raw["client_ref"], f"{field}.client_ref")
            if client_ref in client_refs:
                raise StructureServiceError(
                    "client_ref_duplicate",
                    "完整结构中 client_ref 重复",
                    details={"client_ref": client_ref},
                )
            client_refs.add(client_ref)
            token = ("new", client_ref)
            node.update({"token": token, "client_ref": client_ref})
        nodes_by_token[token] = node
        nodes.append(node)
        for page_type in node["rules"]["default_for_page_types"]:
            owner = default_owners.get(page_type)
            if owner is not None:
                raise StructureServiceError(
                    "page_type_default_duplicate",
                    "每个 page type 只能有一个默认目录",
                    details={"page_type": page_type, "directories": [owner, field]},
                )
            default_owners[page_type] = field

    for node in nodes:
        parent = node.pop("raw_parent")
        if parent is None:
            node["parent_token"] = None
            continue
        if "id" in parent:
            parent_token = ("existing", parent["id"])
            node["parent_identity"] = {"id": parent["id"], "key": parent["key"]}
        else:
            client_ref = _normalize_client_ref(parent["client_ref"], f"{node['field']}.parent.client_ref")
            parent_token = ("new", client_ref)
            node["parent_identity"] = {"client_ref": client_ref}
        node["parent_token"] = parent_token
        if parent_token == node["token"]:
            raise StructureServiceError(
                "directory_cycle",
                "目录不能以自身作为父节点",
                details={"directory": node["field"]},
            )
        if parent_token[0] == "new" and parent_token not in nodes_by_token:
            raise StructureServiceError(
                "directory_parent_missing",
                "父节点 client_ref 不在完整结构中",
                details={"directory": node["field"], "client_ref": parent_token[1]},
            )

    sibling_names = {}
    for node in nodes:
        if node.get("status", "active") != "active":
            continue
        identity = (node["parent_token"], node["name"].casefold())
        owner = sibling_names.get(identity)
        if owner is not None:
            raise StructureServiceError(
                "directory_sibling_name_duplicate",
                "同一父节点下的目录名称必须唯一",
                details={"name": node["name"], "directories": [owner, node["field"]]},
            )
        sibling_names[identity] = node["field"]
    return page_types, nodes, nodes_by_token


def _validate_existing_identities(knowledge_base, nodes, nodes_by_token, local_directories):
    local_by_id = {directory.pk: directory for directory in local_directories}
    requested_ids = {node["id"] for node in nodes if node["kind"] == "existing"}
    referenced_ids = {node["parent_token"][1] for node in nodes if node["parent_token"] is not None and node["parent_token"][0] == "existing"}
    global_by_id = WikiDirectory.objects.filter(pk__in=requested_ids | referenced_ids).in_bulk()

    for node in nodes:
        if node["kind"] != "existing":
            continue
        directory = global_by_id.get(node["id"])
        if directory is None:
            raise StructureServiceError(
                "directory_not_found",
                "existing directory 不存在",
                details={"directory_id": node["id"]},
            )
        if directory.knowledge_base_id != knowledge_base.pk:
            raise StructureServiceError(
                "directory_knowledge_base_mismatch",
                "existing directory 属于其他知识库",
                details={"directory_id": node["id"]},
            )
        mismatches = [field for field in ("key", "origin", "status") if getattr(directory, field) != node[field]]
        if mismatches:
            raise StructureServiceError(
                "directory_read_only_identity_mismatch",
                "existing directory 的只读身份字段与数据库不一致",
                details={"directory_id": node["id"], "fields": mismatches},
            )
        node["object"] = local_by_id[node["id"]]

    for node in nodes:
        parent_token = node["parent_token"]
        if parent_token is None or parent_token[0] != "existing":
            continue
        parent_id = parent_token[1]
        parent = global_by_id.get(parent_id)
        if parent is None:
            raise StructureServiceError(
                "directory_parent_missing",
                "existing 父目录不存在",
                details={"directory": node["field"], "parent_id": parent_id},
            )
        if parent.knowledge_base_id != knowledge_base.pk:
            raise StructureServiceError(
                "directory_parent_knowledge_base_mismatch",
                "目录父节点不能跨知识库",
                details={"directory": node["field"], "parent_id": parent_id},
            )
        if parent_token not in nodes_by_token:
            raise StructureServiceError(
                "directory_parent_not_in_snapshot",
                "目录父节点必须包含在完整结构快照中",
                details={"directory": node["field"], "parent_id": parent_id},
            )
        if parent.key != node["parent_identity"]["key"]:
            raise StructureServiceError(
                "directory_parent_identity_mismatch",
                "父目录 id/key 与数据库不一致",
                details={"directory": node["field"], "parent_id": parent_id},
            )


def _validate_graph(nodes, nodes_by_token):
    depths = {}
    visiting = []
    visiting_set = set()

    def depth(token):
        if token in depths:
            return depths[token]
        if token in visiting_set:
            cycle_start = visiting.index(token)
            cycle = visiting[cycle_start:] + [token]
            raise StructureServiceError(
                "directory_cycle",
                "目录父子关系存在循环",
                details={
                    "directory": nodes_by_token[token]["field"],
                    "path": [nodes_by_token[item]["field"] for item in cycle],
                },
            )
        visiting.append(token)
        visiting_set.add(token)
        parent_token = nodes_by_token[token]["parent_token"]
        if parent_token is not None and len(visiting) >= MAX_DIRECTORY_DEPTH:
            raise StructureServiceError(
                "directory_depth_exceeded",
                f"目录最大深度不能超过 {MAX_DIRECTORY_DEPTH}",
                details={"directory": nodes_by_token[token]["field"], "depth": len(visiting) + 1},
            )
        value = 1 if parent_token is None else depth(parent_token) + 1
        visiting.pop()
        visiting_set.remove(token)
        depths[token] = value
        if value > MAX_DIRECTORY_DEPTH:
            raise StructureServiceError(
                "directory_depth_exceeded",
                f"目录最大深度不能超过 {MAX_DIRECTORY_DEPTH}",
                details={"directory": nodes_by_token[token]["field"], "depth": value},
            )
        return value

    for node in nodes:
        depth(node["token"])
        parent_token = node["parent_token"]
        if parent_token is not None:
            parent = nodes_by_token[parent_token]
            parent_status = parent.get("status", "active")
            if node.get("status", "active") == "active" and parent_status != "active":
                raise StructureServiceError(
                    "directory_parent_not_active",
                    "活动目录的父节点必须是活动目录",
                    details={"directory": node["field"], "parent": parent["field"]},
                )


def _active_snapshot_directory(active_revision, directory_id):
    for node in (active_revision.structure_snapshot or {}).get("directories", []):
        if node.get("id") == directory_id:
            return node
    return None


def _validate_unclassified(active_revision, nodes, nodes_by_token, local_directories):
    system_directories = [directory for directory in local_directories if directory.origin == "system"]
    reserved_directories = [directory for directory in local_directories if directory.key == UNCLASSIFIED_DIRECTORY_KEY]
    if len(system_directories) != 1 or len(reserved_directories) != 1 or system_directories[0].pk != reserved_directories[0].pk:
        raise StructureServiceError(
            "unclassified_directory_invariant",
            "知识库必须且只能有一个使用保留 key 的 system 待归类目录",
            details={
                "system_directory_ids": [directory.pk for directory in system_directories],
                "reserved_directory_ids": [directory.pk for directory in reserved_directories],
            },
        )
    directory = system_directories[0]
    invalid_projection = []
    expected_projection = {
        "key": UNCLASSIFIED_DIRECTORY_KEY,
        "name": UNCLASSIFIED_DIRECTORY_NAME,
        "parent_id": None,
        "origin": "system",
        "status": "active",
        "accepts_pages": True,
        "merged_into_id": None,
    }
    for field, value in expected_projection.items():
        if getattr(directory, field) != value:
            invalid_projection.append(field)
    token = ("existing", directory.pk)
    node = nodes_by_token.get(token)
    if node is None:
        raise StructureServiceError(
            "unclassified_directory_omitted",
            "完整结构不能省略系统待归类目录",
            details={"directory_id": directory.pk},
        )
    current = _active_snapshot_directory(active_revision, directory.pk)
    if current is None:
        invalid_projection.append("active_structure_snapshot")
    else:
        immutable = {
            "name": current.get("name"),
            "parent": current.get("parent"),
        }
        submitted = {
            "name": node["name"],
            "parent": None if node["parent_token"] is None else node["parent_identity"],
        }
        invalid_projection.extend(field for field, value in immutable.items() if submitted[field] != value)
    if node.get("origin") != "system" or node.get("status") != "active" or node["parent_token"] is not None:
        invalid_projection.extend(["origin/status/parent"])
    if invalid_projection:
        raise StructureServiceError(
            "unclassified_directory_invariant",
            "系统待归类目录是不可编辑的 system/active/root 节点",
            details={"directory_id": directory.pk, "fields": sorted(set(invalid_projection))},
        )
    for node in nodes:
        if node["kind"] == "existing" and node["key"] == UNCLASSIFIED_DIRECTORY_KEY and node["id"] != directory.pk:
            raise StructureServiceError(
                "reserved_directory_key_forbidden",
                "非系统目录不得使用待归类保留 key",
                details={"directory_id": node["id"]},
            )


def _validate_omissions(active_revision, active_generation, nodes, local_directories):
    current_ids = {node.get("id") for node in (active_revision.structure_snapshot or {}).get("directories", []) if type(node.get("id")) is int}
    submitted_ids = {node["id"] for node in nodes if node["kind"] == "existing"}
    omitted_ids = current_ids - submitted_ids
    local_by_id = {directory.pk: directory for directory in local_directories}
    missing_projection_ids = sorted(omitted_ids - set(local_by_id))
    if missing_projection_ids:
        raise StructureServiceError(
            "active_structure_projection_mismatch",
            "active structure 中的目录缺少数据库投影",
            status_code=409,
            details={"directory_ids": missing_projection_ids},
        )
    if not omitted_ids:
        return []
    omitted = [local_by_id[directory_id] for directory_id in sorted(omitted_ids)]
    system_directory_ids = [directory.pk for directory in omitted if directory.origin == "system"]
    if system_directory_ids:
        raise StructureServiceError(
            "system_directory_omission_forbidden",
            "完整结构不能省略系统目录",
            details={"directory_ids": system_directory_ids},
        )
    active_children = [directory.pk for directory in local_directories if directory.status == "active" and directory.parent_id in omitted_ids]
    if active_children:
        raise StructureServiceError(
            "directory_omission_has_active_children",
            "v1 不允许省略仍包含活动子目录的目录；请先显式移动或归档子目录",
            details={
                "directory_ids": sorted(omitted_ids),
                "active_child_directory_ids": sorted(active_children),
            },
        )
    generation_pages = list(active_generation.page_members.filter(directory_id__in=omitted_ids).values_list("page_id", flat=True)[:20])
    compatibility_pages = list(
        KnowledgePage.objects.filter(
            knowledge_base_id=active_generation.knowledge_base_id,
            directory_id__in=omitted_ids,
        ).values_list(
            "id", flat=True
        )[:20]
    )
    if generation_pages or compatibility_pages:
        raise StructureServiceError(
            "directory_omission_has_pages",
            "v1 不允许省略包含任意状态页面的目录；请先显式移动页面",
            details={
                "directory_ids": sorted(omitted_ids),
                "generation_page_ids": generation_pages,
                "compatibility_page_ids": compatibility_pages,
            },
        )
    return omitted


def _new_directory_key(used_keys):
    while True:
        key = f"dir_{uuid.uuid4().hex}"
        if key not in used_keys:
            used_keys.add(key)
            return key


def _apply_projection(knowledge_base, nodes, omitted, local_directories, operator):
    used_keys = {directory.key for directory in local_directories}
    client_ref_map = []
    for node in nodes:
        if node["kind"] == "existing":
            directory = node["object"]
            directory.name = node["name"]
            directory.description = node["description"]
            directory.sort_order = node["order"]
            directory.updated_by = operator
            directory.save(update_fields=["name", "description", "sort_order", "updated_by", "updated_at"])
            continue
        requested_key = node.get("restore_key")
        if requested_key:
            if requested_key in used_keys:
                raise StructureServiceError(
                    "native_directory_key_conflict",
                    "原生目录 key 与目标知识库现有目录冲突",
                    details={"key": requested_key},
                )
            used_keys.add(requested_key)
            directory_key = requested_key
        else:
            directory_key = _new_directory_key(used_keys)
        directory = WikiDirectory.objects.create(
            knowledge_base=knowledge_base,
            key=directory_key,
            name=node["name"],
            description=node["description"],
            parent=None,
            sort_order=node["order"],
            origin=node.get("restore_origin", "manual"),
            status="active",
            accepts_pages=True,
            merged_into=None,
            created_by=operator,
            updated_by=operator,
        )
        node["object"] = directory
        client_ref_map.append({"client_ref": node["client_ref"], "id": directory.pk, "key": directory.key})

    objects_by_token = {node["token"]: node["object"] for node in nodes}
    for node in nodes:
        directory = node["object"]
        parent = None if node["parent_token"] is None else objects_by_token[node["parent_token"]]
        if directory.parent_id != getattr(parent, "pk", None):
            directory.parent = parent
            directory.updated_by = operator
            directory.save(update_fields=["parent", "updated_by", "updated_at"])

    for directory in omitted:
        if directory.status == "active":
            if directory.origin == "schema":
                directory.status = "retired"
            elif directory.origin == "manual":
                directory.status = "archived"
            else:
                raise StructureServiceError(
                    "directory_omission_origin_invalid",
                    "只有 schema 或 manual 目录可以从完整结构中省略",
                    details={"directory_id": directory.pk, "origin": directory.origin},
                )
            directory.accepts_pages = False
            directory.merged_into = None
            directory.updated_by = operator
            directory.save(update_fields=["status", "accepts_pages", "merged_into", "updated_by", "updated_at"])
    return client_ref_map


def _canonical_snapshot(page_types, nodes):
    directories = []
    for node in nodes:
        directory = node["object"]
        parent = None
        if node["parent_token"] is not None:
            parent_object = next(candidate["object"] for candidate in nodes if candidate["token"] == node["parent_token"])
            parent = {"id": parent_object.pk, "key": parent_object.key}
        directories.append(
            {
                "id": directory.pk,
                "key": directory.key,
                "origin": directory.origin,
                "status": directory.status,
                "name": node["name"],
                "description": node["description"],
                "order": node["order"],
                "rules": node["rules"],
                "parent": parent,
            }
        )
    directories.sort(key=lambda node: (node["order"], node["id"]))
    return {"format_version": 1, "page_types": page_types, "directories": directories}


def _fingerprint(snapshot):
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _directory_breadcrumb(directory_id, directories_by_id):
    breadcrumb = []
    visited = set()
    current_id = directory_id
    while current_id is not None:
        if current_id in visited:
            raise StructureServiceError("directory_cycle", "目录父链存在循环", details={"directory_id": directory_id})
        visited.add(current_id)
        directory = directories_by_id.get(current_id)
        if directory is None:
            raise StructureServiceError(
                "directory_parent_missing",
                "目录父链缺少同知识库节点",
                details={"directory_id": directory_id, "missing_id": current_id},
            )
        breadcrumb.append({"id": directory.pk, "key": directory.key, "name": directory.name})
        current_id = directory.parent_id
    breadcrumb.reverse()
    return breadcrumb


def _refresh_generation_breadcrumbs(candidate, local_directories):
    directories_by_id = {directory.pk: directory for directory in local_directories}
    members = list(candidate.page_members.select_related("directory").order_by("id"))
    for member in members:
        member.directory_key_snapshot = member.directory.key
        member.directory_breadcrumb_snapshot = _directory_breadcrumb(member.directory_id, directories_by_id)
    if members:
        WikiGenerationPage.objects.bulk_update(
            members,
            ["directory_key_snapshot", "directory_breadcrumb_snapshot"],
            batch_size=500,
        )


def _latest_pointers(knowledge_base):
    revision = knowledge_base.active_structure_revision
    return {
        "structure_revision_id": getattr(revision, "pk", None),
        "structure_version": getattr(revision, "revision_no", None),
        "active_generation_id": knowledge_base.active_generation_id,
    }


def _require_active_pair(knowledge_base):
    revision = knowledge_base.active_structure_revision
    generation = knowledge_base.active_generation
    if revision is None or generation is None:
        raise StructureServiceError(
            "active_governance_snapshot_missing",
            "知识库尚无可治理的 active structure/generation",
            status_code=409,
            details={"latest": _latest_pointers(knowledge_base)},
        )
    invalid = []
    if revision.knowledge_base_id != knowledge_base.pk:
        invalid.append("structure_knowledge_base")
    if generation.knowledge_base_id != knowledge_base.pk:
        invalid.append("generation_knowledge_base")
    if generation.structure_revision_id != revision.pk:
        invalid.append("generation_structure_revision")
    if generation.status != "active":
        invalid.append("generation_status")
    if invalid:
        raise StructureServiceError(
            "active_governance_pointer_mismatch",
            "active structure/generation 指针不一致",
            status_code=409,
            details={"fields": invalid, "latest": _latest_pointers(knowledge_base)},
        )
    return revision, generation


def _response(revision, generation, snapshot, client_ref_map):
    payload = {
        "structure_revision": {
            "id": revision.pk,
            "version": revision.revision_no,
            "fingerprint": revision.fingerprint,
        },
        "active_generation": {
            "id": generation.pk,
            "structure_revision_id": generation.structure_revision_id,
            "structure_version": revision.revision_no,
            "status": generation.status,
        },
        "structure": deepcopy(snapshot),
        "client_ref_map": list(client_ref_map),
    }
    _validate_contract(payload, STRUCTURE_SAVE_RESPONSE, request=False)
    return payload


def _bootstrap_template_nodes(template_key):
    template_key = str(template_key or "general")
    try:
        template_structure = get_template_structure(template_key)
        if template_structure.get("format_version") != 1:
            raise StructureServiceError(
                "template_structure_format_invalid",
                "模板结构 format_version 必须为 1",
            )
        page_types = template_structure.get("page_types")
        raw_directories = template_structure.get("directories")
        if not isinstance(page_types, list) or not page_types:
            raise StructureServiceError(
                "template_structure_page_types_missing",
                "模板结构必须定义至少一个 page type",
            )
        if not isinstance(raw_directories, list) or not raw_directories:
            raise StructureServiceError(
                "template_structure_directories_missing",
                "模板结构必须定义至少一个目录",
            )

        directories = []
        for index, raw in enumerate(raw_directories):
            if not isinstance(raw, dict):
                raise StructureServiceError(
                    "template_structure_directory_invalid",
                    "模板目录必须是对象",
                    details={"index": index},
                )
            key = raw.get("key")
            if not isinstance(key, str) or not NATIVE_DIRECTORY_KEY_RE.fullmatch(key):
                raise StructureServiceError(
                    "template_structure_key_invalid",
                    "模板目录 key 非法",
                    details={"index": index, "key": key},
                )
            if key == UNCLASSIFIED_DIRECTORY_KEY:
                raise StructureServiceError(
                    "template_structure_reserved_key",
                    "模板目录不得占用系统待归类 key",
                    details={"index": index, "key": key},
                )
            parent_key = raw.get("parent_key")
            if parent_key is not None and not isinstance(parent_key, str):
                raise StructureServiceError(
                    "template_structure_parent_invalid",
                    "模板目录 parent_key 必须是字符串或 null",
                    details={"index": index, "parent_key": parent_key},
                )
            directories.append(
                {
                    "kind": "new",
                    "client_ref": key,
                    "name": raw["name"],
                    "description": raw.get("description", ""),
                    "order": raw["order"],
                    "rules": raw["rules"],
                    "parent": {"client_ref": parent_key} if parent_key else None,
                }
            )

        normalized_page_types, nodes, nodes_by_token = _normalize_structure(
            {
                "page_types": page_types,
                "directories": directories,
            }
        )
        _validate_graph(nodes, nodes_by_token)
        for node in nodes:
            node["restore_key"] = node["client_ref"]
            node["restore_origin"] = "schema"
        return normalized_page_types, nodes
    except StructureServiceError as error:
        raise StructureServiceError(
            "knowledge_base_template_structure_invalid",
            "知识库模板的结构化目录骨架无效",
            status_code=500,
            details={
                "template_key": template_key,
                "source_code": error.code,
                "source_details": error.details,
            },
        ) from error
    except (KeyError, TypeError, ValueError) as error:
        raise StructureServiceError(
            "knowledge_base_template_structure_invalid",
            "知识库模板的结构化目录骨架不完整",
            status_code=500,
            details={"template_key": template_key, "error": str(error)},
        ) from error


def _bootstrap_system_node(directory):
    return {
        "object": directory,
        "parent_token": None,
        "name": directory.name,
        "description": directory.description or "",
        "order": directory.sort_order,
        "rules": {
            "allowed_page_types": [],
            "default_for_page_types": [],
        },
    }


def _bootstrap_snapshot(directories, template_key):
    page_types, nodes = _bootstrap_template_nodes(template_key)
    directories_by_key = {directory.key: directory for directory in directories}
    expected_keys = {
        UNCLASSIFIED_DIRECTORY_KEY,
        *(node["restore_key"] for node in nodes),
    }
    actual_keys = set(directories_by_key)
    if actual_keys != expected_keys:
        raise StructureServiceError(
            "knowledge_base_bootstrap_directory_mismatch",
            "知识库 bootstrap 目录投影与模板不一致",
            status_code=409,
            details={
                "missing_keys": sorted(expected_keys - actual_keys),
                "unexpected_keys": sorted(actual_keys - expected_keys),
            },
        )
    system_directory = directories_by_key[UNCLASSIFIED_DIRECTORY_KEY]
    for node in nodes:
        node["object"] = directories_by_key[node["restore_key"]]
    return _canonical_snapshot(
        page_types,
        [_bootstrap_system_node(system_directory), *nodes],
    )


def _bootstrap_content_ids(knowledge_base):
    return {
        "page_id": KnowledgePage.objects.filter(knowledge_base=knowledge_base).order_by("id").values_list("id", flat=True).first(),
        "material_id": Material.objects.filter(knowledge_base=knowledge_base).order_by("id").values_list("id", flat=True).first(),
        "build_record_id": BuildRecord.objects.filter(knowledge_base=knowledge_base).order_by("id").values_list("id", flat=True).first(),
    }


def _bootstrap_completion_errors(knowledge_base, directories, revisions, generations):
    errors = []
    _, template_nodes = _bootstrap_template_nodes(knowledge_base.template_key)
    if len(directories) != len(template_nodes) + 1:
        errors.append("directory_count")
    if len(revisions) != 1:
        errors.append("revision_count")
    if len(generations) != 1:
        errors.append("generation_count")
    if errors:
        return errors

    directories_by_key = {directory.key: directory for directory in directories}
    directory = directories_by_key.get(UNCLASSIFIED_DIRECTORY_KEY)
    if directory is None:
        return ["directory.unclassified_missing"]
    expected_directory = {
        "key": UNCLASSIFIED_DIRECTORY_KEY,
        "name": UNCLASSIFIED_DIRECTORY_NAME,
        "description": "系统待归类目录",
        "parent_id": None,
        "sort_order": 0,
        "origin": "system",
        "status": "active",
        "accepts_pages": True,
        "merged_into_id": None,
    }
    errors.extend(f"directory.{field}" for field, value in expected_directory.items() if getattr(directory, field) != value)

    for node in template_nodes:
        key = node["restore_key"]
        template_directory = directories_by_key.get(key)
        if template_directory is None:
            errors.append(f"directory.{key}.missing")
            continue
        parent_key = node["parent_token"][1] if node["parent_token"] is not None else None
        parent = directories_by_key.get(parent_key) if parent_key else None
        expected_template_directory = {
            "name": node["name"],
            "description": node["description"],
            "parent_id": getattr(parent, "pk", None),
            "sort_order": node["order"],
            "origin": "schema",
            "status": "active",
            "accepts_pages": True,
            "merged_into_id": None,
        }
        errors.extend(
            f"directory.{key}.{field}" for field, value in expected_template_directory.items() if getattr(template_directory, field) != value
        )

    revision = revisions[0]
    snapshot = _bootstrap_snapshot(directories, knowledge_base.template_key)
    expected_revision = {
        "knowledge_base_id": knowledge_base.pk,
        "revision_no": 1,
        "structure_snapshot": snapshot,
        "fingerprint": _fingerprint(snapshot),
    }
    errors.extend(f"revision.{field}" for field, value in expected_revision.items() if getattr(revision, field) != value)

    generation = generations[0]
    expected_generation = {
        "knowledge_base_id": knowledge_base.pk,
        "build_record_id": None,
        "structure_revision_id": revision.pk,
        "base_generation_id": None,
        "rollback_of_id": None,
        "kind": "governance",
        "structure_fingerprint": revision.fingerprint,
        "pipeline_version": BOOTSTRAP_PIPELINE_VERSION,
        "source_fingerprints": BOOTSTRAP_SOURCE_FINGERPRINTS,
        "status": "active",
    }
    errors.extend(f"generation.{field}" for field, value in expected_generation.items() if getattr(generation, field) != value)
    if generation.page_members.exists():
        errors.append("generation.page_members")
    if generation.relations.exists():
        errors.append("generation.relations")
    if knowledge_base.active_structure_revision_id != revision.pk:
        errors.append("active_structure_revision")
    if knowledge_base.active_generation_id != generation.pk:
        errors.append("active_generation")
    return errors


@transaction.atomic
def bootstrap_knowledge_base(knowledge_base, *, operator=""):
    """Atomically create the empty governance baseline for a newly created KB."""

    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    locked = WikiKnowledgeBase.objects.select_for_update().filter(pk=knowledge_base_id).first()
    if locked is None:
        raise StructureServiceError(
            "knowledge_base_not_found",
            "知识库不存在",
            status_code=404,
        )

    content_ids = _bootstrap_content_ids(locked)
    populated = {field: value for field, value in content_ids.items() if value is not None}
    if populated:
        raise StructureServiceError(
            "knowledge_base_bootstrap_requires_empty",
            "新知识库治理 bootstrap 只允许完全空的知识库；存量知识库请使用管理命令",
            status_code=409,
            details=populated,
        )

    directories = list(WikiDirectory.objects.select_for_update().filter(knowledge_base=locked).order_by("id"))
    revisions = list(WikiStructureRevision.objects.select_for_update().filter(knowledge_base=locked).order_by("id"))
    generations = list(WikiGeneration.objects.select_for_update().filter(knowledge_base=locked).order_by("id"))

    if locked.active_structure_revision_id is not None or locked.active_generation_id is not None:
        errors = _bootstrap_completion_errors(
            locked,
            directories,
            revisions,
            generations,
        )
        if errors:
            raise StructureServiceError(
                "knowledge_base_bootstrap_corrupt",
                "新知识库治理 bootstrap 完成态已损坏，拒绝自动修复",
                status_code=409,
                details={"fields": errors},
            )
        revision = revisions[0]
        generation = generations[0]
        return _response(
            revision,
            generation,
            revision.structure_snapshot,
            [],
        )

    initial_errors = []
    if locked.directory_enabled:
        initial_errors.append("directory_enabled")
    if locked.active_structure_revision_id is not None:
        initial_errors.append("active_structure_revision")
    if locked.active_generation_id is not None:
        initial_errors.append("active_generation")
    if directories:
        initial_errors.append("directories")
    if revisions:
        initial_errors.append("structure_revisions")
    if generations:
        initial_errors.append("generations")
    if initial_errors:
        raise StructureServiceError(
            "knowledge_base_bootstrap_corrupt",
            "新知识库治理 bootstrap 初始状态不完整或有歧义，拒绝自动覆盖",
            status_code=409,
            details={"fields": initial_errors},
        )

    actor = unicodedata.normalize("NFKC", str(operator or "")).strip()[:32]
    directory = WikiDirectory.objects.create(
        knowledge_base=locked,
        key=UNCLASSIFIED_DIRECTORY_KEY,
        name=UNCLASSIFIED_DIRECTORY_NAME,
        description="系统待归类目录",
        parent=None,
        sort_order=0,
        origin="system",
        status="active",
        accepts_pages=True,
        merged_into=None,
        created_by=actor,
        updated_by=actor,
    )
    _, template_nodes = _bootstrap_template_nodes(locked.template_key)
    _apply_projection(
        locked,
        template_nodes,
        [],
        [directory],
        actor,
    )
    bootstrap_directories = [directory, *(node["object"] for node in template_nodes)]
    snapshot = _bootstrap_snapshot(bootstrap_directories, locked.template_key)
    fingerprint = _fingerprint(snapshot)
    revision = WikiStructureRevision.objects.create(
        knowledge_base=locked,
        revision_no=1,
        structure_snapshot=snapshot,
        fingerprint=fingerprint,
        created_by=actor,
        updated_by=actor,
    )
    generation = WikiGeneration.objects.create(
        knowledge_base=locked,
        build_record=None,
        structure_revision=revision,
        base_generation=None,
        rollback_of=None,
        kind="governance",
        structure_fingerprint=fingerprint,
        pipeline_version=BOOTSTRAP_PIPELINE_VERSION,
        source_fingerprints=deepcopy(BOOTSTRAP_SOURCE_FINGERPRINTS),
        status="preparing",
        created_by=actor,
        updated_by=actor,
    )
    try:
        mark_generation_ready(generation.pk)
    except GenerationServiceError as error:
        raise StructureServiceError(
            error.code,
            str(error),
            status_code=409 if error.retryable else 422,
            retryable=error.retryable,
            details=error.details,
        ) from error

    locked.active_structure_revision = revision
    locked.updated_by = actor
    locked.save(
        update_fields=[
            "active_structure_revision",
            "updated_by",
            "updated_at",
        ]
    )
    try:
        activation = activate_generation(
            generation.pk,
            requested_base_generation_id=None,
            expected_structure_revision_id=revision.pk,
            expected_structure_version=revision.revision_no,
        )
    except GenerationServiceError as error:
        raise StructureServiceError(
            error.code,
            str(error),
            status_code=409 if error.retryable else 422,
            retryable=error.retryable,
            details=error.details,
        ) from error
    if activation.outcome != "active":
        raise StructureServiceError(
            activation.code,
            "新知识库 baseline generation 激活失败",
            status_code=409 if activation.retryable else 422,
            retryable=activation.retryable,
            details={"candidate_generation_id": generation.pk},
        )

    locked.active_generation = generation
    locked.directory_enabled = False
    locked.save(
        update_fields=[
            "active_generation",
            "directory_enabled",
            "updated_by",
            "updated_at",
        ]
    )
    generation.refresh_from_db(fields=["status"])
    errors = _bootstrap_completion_errors(
        locked,
        bootstrap_directories,
        [revision],
        [generation],
    )
    if errors:
        raise StructureServiceError(
            "knowledge_base_bootstrap_corrupt",
            "新知识库治理 bootstrap 完成校验失败",
            status_code=409,
            details={"fields": errors},
        )
    return _response(revision, generation, snapshot, [])


def get_structure(knowledge_base):
    """Return the current canonical structure and its active CAS pointers."""

    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    current = (
        WikiKnowledgeBase.objects.select_related(
            "active_structure_revision",
            "active_generation__structure_revision",
        )
        .filter(pk=knowledge_base_id)
        .first()
    )
    if current is None:
        raise StructureServiceError("knowledge_base_not_found", "知识库不存在", status_code=404)
    revision = current.active_structure_revision
    generation = current.active_generation
    structure = deepcopy(revision.structure_snapshot) if revision is not None else {"format_version": 1, "page_types": [], "directories": []}
    return {
        "structure_revision": (
            {
                "id": revision.pk,
                "version": revision.revision_no,
                "fingerprint": revision.fingerprint,
            }
            if revision is not None
            else None
        ),
        "active_generation": (
            {
                "id": generation.pk,
                "structure_revision_id": generation.structure_revision_id,
                "structure_version": generation.structure_revision.revision_no,
                "status": generation.status,
            }
            if generation is not None
            else None
        ),
        "structure": structure,
    }


@transaction.atomic
def save_structure(knowledge_base, payload, *, operator=""):
    """Validate and atomically activate an immutable structure/governance pair."""

    _validate_contract(payload, STRUCTURE_SAVE_REQUEST, request=True)
    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    locked = WikiKnowledgeBase.objects.select_for_update().filter(pk=knowledge_base_id).first()
    if locked is None:
        raise StructureServiceError("knowledge_base_not_found", "知识库不存在", status_code=404)
    active_revision, active_generation = _require_active_pair(locked)
    latest = _latest_pointers(locked)
    if payload["structure_version"] != active_revision.revision_no:
        raise StructureServiceError(
            "structure_version_conflict",
            "active structure version 已变化",
            status_code=409,
            retryable=True,
            details={"expected": payload["structure_version"], "latest": latest},
        )
    if payload["base_generation_id"] != active_generation.pk:
        raise StructureServiceError(
            "base_generation_conflict",
            "active generation 已变化",
            status_code=409,
            retryable=True,
            details={"expected": payload["base_generation_id"], "latest": latest},
        )

    page_types, nodes, nodes_by_token = _normalize_structure(payload["structure"])
    local_directories = list(WikiDirectory.objects.select_for_update().filter(knowledge_base=locked).order_by("id"))
    _validate_existing_identities(locked, nodes, nodes_by_token, local_directories)
    _validate_graph(nodes, nodes_by_token)
    _validate_unclassified(active_revision, nodes, nodes_by_token, local_directories)
    omitted = _validate_omissions(active_revision, active_generation, nodes, local_directories)

    actor = unicodedata.normalize("NFKC", str(operator or "")).strip()[:32]
    client_ref_map = _apply_projection(locked, nodes, omitted, local_directories, actor)
    snapshot = _canonical_snapshot(page_types, nodes)
    fingerprint = _fingerprint(snapshot)
    revision_no = (WikiStructureRevision.objects.filter(knowledge_base=locked).aggregate(value=Max("revision_no"))["value"] or 0) + 1
    revision = WikiStructureRevision.objects.create(
        knowledge_base=locked,
        revision_no=revision_no,
        structure_snapshot=snapshot,
        fingerprint=fingerprint,
        created_by=actor,
        updated_by=actor,
    )
    candidate = WikiGeneration.objects.create(
        knowledge_base=locked,
        build_record=None,
        structure_revision=revision,
        base_generation=active_generation,
        rollback_of=None,
        kind="governance",
        structure_fingerprint=fingerprint,
        pipeline_version=GOVERNANCE_PIPELINE_VERSION,
        source_fingerprints=deepcopy(active_generation.source_fingerprints or []),
        status="preparing",
        created_by=actor,
        updated_by=actor,
    )
    try:
        clone_base_snapshot(candidate.pk)
        refreshed_directories = list(WikiDirectory.objects.filter(knowledge_base=locked).order_by("id"))
        _refresh_generation_breadcrumbs(candidate, refreshed_directories)
        mark_generation_ready(candidate.pk)
    except GenerationServiceError as error:
        raise StructureServiceError(
            error.code,
            str(error),
            status_code=409 if error.retryable else 422,
            retryable=error.retryable,
            details=error.details,
        ) from error

    locked.active_structure_revision = revision
    locked.updated_by = actor
    locked.save(update_fields=["active_structure_revision", "updated_by", "updated_at"])
    try:
        activation = activate_generation(
            candidate.pk,
            requested_base_generation_id=active_generation.pk,
            expected_structure_revision_id=revision.pk,
            expected_structure_version=revision.revision_no,
        )
    except GenerationServiceError as error:
        raise StructureServiceError(
            error.code,
            str(error),
            status_code=409 if error.retryable else 422,
            retryable=error.retryable,
            details=error.details,
        ) from error
    if activation.outcome != "active":
        raise StructureServiceError(
            activation.code,
            "目录结构治理 generation 激活失败",
            status_code=409 if activation.retryable else 422,
            retryable=activation.retryable,
            details={"latest": _latest_pointers(locked), "candidate_generation_id": candidate.pk},
        )
    candidate.refresh_from_db(fields=["status"])
    return _response(revision, candidate, snapshot, client_ref_map)


def _native_restore_nodes(locked, native_snapshot, active_revision, active_generation, local_directories):
    if not isinstance(native_snapshot, dict) or native_snapshot.get("format_version") != 1:
        raise StructureServiceError("native_structure_invalid", "原生 structure.json 格式版本无效")
    raw_directories = native_snapshot.get("directories")
    if not isinstance(raw_directories, list):
        raise StructureServiceError("native_structure_invalid", "原生 structure.json 缺少 directories")
    if KnowledgePage.objects.filter(knowledge_base=locked).exists() or active_generation.page_members.exists():
        raise StructureServiceError(
            "native_structure_restore_requires_empty_kb",
            "原生结构仅可恢复到没有任何知识页面的空知识库",
        )
    if len(local_directories) != 1:
        raise StructureServiceError(
            "native_structure_restore_requires_pristine_projection",
            "原生结构恢复要求目标知识库仅包含系统待归类目录",
            details={"directory_ids": [directory.pk for directory in local_directories]},
        )
    unclassified = local_directories[0]
    if unclassified.key != UNCLASSIFIED_DIRECTORY_KEY or unclassified.origin != "system":
        raise StructureServiceError(
            "unclassified_directory_invariant",
            "目标知识库缺少唯一系统待归类目录",
        )

    source_by_key = {}
    for index, raw in enumerate(raw_directories):
        if not isinstance(raw, dict):
            raise StructureServiceError(
                "native_structure_directory_invalid",
                "原生结构目录必须是对象",
                details={"index": index},
            )
        key = raw.get("key")
        if not isinstance(key, str) or not NATIVE_DIRECTORY_KEY_RE.fullmatch(key):
            raise StructureServiceError(
                "native_directory_key_invalid",
                "原生结构目录 key 非法",
                details={"index": index, "key": key},
            )
        if key in source_by_key:
            raise StructureServiceError(
                "native_directory_key_duplicate",
                "原生结构目录 key 重复",
                details={"key": key},
            )
        origin = raw.get("origin")
        status = raw.get("status")
        if status != "active":
            raise StructureServiceError(
                "native_directory_status_invalid",
                "原生活动结构只能包含 active 目录",
                details={"key": key, "status": status},
            )
        if key == UNCLASSIFIED_DIRECTORY_KEY:
            if origin != "system":
                raise StructureServiceError(
                    "reserved_directory_key_forbidden",
                    "待归类保留 key 只能属于 system 目录",
                )
        elif origin not in {"schema", "manual"}:
            raise StructureServiceError(
                "native_directory_origin_invalid",
                "原生结构只允许 schema/manual 目录和系统待归类目录",
                details={"key": key, "origin": origin},
            )
        source_by_key[key] = raw
    if UNCLASSIFIED_DIRECTORY_KEY not in source_by_key:
        raise StructureServiceError("unclassified_directory_omitted", "原生结构不能省略系统待归类目录")

    active_unclassified = _active_snapshot_directory(active_revision, unclassified.pk) or {}
    converted = []
    restore_metadata = {}
    for key, raw in source_by_key.items():
        parent = raw.get("parent")
        parent_key = None
        if parent is not None:
            if not isinstance(parent, dict) or not isinstance(parent.get("key"), str):
                raise StructureServiceError(
                    "native_directory_parent_invalid",
                    "原生结构父目录必须使用稳定 key",
                    details={"key": key},
                )
            parent_key = parent["key"]
            if parent_key not in source_by_key:
                raise StructureServiceError(
                    "directory_parent_missing",
                    "原生结构父目录 key 不存在",
                    details={"key": key, "parent_key": parent_key},
                )
        if parent_key is None:
            parent_ref = None
        elif parent_key == UNCLASSIFIED_DIRECTORY_KEY:
            parent_ref = {"id": unclassified.pk, "key": unclassified.key}
        else:
            parent_ref = {"client_ref": f"native:{parent_key}"}

        common = {
            "name": (active_unclassified.get("name", unclassified.name) if key == UNCLASSIFIED_DIRECTORY_KEY else raw.get("name")),
            "description": raw.get("description", ""),
            "order": raw.get("order"),
            "rules": raw.get("rules"),
            "parent": parent_ref,
        }
        if key == UNCLASSIFIED_DIRECTORY_KEY:
            converted.append(
                {
                    "kind": "existing",
                    "id": unclassified.pk,
                    "key": unclassified.key,
                    "origin": unclassified.origin,
                    "status": unclassified.status,
                    **common,
                }
            )
        else:
            client_ref = f"native:{key}"
            converted.append({"kind": "new", "client_ref": client_ref, **common})
            restore_metadata[client_ref] = {"key": key, "origin": raw["origin"]}

    request = {
        "structure_version": active_revision.revision_no,
        "base_generation_id": active_generation.pk,
        "structure": {
            "format_version": 1,
            "page_types": native_snapshot.get("page_types"),
            "directories": converted,
        },
    }
    _validate_contract(request, STRUCTURE_SAVE_REQUEST, request=True)
    page_types, nodes, nodes_by_token = _normalize_structure(request["structure"])
    _validate_existing_identities(locked, nodes, nodes_by_token, local_directories)
    _validate_graph(nodes, nodes_by_token)
    _validate_unclassified(active_revision, nodes, nodes_by_token, local_directories)
    omitted = _validate_omissions(active_revision, active_generation, nodes, local_directories)
    if omitted:
        raise StructureServiceError(
            "native_structure_restore_requires_pristine_projection",
            "原生结构恢复不能覆盖已有目录投影",
        )
    for node in nodes:
        if node["kind"] == "new":
            metadata = restore_metadata[node["client_ref"]]
            node["restore_key"] = metadata["key"]
            node["restore_origin"] = metadata["origin"]
    return page_types, nodes


def preview_native_structure_restore(knowledge_base, native_snapshot):
    current = WikiKnowledgeBase.objects.select_related(
        "active_structure_revision",
        "active_generation",
    ).get(pk=getattr(knowledge_base, "pk", knowledge_base))
    active_revision, active_generation = _require_active_pair(current)
    local_directories = list(WikiDirectory.objects.filter(knowledge_base=current).order_by("id"))
    _page_types, nodes = _native_restore_nodes(
        current,
        native_snapshot,
        active_revision,
        active_generation,
        local_directories,
    )
    return {
        "restore_native_structure": True,
        "create_directory_count": sum(node["kind"] == "new" for node in nodes),
    }


@transaction.atomic
def restore_native_structure(
    knowledge_base,
    native_snapshot,
    *,
    expected_base_generation_id,
    expected_structure_version,
    source_fingerprint="",
    operator="",
):
    locked = WikiKnowledgeBase.objects.select_for_update().filter(pk=getattr(knowledge_base, "pk", knowledge_base)).first()
    if locked is None:
        raise StructureServiceError("knowledge_base_not_found", "知识库不存在", status_code=404)
    active_revision, active_generation = _require_active_pair(locked)
    if expected_structure_version != active_revision.revision_no:
        raise StructureServiceError(
            "structure_version_conflict",
            "active structure version 已变化",
            status_code=409,
            retryable=True,
            details={"latest": _latest_pointers(locked)},
        )
    if expected_base_generation_id != active_generation.pk:
        raise StructureServiceError(
            "base_generation_conflict",
            "active generation 已变化",
            status_code=409,
            retryable=True,
            details={"latest": _latest_pointers(locked)},
        )

    local_directories = list(WikiDirectory.objects.select_for_update().filter(knowledge_base=locked).order_by("id"))
    page_types, nodes = _native_restore_nodes(
        locked,
        native_snapshot,
        active_revision,
        active_generation,
        local_directories,
    )
    actor = unicodedata.normalize("NFKC", str(operator or "")).strip()[:32]
    client_ref_map = _apply_projection(locked, nodes, [], local_directories, actor)
    snapshot = _canonical_snapshot(page_types, nodes)
    fingerprint = _fingerprint(snapshot)
    revision_no = (WikiStructureRevision.objects.filter(knowledge_base=locked).aggregate(value=Max("revision_no"))["value"] or 0) + 1
    revision = WikiStructureRevision.objects.create(
        knowledge_base=locked,
        revision_no=revision_no,
        structure_snapshot=snapshot,
        fingerprint=fingerprint,
        created_by=actor,
        updated_by=actor,
    )
    candidate = WikiGeneration.objects.create(
        knowledge_base=locked,
        build_record=None,
        structure_revision=revision,
        base_generation=active_generation,
        rollback_of=None,
        kind="governance",
        structure_fingerprint=fingerprint,
        pipeline_version=NATIVE_RESTORE_PIPELINE_VERSION,
        source_fingerprints=([{"archive_sha256": source_fingerprint}] if source_fingerprint else []),
        status="preparing",
        created_by=actor,
        updated_by=actor,
    )
    try:
        clone_base_snapshot(candidate.pk)
        refreshed_directories = list(WikiDirectory.objects.filter(knowledge_base=locked).order_by("id"))
        _refresh_generation_breadcrumbs(candidate, refreshed_directories)
        mark_generation_ready(candidate.pk)
    except GenerationServiceError as error:
        raise StructureServiceError(
            error.code,
            str(error),
            status_code=409 if error.retryable else 422,
            retryable=error.retryable,
            details=error.details,
        ) from error

    locked.active_structure_revision = revision
    locked.updated_by = actor
    locked.save(update_fields=["active_structure_revision", "updated_by", "updated_at"])
    try:
        activation = activate_generation(
            candidate.pk,
            requested_base_generation_id=active_generation.pk,
            expected_structure_revision_id=revision.pk,
            expected_structure_version=revision.revision_no,
        )
    except GenerationServiceError as error:
        raise StructureServiceError(
            error.code,
            str(error),
            status_code=409 if error.retryable else 422,
            retryable=error.retryable,
            details=error.details,
        ) from error
    if activation.outcome != "active":
        raise StructureServiceError(
            activation.code,
            "原生目录结构 generation 激活失败",
            status_code=409 if activation.retryable else 422,
            retryable=activation.retryable,
            details={
                "latest": _latest_pointers(locked),
                "candidate_generation_id": candidate.pk,
            },
        )
    candidate.refresh_from_db(fields=["status"])
    return _response(revision, candidate, snapshot, client_ref_map)


__all__ = [
    "STRUCTURE_SAVE_REQUEST",
    "STRUCTURE_SAVE_RESPONSE",
    "StructureServiceError",
    "bootstrap_knowledge_base",
    "get_structure",
    "preview_native_structure_restore",
    "restore_native_structure",
    "save_structure",
]
