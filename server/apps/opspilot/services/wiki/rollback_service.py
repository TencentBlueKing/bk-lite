"""Preview and atomically execute retained Wiki generation rollbacks."""

from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from copy import deepcopy

from django.db import transaction
from django.db.models import Max
from jsonschema import Draft202012Validator

from apps.opspilot.models import BuildRecord, WikiDirectory, WikiGeneration, WikiKnowledgeBase, WikiStructureRevision
from apps.opspilot.services.wiki.generation_consistency_contract import (
    RollbackCompatibility,
    RollbackDirectorySnapshot,
    RollbackExecuteFacts,
    RollbackExecutionOutcome,
    RollbackStructureFacts,
    compare_rollback_structure,
    decide_rollback_execute,
)
from apps.opspilot.services.wiki.generation_service import (
    GENERATION_PAGE_ACTIONS_KEY,
    GenerationServiceError,
    activate_generation,
    begin_generation,
    clone_rollback_snapshot,
    mark_generation_ready,
)
from apps.opspilot.services.wiki.governance_api_schemas import SchemaName, get_schema

PREVIEW_REQUEST_SCHEMA = get_schema(SchemaName.GENERATION_ROLLBACK_PREVIEW_REQUEST)
PREVIEW_RESPONSE_SCHEMA = get_schema(SchemaName.GENERATION_ROLLBACK_PREVIEW_RESPONSE)
EXECUTE_REQUEST_SCHEMA = get_schema(SchemaName.GENERATION_ROLLBACK_EXECUTE_REQUEST)
EXECUTE_RESPONSE_SCHEMA = get_schema(SchemaName.GENERATION_ROLLBACK_EXECUTE_RESPONSE)
ROLLBACK_PIPELINE_VERSION = "wiki-generation-rollback-v1"
SUCCESSFUL_GENERATION_STATUSES = {"active", "superseded"}
logger = logging.getLogger("opspilot")


class RollbackServiceError(Exception):
    """Stable rollback error suitable for API responses."""

    def __init__(
        self,
        code,
        message,
        *,
        status_code=422,
        retryable=False,
        details=None,
    ):
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
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    if not errors:
        return
    raise RollbackServiceError(
        ("generation_rollback_request_invalid" if request else "generation_rollback_response_invalid"),
        ("Generation 回退请求不符合版本化契约" if request else "Generation 回退响应不符合版本化契约"),
        status_code=400 if request else 500,
        details={
            "issues": [
                {
                    "path": _schema_path(error),
                    "message": error.message,
                }
                for error in errors[:20]
            ]
        },
    )


def _active_pair(knowledge_base):
    revision = knowledge_base.active_structure_revision
    generation = knowledge_base.active_generation
    if revision is None or generation is None:
        raise RollbackServiceError(
            "wiki_generation_not_ready",
            "知识库尚未形成可回退的 active structure/generation",
            status_code=409,
            retryable=True,
            details={
                "active_structure_revision_id": (knowledge_base.active_structure_revision_id),
                "active_generation_id": knowledge_base.active_generation_id,
            },
        )
    if (
        revision.knowledge_base_id != knowledge_base.pk
        or generation.knowledge_base_id != knowledge_base.pk
        or generation.structure_revision_id != revision.pk
    ):
        raise RollbackServiceError(
            "active_generation_structure_mismatch",
            "知识库 active structure/generation 不一致",
            status_code=409,
            retryable=True,
        )
    return revision, generation


def _require_request_cas(
    payload,
    revision,
    generation,
):
    if payload["base_generation_id"] != generation.pk or payload["structure_version"] != revision.revision_no:
        raise RollbackServiceError(
            "generation_rollback_cas_conflict",
            "回退预期的 structure/base generation 已变化",
            status_code=409,
            retryable=True,
            details={
                "expected": {
                    "base_generation_id": payload["base_generation_id"],
                    "structure_version": payload["structure_version"],
                },
                "latest": {
                    "base_generation_id": generation.pk,
                    "structure_revision_id": revision.pk,
                    "structure_version": revision.revision_no,
                },
            },
        )


def _target_generation(knowledge_base, target_generation_id):
    try:
        return WikiGeneration.objects.select_related("structure_revision").get(
            pk=target_generation_id,
            knowledge_base=knowledge_base,
        )
    except WikiGeneration.DoesNotExist as error:
        raise RollbackServiceError(
            "rollback_target_not_found",
            "回退目标 generation 不存在或不属于该知识库",
            status_code=404,
            details={"target_generation_id": target_generation_id},
        ) from error


