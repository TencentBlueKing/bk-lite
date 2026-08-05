"""Preview and execute destructive Wiki directory operations.

The signed operation token binds the complete impact snapshot to the active
structure and generation. Execution recalculates the impact under the
knowledge-base lock, publishes a new immutable structure/generation pair, and
never asks an LLM to merge page content.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from copy import deepcopy
from datetime import timedelta

from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from jsonschema import Draft202012Validator

from apps.opspilot.models import PageDirectoryChange, WikiDirectory, WikiGeneration, WikiGenerationPage, WikiKnowledgeBase, WikiStructureRevision
from apps.opspilot.services.wiki.directory_service import DirectoryServiceError, _active_pair, _generation_error
from apps.opspilot.services.wiki.generation_service import (
    GenerationServiceError,
    activate_generation,
    clone_base_snapshot,
    mark_generation_ready,
    put_generation_member,
)
from apps.opspilot.services.wiki.governance_api_schemas import SchemaName, get_schema

PREVIEW_REQUEST_SCHEMA = get_schema(SchemaName.DIRECTORY_OPERATION_PREVIEW_REQUEST)
PREVIEW_RESPONSE_SCHEMA = get_schema(SchemaName.DIRECTORY_OPERATION_PREVIEW_RESPONSE)
EXECUTE_REQUEST_SCHEMA = get_schema(SchemaName.DIRECTORY_OPERATION_EXECUTE_REQUEST)
EXECUTE_RESPONSE_SCHEMA = get_schema(SchemaName.DIRECTORY_OPERATION_EXECUTE_RESPONSE)
OPERATION_TOKEN_SALT = "opspilot.wiki.directory-operation.v1"
OPERATION_TOKEN_TTL_SECONDS = 10 * 60
OPERATION_PIPELINE_VERSION = "wiki-directory-operation-v1"
UNCLASSIFIED_DIRECTORY_KEY = "__unclassified__"


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
    issues = [
        {
            "path": _schema_path(error),
            "message": error.message,
        }
        for error in errors[:20]
    ]
    raise DirectoryServiceError(
        ("directory_operation_request_invalid" if request else "directory_operation_response_invalid"),
        ("目录操作请求不符合版本化契约" if request else "目录操作响应不符合版本化契约"),
        status_code=400 if request else 500,
        details={"issues": issues},
    )


def _directory_ref(directory):
    return {
        "id": directory.pk,
        "key": directory.key,
    }


def _normalized_name(value):
    return " ".join(
        unicodedata.normalize(
            "NFKC",
            str(value or ""),
        ).split()
    ).casefold()


def _active_snapshot_ids(revision):
    return {
        node.get("id")
        for node in (revision.structure_snapshot or {}).get("directories", [])
        if (isinstance(node, dict) and type(node.get("id")) is int)
    }


def _descendant_ids(source_id, directories):
    children = {}
    for directory in directories:
        children.setdefault(
            directory.parent_id,
            [],
        ).append(directory.pk)
    descendants = set()
    pending = list(children.get(source_id, []))
    while pending:
        directory_id = pending.pop()
        if directory_id in descendants:
            raise DirectoryServiceError(
                "directory_cycle",
                "目录父链存在循环",
                details={"directory_id": source_id},
            )
        descendants.add(directory_id)
        pending.extend(children.get(directory_id, []))
    return descendants


def _block(code, details):
    return {
        "code": code,
        "details": details,
    }


def _conflict(source, target):
    return {
        "code": "child_directory_name_conflict",
        "details": (f"源子目录“{source.name}”与目标子目录" f"“{target.name}”规范化名称冲突"),
        "source": _directory_ref(source),
        "target": _directory_ref(target),
    }


def _load_directory(
    directories_by_id,
    reference,
    field,
    active_ids,
):
    directory = directories_by_id.get(reference["id"])
    if directory is None or directory.key != reference["key"] or directory.pk not in active_ids or directory.status != "active":
        raise DirectoryServiceError(
            f"{field}_directory_invalid",
            f"{field} 目录不属于当前活动结构",
            details={"reference": reference},
        )
    return directory


def _operation_state(
    knowledge_base,
    payload,
    *,
    lock_directories=False,
):
    (
        knowledge_base,
        revision,
        generation,
    ) = _active_pair(
        knowledge_base,
        base_generation_id=payload["base_generation_id"],
        structure_version=payload["structure_version"],
    )
    directory_query = WikiDirectory.objects.filter(knowledge_base=knowledge_base).order_by("id")
    if lock_directories:
        directory_query = directory_query.select_for_update()
    directories = list(directory_query)
    directories_by_id = {directory.pk: directory for directory in directories}
    active_ids = _active_snapshot_ids(revision)
    source = _load_directory(
        directories_by_id,
        payload["source"],
        "source",
        active_ids,
    )
    target = None
    if payload["action"] in {"merge", "retire"}:
        target = _load_directory(
            directories_by_id,
            payload["target"],
            "target",
            active_ids,
        )

    descendants = _descendant_ids(
        source.pk,
        [directory for directory in directories if (directory.status == "active" and directory.pk in active_ids)],
    )
    subtree_ids = {source.pk, *descendants}
    members = list(generation.page_members.filter(directory_id__in=subtree_ids).select_related("directory").order_by("page_id"))
    direct_members = [member for member in members if member.directory_id == source.pk]
    descendant_members = [member for member in members if member.directory_id != source.pk]
    child_directories = [
        directory for directory in directories if (directory.status == "active" and directory.parent_id == source.pk and directory.pk in active_ids)
    ]
    conflicts = []
    block_reasons = []

    if source.key == UNCLASSIFIED_DIRECTORY_KEY:
        block_reasons.append(
            _block(
                "system_directory_protected",
                "系统待归类目录不能执行破坏性操作",
            )
        )

    if payload["action"] in {"merge", "retire"}:
        if target.pk == source.pk:
            block_reasons.append(
                _block(
                    "directory_migration_same_target",
                    "源目录与目标目录不能相同",
                )
            )
        if target.pk in descendants:
            block_reasons.append(
                _block(
                    "directory_migration_cycle",
                    "目标目录不能是源目录的后代",
                )
            )
        if not target.accepts_pages:
            block_reasons.append(
                _block(
                    "target_directory_not_assignable",
                    "目标目录不能接收页面",
                )
            )
        target_children_by_name = {
            _normalized_name(directory.name): directory
            for directory in directories
            if (directory.status == "active" and directory.parent_id == target.pk and directory.pk in active_ids and directory.pk != source.pk)
        }
        for child in child_directories:
            target_child = target_children_by_name.get(_normalized_name(child.name))
            if target_child is not None and target_child.pk != child.pk:
                conflicts.append(_conflict(child, target_child))
    else:
        if members:
            block_reasons.append(
                _block(
                    "directory_not_empty",
                    "目录或后代仍包含活动页面",
                )
            )
        if child_directories:
            block_reasons.append(
                _block(
                    "directory_has_active_children",
                    "目录仍包含活动子目录",
                )
            )

    expected_origin = "schema" if payload["action"] == "retire" else "manual" if payload["action"] == "archive" else None
    if expected_origin is not None and source.origin != expected_origin:
        block_reasons.append(
            _block(
                "directory_origin_invalid",
                f"{payload['action']} 仅允许作用于 {expected_origin} 目录",
            )
        )

    redirect = (
        {
            "source": _directory_ref(source),
            "target": _directory_ref(target),
        }
        if target is not None
        else None
    )
    impact = {
        "direct_page_count": len(direct_members),
        "descendant_page_count": len(descendant_members),
        "manual_page_count": sum(member.assignment_mode == "manual" for member in members),
        "child_directory_count": len(child_directories),
        "conflicts": conflicts,
        "block_reasons": block_reasons,
        "redirect": redirect,
    }
    hash_state = {
        "knowledge_base_id": knowledge_base.pk,
        "structure_revision_id": revision.pk,
        "structure_version": revision.revision_no,
        "base_generation_id": generation.pk,
        "action": payload["action"],
        "source": _directory_ref(source),
        "target": (_directory_ref(target) if target is not None else None),
        "members": [
            {
                "page_id": member.page_id,
                "page_version_id": (member.page_version_id),
                "directory_id": (member.directory_id),
                "assignment_mode": (member.assignment_mode),
            }
            for member in members
        ],
        "children": [
            {
                "id": directory.pk,
                "key": directory.key,
                "name": directory.name,
                "parent_id": directory.parent_id,
            }
            for directory in child_directories
        ],
        "conflicts": conflicts,
        "block_reasons": block_reasons,
    }
    canonical = json.dumps(
        hash_state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "knowledge_base": knowledge_base,
        "revision": revision,
        "generation": generation,
        "directories": directories,
        "source": source,
        "target": target,
        "direct_members": direct_members,
        "child_directories": child_directories,
        "impact": impact,
        "impact_hash": hashlib.sha256(canonical).hexdigest(),
        "can_execute": (not conflicts and not block_reasons),
    }


def _binding(state, action):
    binding = {
        "knowledge_base_id": (state["knowledge_base"].pk),
        "structure_version": (state["revision"].revision_no),
        "base_generation_id": (state["generation"].pk),
        "action": action,
        "source": _directory_ref(state["source"]),
        "impact_hash": state["impact_hash"],
    }
    if state["target"] is not None:
        binding["target"] = _directory_ref(state["target"])
    return binding


def preview_directory_operation(
    knowledge_base,
    payload,
):
    _validate_contract(
        payload,
        PREVIEW_REQUEST_SCHEMA,
        request=True,
    )
    state = _operation_state(
        knowledge_base,
        payload,
    )
    binding = _binding(state, payload["action"])
    token_payload = {
        "jti": uuid.uuid4().hex,
        "binding": binding,
    }
    operation_token = signing.dumps(
        token_payload,
        salt=OPERATION_TOKEN_SALT,
        compress=True,
    )
    expires_at = timezone.now() + timedelta(seconds=OPERATION_TOKEN_TTL_SECONDS)
    response = {
        "impact": state["impact"],
        "can_execute": state["can_execute"],
        "impact_hash": state["impact_hash"],
        "operation_token": operation_token,
        "expires_at": (
            expires_at.isoformat().replace(
                "+00:00",
                "Z",
            )
        ),
        "single_use": True,
        "binding": binding,
    }
    _validate_contract(
        response,
        PREVIEW_RESPONSE_SCHEMA,
        request=False,
    )
    return response


def _decode_operation_token(operation_token):
    try:
        payload = signing.loads(
            operation_token,
            salt=OPERATION_TOKEN_SALT,
            max_age=OPERATION_TOKEN_TTL_SECONDS,
        )
    except signing.SignatureExpired as error:
        raise DirectoryServiceError(
            "operation_token_expired",
            "目录操作预览已过期，请重新预览",
            status_code=409,
            retryable=True,
        ) from error
    except signing.BadSignature as error:
        raise DirectoryServiceError(
            "operation_token_invalid",
            "目录操作 token 无效",
            status_code=400,
        ) from error
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("jti"), str)
        or not isinstance(
            payload.get("binding"),
            dict,
        )
    ):
        raise DirectoryServiceError(
            "operation_token_invalid",
            "目录操作 token 载荷无效",
            status_code=400,
        )
    return payload


def _snapshot_after_operation(state, action):
    snapshot = deepcopy(state["revision"].structure_snapshot)
    source_id = state["source"].pk
    target = state["target"]
    next_directories = []
    for node in snapshot["directories"]:
        if node.get("id") == source_id:
            continue
        if action in {"merge", "retire"} and (node.get("parent") or {}).get("id") == source_id:
            node["parent"] = _directory_ref(target)
        next_directories.append(node)
    next_directories.sort(
        key=lambda node: (
            node.get("order", 0),
            node.get("id", 0),
        )
    )
    snapshot["directories"] = next_directories
    return snapshot


def _snapshot_fingerprint(snapshot):
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _breadcrumb(directory_id, directories_by_id):
    result = []
    visited = set()
    current_id = directory_id
    while current_id is not None:
        if current_id in visited:
            raise DirectoryServiceError(
                "directory_cycle",
                "目录父链存在循环",
                details={"directory_id": directory_id},
            )
        visited.add(current_id)
        directory = directories_by_id.get(current_id)
        if directory is None:
            raise DirectoryServiceError(
                "directory_parent_missing",
                "目录父链不完整",
                details={
                    "directory_id": directory_id,
                    "missing_directory_id": (current_id),
                },
            )
        result.append(_directory_ref(directory) | {"name": directory.name})
        current_id = directory.parent_id
    result.reverse()
    return result


def _refresh_candidate_breadcrumbs(
    candidate,
    directories,
):
    directories_by_id = {directory.pk: directory for directory in directories}
    members = list(candidate.page_members.select_related("directory").order_by("id"))
    for member in members:
        member.directory_key_snapshot = member.directory.key
        member.directory_breadcrumb_snapshot = _breadcrumb(
            member.directory_id,
            directories_by_id,
        )
    if members:
        WikiGenerationPage.objects.bulk_update(
            members,
            [
                "directory_key_snapshot",
                "directory_breadcrumb_snapshot",
            ],
            batch_size=500,
        )


def _execute_locked(
    knowledge_base_id,
    request_payload,
    expected_impact_hash,
    *,
    operator,
):
    with transaction.atomic():
        locked = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base_id)
        state = _operation_state(
            locked,
            request_payload,
            lock_directories=True,
        )
        if not state["can_execute"] or state["impact_hash"] != expected_impact_hash:
            raise DirectoryServiceError(
                "directory_operation_stale",
                "目录影响已变化，请重新预览",
                status_code=409,
                retryable=True,
                details={
                    "latest_impact": state["impact"],
                    "latest_impact_hash": (state["impact_hash"]),
                },
            )

        action = request_payload["action"]
        source = state["source"]
        target = state["target"]
        snapshot = _snapshot_after_operation(
            state,
            action,
        )
        fingerprint = _snapshot_fingerprint(snapshot)
        actor = unicodedata.normalize(
            "NFKC",
            str(operator or ""),
        ).strip()[:32]
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
            base_generation=state["generation"],
            rollback_of=None,
            kind="governance",
            structure_fingerprint=fingerprint,
            pipeline_version=(OPERATION_PIPELINE_VERSION),
            source_fingerprints=deepcopy(state["generation"].source_fingerprints or []),
            status="preparing",
            created_by=actor,
            updated_by=actor,
        )

        source.status = {
            "merge": "merged",
            "retire": "retired",
            "archive": "archived",
        }[action]
        source.accepts_pages = False
        source.merged_into = target if action in {"merge", "retire"} else None
        source.updated_by = actor
        source.save(
            update_fields=[
                "status",
                "accepts_pages",
                "merged_into",
                "updated_by",
                "updated_at",
            ]
        )
        if action in {"merge", "retire"}:
            for child in state["child_directories"]:
                child.parent = target
                child.updated_by = actor
                child.save(
                    update_fields=[
                        "parent",
                        "updated_by",
                        "updated_at",
                    ]
                )

        try:
            clone_base_snapshot(candidate.pk)
            changes = []
            if action in {"merge", "retire"}:
                for member in state["direct_members"]:
                    put_generation_member(
                        candidate.pk,
                        page_id=member.page_id,
                        page_version_id=(member.page_version_id),
                        directory_id=target.pk,
                        assignment_mode=(member.assignment_mode),
                        page_status="active",
                        display_snapshot=(member.page_display_snapshot),
                    )
                    changes.append(
                        PageDirectoryChange(
                            page_id=member.page_id,
                            generation=candidate,
                            structure_revision=revision,
                            from_directory=source,
                            to_directory=target,
                            from_assignment_mode=(member.assignment_mode),
                            to_assignment_mode=(member.assignment_mode),
                            source=("structure_merge" if action == "merge" else "structure_retire"),
                            operator=operator,
                            reason=("目录结构合并，保留原归类模式" if action == "merge" else "目录退役迁移，保留原归类模式"),
                            created_by=actor,
                            updated_by=actor,
                        )
                    )
            refreshed_directories = list(WikiDirectory.objects.filter(knowledge_base=locked).order_by("id"))
            _refresh_candidate_breadcrumbs(
                candidate,
                refreshed_directories,
            )
            if changes:
                PageDirectoryChange.objects.bulk_create(
                    changes,
                    batch_size=500,
                )
            mark_generation_ready(candidate.pk)
        except GenerationServiceError as error:
            raise _generation_error(error) from error

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
                candidate.pk,
                requested_base_generation_id=(state["generation"].pk),
                expected_structure_revision_id=(revision.pk),
                expected_structure_version=(revision.revision_no),
            )
        except GenerationServiceError as error:
            raise _generation_error(error) from error
        if activation.outcome != "active":
            raise DirectoryServiceError(
                activation.code,
                "目录治理 generation 激活失败",
                status_code=409,
                retryable=activation.retryable,
                details={"candidate_generation_id": (candidate.pk)},
            )
        result = {
            "structure_revision": {
                "id": revision.pk,
                "version": revision.revision_no,
                "fingerprint": revision.fingerprint,
            },
            "active_generation": {
                "id": candidate.pk,
                "structure_revision_id": (revision.pk),
                "structure_version": (revision.revision_no),
                "status": "active",
            },
            "action_result": {
                "action": action,
                "source": _directory_ref(source),
                "source_status": source.status,
                "redirect": (
                    {
                        "source": (_directory_ref(source)),
                        "target": (_directory_ref(target)),
                    }
                    if target is not None
                    else None
                ),
            },
        }
        if target is not None:
            result["action_result"]["target"] = _directory_ref(target)
        _validate_contract(
            result,
            EXECUTE_RESPONSE_SCHEMA,
            request=False,
        )
        return result


def execute_directory_operation(
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
    token_payload = _decode_operation_token(payload["operation_token"])
    binding = token_payload["binding"]
    knowledge_base_id = getattr(
        knowledge_base,
        "pk",
        knowledge_base,
    )
    request_binding = {
        "knowledge_base_id": knowledge_base_id,
        "structure_version": payload["structure_version"],
        "base_generation_id": payload["base_generation_id"],
        "action": payload["action"],
        "source": payload["source"],
        "impact_hash": payload["impact_hash"],
    }
    if payload["action"] in {"merge", "retire"}:
        request_binding["target"] = payload["target"]
    if binding != request_binding:
        raise DirectoryServiceError(
            "operation_token_binding_mismatch",
            "目录操作参数与预览 token 不一致",
            status_code=409,
            retryable=True,
            details={
                "expected_binding": binding,
                "actual_binding": request_binding,
            },
        )
    consumed_key = "wiki-directory-operation-consumed:" f"{token_payload['jti']}"
    if not cache.add(
        consumed_key,
        True,
        timeout=OPERATION_TOKEN_TTL_SECONDS,
    ):
        raise DirectoryServiceError(
            "operation_token_replayed",
            "目录操作 token 已使用，请重新预览",
            status_code=409,
            retryable=True,
        )
    return _execute_locked(
        knowledge_base_id,
        {
            "structure_version": binding["structure_version"],
            "base_generation_id": binding["base_generation_id"],
            "action": binding["action"],
            "source": binding["source"],
            **({"target": binding["target"]} if "target" in binding else {}),
        },
        binding["impact_hash"],
        operator=operator,
    )


__all__ = [
    "execute_directory_operation",
    "preview_directory_operation",
]