def _structure_nodes(snapshot):
    if not isinstance(snapshot, dict):
        raise RollbackServiceError(
            "rollback_structure_snapshot_invalid",
            "历史结构快照不是对象",
        )
    nodes = snapshot.get("directories")
    if not isinstance(nodes, list):
        raise RollbackServiceError(
            "rollback_structure_snapshot_invalid",
            "历史结构快照缺少 directories",
        )
    return nodes


def _snapshot_directory_facts(
    knowledge_base_id,
    snapshot,
):
    nodes = _structure_nodes(snapshot)
    by_id = {}
    for node in nodes:
        if (
            not isinstance(node, dict)
            or type(node.get("id")) is not int
            or not isinstance(node.get("key"), str)
            or not node["key"].strip()
            or not isinstance(node.get("name"), str)
            or not node["name"].strip()
        ):
            raise RollbackServiceError(
                "rollback_structure_snapshot_invalid",
                "历史结构快照包含非法目录节点",
            )
        if node["id"] in by_id:
            raise RollbackServiceError(
                "rollback_structure_snapshot_invalid",
                "历史结构快照包含重复目录 ID",
                details={"directory_id": node["id"]},
            )
        by_id[node["id"]] = node

    cache = {}
    visiting = set()

    def build(node_id):
        if node_id in cache:
            return cache[node_id]
        if node_id in visiting:
            raise RollbackServiceError(
                "rollback_structure_cycle",
                "历史结构快照包含目录循环",
                details={"directory_id": node_id},
            )
        node = by_id.get(node_id)
        if node is None:
            raise RollbackServiceError(
                "rollback_structure_parent_missing",
                "历史结构快照缺少父目录",
                details={"directory_id": node_id},
            )
        visiting.add(node_id)
        parent = node.get("parent")
        if parent is None:
            key_path = ()
            display_path = ()
        elif isinstance(parent, dict) and type(parent.get("id")) is int:
            parent_key_path, parent_display_path = build(parent["id"])
            key_path = parent_key_path
            display_path = parent_display_path
        else:
            raise RollbackServiceError(
                "rollback_structure_snapshot_invalid",
                "历史结构快照包含非法父目录引用",
                details={"directory_id": node_id},
            )
        visiting.remove(node_id)
        value = (
            key_path + (node["key"],),
            display_path + (node["name"],),
        )
        cache[node_id] = value
        return value

    facts = []
    for node in nodes:
        key_path, display_path = build(node["id"])
        status = node.get("status", "active")
        facts.append(
            RollbackDirectorySnapshot(
                knowledge_base_id=knowledge_base_id,
                key=node["key"],
                status=status,
                accepts_pages=status == "active",
                key_path=key_path,
                display_path=display_path,
            )
        )
    return tuple(facts)


def _live_directory_facts(knowledge_base):
    rows = list(
        WikiDirectory.objects.filter(knowledge_base=knowledge_base)
        .values(
            "id",
            "key",
            "name",
            "parent_id",
            "status",
            "accepts_pages",
        )
        .order_by("id")
    )
    by_id = {row["id"]: row for row in rows}
    cache = {}
    visiting = set()

    def build(directory_id):
        if directory_id in cache:
            return cache[directory_id]
        if directory_id in visiting:
            raise RollbackServiceError(
                "current_structure_cycle",
                "当前目录投影包含循环",
                details={"directory_id": directory_id},
            )
        row = by_id.get(directory_id)
        if row is None:
            raise RollbackServiceError(
                "current_structure_parent_missing",
                "当前目录投影缺少父目录",
                details={"directory_id": directory_id},
            )
        visiting.add(directory_id)
        if row["parent_id"] is None:
            key_path = ()
            display_path = ()
        else:
            key_path, display_path = build(row["parent_id"])
        visiting.remove(directory_id)
        value = (
            key_path + (row["key"],),
            display_path + (row["name"],),
        )
        cache[directory_id] = value
        return value

    return tuple(
        RollbackDirectorySnapshot(
            knowledge_base_id=knowledge_base.pk,
            key=row["key"],
            status=row["status"],
            accepts_pages=row["accepts_pages"],
            key_path=build(row["id"])[0],
            display_path=build(row["id"])[1],
        )
        for row in rows
    )


def _compatibility(
    knowledge_base,
    current_revision,
    target,
):
    referenced_keys = tuple(
        sorted(
            set(
                target.page_members.values_list(
                    "directory_key_snapshot",
                    flat=True,
                )
            )
        )
    )
    facts = RollbackStructureFacts(
        knowledge_base_id=knowledge_base.pk,
        target_generation_id=target.pk,
        target_generation_knowledge_base_id=(target.knowledge_base_id),
        target_generation_status=target.status,
        target_generation_retained=True,
        target_structure_revision_id=(target.structure_revision_id),
        target_structure_version=(target.structure_revision.revision_no),
        current_structure_revision_id=current_revision.pk,
        current_structure_version=current_revision.revision_no,
        referenced_directory_keys=referenced_keys,
        target_directories=_snapshot_directory_facts(
            knowledge_base.pk,
            target.structure_revision.structure_snapshot,
        ),
        current_directories=_live_directory_facts(knowledge_base),
    )
    return compare_rollback_structure(facts)


def _issue_details(issue):
    target = "/".join(issue.target_path)
    current = "/".join(issue.current_path)
    if target and current:
        return f"目标路径 {target}；当前路径 {current}"
    if target:
        return f"目标路径 {target}"
    if current:
        return f"当前路径 {current}"
    if issue.directory_key:
        return f"目录 {issue.directory_key}"
    return issue.code.value


def _preview_response(target, compatibility):
    issues = [
        {
            "code": issue.code.value,
            "path": "/".join(issue.target_path or issue.current_path),
            "details": _issue_details(issue),
        }
        for issue in compatibility.issues
    ]
    response = {
        "outcome": compatibility.outcome.value,
        "target_generation_id": target.pk,
        "structure_diff": issues,
        "impact": {
            "page_count": target.page_members.count(),
            "directory_count": len(
                set(
                    target.page_members.values_list(
                        "directory_key_snapshot",
                        flat=True,
                    )
                )
            ),
            "relation_count": target.relations.count(),
        },
        "allow_restore": (compatibility.outcome is RollbackCompatibility.REQUIRES_STRUCTURE_RESTORE),
        "block_reasons": [
            {
                "code": issue.code.value,
                "details": _issue_details(issue),
            }
            for issue in compatibility.issues
            if not issue.restorable
        ],
    }
    _validate_contract(
        response,
        PREVIEW_RESPONSE_SCHEMA,
        request=False,
    )
    return response


def preview_generation_rollback(
    knowledge_base,
    payload,
):
    _validate_contract(
        payload,
        PREVIEW_REQUEST_SCHEMA,
        request=True,
    )
    knowledge_base_id = getattr(
        knowledge_base,
        "pk",
        knowledge_base,
    )
    current = WikiKnowledgeBase.objects.select_related(
        "active_structure_revision",
        "active_generation",
    ).get(pk=knowledge_base_id)
    revision, generation = _active_pair(current)
    _require_request_cas(payload, revision, generation)
    target = _target_generation(
        current,
        payload["target_generation_id"],
    )
    compatibility = _compatibility(
        current,
        revision,
        target,
    )
    return _preview_response(target, compatibility)


def _snapshot_fingerprint(snapshot):
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _restore_structure_projection(
    knowledge_base,
    target_revision,
    *,
    operator,
):
    snapshot = deepcopy(target_revision.structure_snapshot or {})
    fingerprint = _snapshot_fingerprint(snapshot)
    if fingerprint != target_revision.fingerprint:
        raise RollbackServiceError(
            "rollback_structure_fingerprint_mismatch",
            "历史结构快照指纹不一致",
            details={"target_structure_revision_id": (target_revision.pk)},
        )
    nodes = _structure_nodes(snapshot)
    directories = list(WikiDirectory.objects.select_for_update().filter(knowledge_base=knowledge_base).order_by("id"))
    by_id = {directory.pk: directory for directory in directories}
    target_ids = set()
    actor = unicodedata.normalize(
        "NFKC",
        str(operator or ""),
    ).strip()[:32]

    for node in nodes:
        directory = by_id.get(node.get("id"))
        if directory is None:
            raise RollbackServiceError(
                "rollback_target_directory_missing",
                "历史结构目录已不存在，无法恢复",
                details={"directory_id": node.get("id")},
            )
        if directory.key != node.get("key") or directory.origin != node.get("origin"):
            raise RollbackServiceError(
                "rollback_target_directory_identity_mismatch",
                "历史结构目录身份已损坏",
                details={"directory_id": directory.pk},
            )
        target_ids.add(directory.pk)
        directory.name = node["name"]
        directory.description = node.get("description", "")
        directory.sort_order = node.get("order", 0)
        directory.status = node.get("status", "active")
        directory.accepts_pages = directory.status == "active"
        directory.merged_into = None
        directory.updated_by = actor
        directory.save(
            update_fields=[
                "name",
                "description",
                "sort_order",
                "status",
                "accepts_pages",
                "merged_into",
                "updated_by",
                "updated_at",
            ]
        )

    for directory in directories:
        if directory.pk in target_ids or directory.status != "active":
            continue
        if directory.origin == "schema":
            directory.status = "retired"
        elif directory.origin == "manual":
            directory.status = "archived"
        else:
            raise RollbackServiceError(
                "rollback_extra_system_directory",
                "当前结构包含历史快照之外的系统目录",
                details={"directory_id": directory.pk},
            )
        directory.accepts_pages = False
        directory.merged_into = None
        directory.updated_by = actor
        directory.save(
            update_fields=[
                "status",
                "accepts_pages",
                "merged_into",
                "updated_by",
                "updated_at",
            ]
        )

    for node in nodes:
        directory = by_id[node["id"]]
        parent = node.get("parent")
        parent_id = parent.get("id") if isinstance(parent, dict) else None
        if parent_id is not None and parent_id not in target_ids:
            raise RollbackServiceError(
                "rollback_structure_parent_missing",
                "历史结构父目录已不存在",
                details={
                    "directory_id": directory.pk,
                    "parent_id": parent_id,
                },
            )
        if directory.parent_id != parent_id:
            directory.parent_id = parent_id
            directory.updated_by = actor
            directory.save(
                update_fields=[
                    "parent",
                    "updated_by",
                    "updated_at",
                ]
            )

    revision_no = (WikiStructureRevision.objects.filter(knowledge_base=knowledge_base).aggregate(value=Max("revision_no"))["value"] or 0) + 1
    return WikiStructureRevision.objects.create(
        knowledge_base=knowledge_base,
        revision_no=revision_no,
        structure_snapshot=snapshot,
        fingerprint=fingerprint,
        created_by=actor,
        updated_by=actor,
    )


def _rollback_build_record(
    knowledge_base,
    active_generation,
    target,
    payload,
    *,
    operator,
):
    active_page_ids = set(
        active_generation.page_members.values_list(
            "page_id",
            flat=True,
        )
    )
    target_page_ids = set(
        target.page_members.values_list(
            "page_id",
            flat=True,
        )
    )
    archived = sorted(active_page_ids - target_page_ids)
    restored = sorted(target_page_ids - active_page_ids)
    unchanged = sorted(active_page_ids & target_page_ids)
    actor = unicodedata.normalize(
        "NFKC",
        str(operator or ""),
    ).strip()[:32]
    return BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="rollback",
        operator=operator or "",
        inputs={
            "target_generation_id": target.pk,
            "base_generation_id": active_generation.pk,
            "structure_version": payload["structure_version"],
            "confirm_structure_restore": payload["confirm_structure_restore"],
        },
        stage="rollback_preparing",
        progress=0,
        counts={
            "restored": len(restored),
            "archived": len(archived),
            "unchanged": len(unchanged),
        },
        affected_pages=sorted(target_page_ids | active_page_ids),
        errors=[],
        maintenance={
            GENERATION_PAGE_ACTIONS_KEY: [
                {
                    "page_id": page_id,
                    "action": "archive",
                    "target_status": "archived",
                }
                for page_id in archived
            ],
            "rollback_of": target.pk,
        },
        status="running",
        created_by=actor,
        updated_by=actor,
    )


@transaction.atomic
def execute_generation_rollback(
    knowledge_base,
    payload,
    *,
    operator="",
):
    _validate_contract(
        payload,
        EXECUTE_REQUEST_SCHEMA,
        request=True,
    )
    knowledge_base_id = getattr(
        knowledge_base,
        "pk",
        knowledge_base,
    )
    # Lock only the knowledge-base row. Both active pointers are nullable, so
    # select_related() would create outer joins that PostgreSQL cannot lock.
    locked = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base_id)
    revision, generation = _active_pair(locked)
    target = _target_generation(
        locked,
        payload["target_generation_id"],
    )
    compatibility = _compatibility(
        locked,
        revision,
        target,
    )
    decision = decide_rollback_execute(
        RollbackExecuteFacts(
            knowledge_base_id=locked.pk,
            target_generation_id=target.pk,
            requested_base_generation_id=payload["base_generation_id"],
            active_generation_id=generation.pk,
            requested_structure_version=payload["structure_version"],
            active_structure_version=revision.revision_no,
            confirm_structure_restore=payload["confirm_structure_restore"],
            compatibility=compatibility,
        )
    )
    if decision.outcome is not RollbackExecutionOutcome.EXECUTE:
        status_code = 409 if decision.outcome.value in {"conflict", "confirmation_required"} else 422
        raise RollbackServiceError(
            decision.code.value,
            "Generation 回退当前不可执行",
            status_code=status_code,
            retryable=decision.retryable,
            details={
                "preview": _preview_response(
                    target,
                    compatibility,
                )
            },
        )

    active_revision = revision
    if decision.create_structure_revision:
        active_revision = _restore_structure_projection(
            locked,
            target.structure_revision,
            operator=operator,
        )

    build_record = _rollback_build_record(
        locked,
        generation,
        target,
        payload,
        operator=operator,
    )
    try:
        candidate = begin_generation(
            knowledge_base=locked,
            kind="rollback",
            base_generation_id=generation.pk,
            structure_revision_id=active_revision.pk,
            pipeline_version=ROLLBACK_PIPELINE_VERSION,
            source_fingerprints=deepcopy(target.source_fingerprints or []),
            build_record=build_record,
            rollback_of_id=target.pk,
            operator=operator,
        )
        clone_rollback_snapshot(candidate.pk)
        mark_generation_ready(candidate.pk)
    except GenerationServiceError as error:
        raise RollbackServiceError(
            error.code,
            str(error),
            status_code=409 if error.retryable else 422,
            retryable=error.retryable,
            details=error.details,
        ) from error

    if decision.create_structure_revision:
        locked.active_structure_revision = active_revision
        locked.updated_by = unicodedata.normalize(
            "NFKC",
            str(operator or ""),
        ).strip()[:32]
        locked.save(
            update_fields=[
                "active_structure_revision",
                "updated_by",
                "updated_at",
            ]
        )

    try:
        activation = activate_generation(
            candidate.pk,
            requested_base_generation_id=generation.pk,
            expected_structure_revision_id=active_revision.pk,
            expected_structure_version=(active_revision.revision_no),
        )
    except GenerationServiceError as error:
        raise RollbackServiceError(
            error.code,
            str(error),
            status_code=409 if error.retryable else 422,
            retryable=error.retryable,
            details=error.details,
        ) from error
    if activation.outcome != "active":
        raise RollbackServiceError(
            activation.code,
            "Rollback generation 激活失败",
            status_code=409,
            retryable=activation.retryable,
            details={
                "candidate_generation_id": candidate.pk,
            },
        )

    maintenance = dict(build_record.maintenance or {})
    maintenance.update(
        {
            "generation_id": candidate.pk,
            "base_generation_id": generation.pk,
            "structure_revision_id": active_revision.pk,
            "structure_fingerprint": (active_revision.fingerprint),
            "pipeline_version": ROLLBACK_PIPELINE_VERSION,
            "activation": activation.outcome,
        }
    )
    build_record.maintenance = maintenance
    build_record.stage = "completed"
    build_record.progress = 100
    build_record.status = "success"
    build_record.save(
        update_fields=[
            "maintenance",
            "stage",
            "progress",
            "status",
            "updated_at",
        ]
    )

    response = {
        "previous_generation": {
            "id": generation.pk,
            "status": "superseded",
        },
        "active_generation": {
            "id": candidate.pk,
            "kind": "rollback",
            "rollback_of": target.pk,
            "structure_revision_id": active_revision.pk,
            "structure_version": active_revision.revision_no,
            "status": "active",
        },
        "structure_result": {
            "restored": decision.create_structure_revision,
            "previous_structure_revision_id": revision.pk,
            "active_structure_revision_id": active_revision.pk,
            "structure_version": active_revision.revision_no,
            "fingerprint": active_revision.fingerprint,
        },
    }
    _validate_contract(
        response,
        EXECUTE_RESPONSE_SCHEMA,
        request=False,
    )
    logger.info(
        "wiki_generation_rollback kb=%s target=%s previous=%s active=%s structure_restored=%s",
        locked.pk,
        target.pk,
        generation.pk,
        candidate.pk,
        decision.create_structure_revision,
    )
    return response
