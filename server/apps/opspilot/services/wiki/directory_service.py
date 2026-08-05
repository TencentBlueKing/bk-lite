"""Wiki directory page-assignment governance operations.

Page moves and automatic re-routing prepare a complete governance generation
outside the final knowledge-base lock. Only the short activation transaction
updates the active pointer, compatibility mirror, and directory-change audit.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from apps.opspilot.models import BuildRecord, KnowledgePage, PageDirectoryChange, WikiDirectory, WikiGeneration, WikiGenerationPage, WikiKnowledgeBase
from apps.opspilot.services.wiki.directory_routing_contract import (
    AssignmentMode,
    DirectoryReferenceSource,
    DirectoryRoutingInvariantError,
    DirectorySnapshot,
    DirectoryStatus,
    route_directory,
)
from apps.opspilot.services.wiki.generation_service import (
    GENERATION_PAGE_ACTIONS_KEY,
    GenerationServiceError,
    activate_generation,
    begin_generation,
    clone_base_snapshot,
    mark_generation_ready,
    put_generation_member,
    remove_generation_member,
)

PAGE_LIFECYCLE_PIPELINE_VERSION = "wiki-page-lifecycle-governance-v1"

UNCLASSIFIED_DIRECTORY_KEY = "__unclassified__"
PAGE_DIRECTORY_PIPELINE_VERSION = "wiki-page-directory-governance-v1"
MAX_BATCH_PAGE_COUNT = 500


class DirectoryServiceError(Exception):
    def __init__(
        self,
        code,
        message,
        *,
        status_code=422,
        retryable=False,
        details=None,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}


@dataclass(frozen=True)
class _PageAssignment:
    member: WikiGenerationPage
    target: WikiDirectory
    mode: str
    source: str
    reason: str


class _ActivationRejected(Exception):
    def __init__(self, activation):
        super().__init__(activation.code)
        self.activation = activation


def _positive_int(value, field):
    if isinstance(value, bool):
        raise DirectoryServiceError(
            f"{field}_invalid",
            f"{field} 必须为正整数",
            status_code=400,
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise DirectoryServiceError(
            f"{field}_invalid",
            f"{field} 必须为正整数",
            status_code=400,
        ) from error
    if parsed <= 0:
        raise DirectoryServiceError(
            f"{field}_invalid",
            f"{field} 必须为正整数",
            status_code=400,
        )
    return parsed


def _page_ids(values):
    if not isinstance(values, list) or not values:
        raise DirectoryServiceError(
            "page_ids_required",
            "page_ids 不能为空",
            status_code=400,
        )
    result = []
    seen = set()
    for value in values:
        page_id = _positive_int(value, "page_id")
        if page_id not in seen:
            result.append(page_id)
            seen.add(page_id)
    if len(result) > MAX_BATCH_PAGE_COUNT:
        raise DirectoryServiceError(
            "page_batch_too_large",
            f"单次最多治理 {MAX_BATCH_PAGE_COUNT} 个页面",
            status_code=400,
            details={"limit": MAX_BATCH_PAGE_COUNT, "actual": len(result)},
        )
    return result


def _generation_error(error):
    conflict_codes = {
        "base_generation_conflict",
        "structure_revision_conflict",
        "structure_version_conflict",
    }
    is_conflict = error.code in conflict_codes or error.retryable
    return DirectoryServiceError(
        error.code,
        str(error),
        status_code=409 if is_conflict else 422,
        retryable=is_conflict,
        details=error.details,
    )


def _active_pair(
    knowledge_base,
    *,
    base_generation_id,
    structure_version,
):
    current = WikiKnowledgeBase.objects.select_related(
        "active_generation",
        "active_structure_revision",
    ).get(pk=getattr(knowledge_base, "pk", knowledge_base))
    revision = current.active_structure_revision
    generation = current.active_generation
    if revision is None or generation is None or generation.status != "active":
        raise DirectoryServiceError(
            "active_snapshot_missing",
            "知识库缺少可治理的 active structure/generation",
            status_code=409,
            retryable=True,
        )
    if generation.structure_revision_id != revision.pk:
        raise DirectoryServiceError(
            "active_snapshot_mismatch",
            "active structure/generation 指针不一致",
            status_code=409,
            retryable=True,
            details={
                "active_structure_revision_id": revision.pk,
                "active_generation_id": generation.pk,
                "generation_structure_revision_id": (generation.structure_revision_id),
            },
        )
    if generation.pk != base_generation_id:
        raise DirectoryServiceError(
            "base_generation_conflict",
            "active generation 已变化",
            status_code=409,
            retryable=True,
            details={
                "expected": base_generation_id,
                "actual": generation.pk,
            },
        )
    if revision.revision_no != structure_version:
        raise DirectoryServiceError(
            "structure_version_conflict",
            "active structure revision 已变化",
            status_code=409,
            retryable=True,
            details={
                "expected": structure_version,
                "actual": revision.revision_no,
            },
        )
    return current, revision, generation


def _active_members(generation, page_ids):
    members = list(generation.page_members.filter(page_id__in=page_ids).select_related("page", "page_version", "directory").order_by("page_id"))
    members_by_page_id = {member.page_id: member for member in members}
    missing = [page_id for page_id in page_ids if page_id not in members_by_page_id]
    if missing:
        raise DirectoryServiceError(
            "page_not_in_active_generation",
            "部分页面不属于当前活动知识集合",
            details={"page_ids": missing},
        )
    invalid = [member.page_id for member in members if member.page_status != "active"]
    if invalid:
        raise DirectoryServiceError(
            "active_member_status_invalid",
            "当前 generation 包含非 active 页面成员",
            details={"page_ids": invalid},
        )
    return [members_by_page_id[page_id] for page_id in page_ids]


def _snapshot_rules(revision):
    snapshot = revision.structure_snapshot or {}
    directories = snapshot.get("directories")
    if snapshot.get("format_version") != 1 or not isinstance(directories, list):
        raise DirectoryServiceError(
            "structure_snapshot_invalid",
            "active structure snapshot 不是受支持的完整结构格式",
            details={"structure_revision_id": revision.pk},
        )
    rules_by_key = {node.get("key"): node.get("rules") or {} for node in directories if (isinstance(node, dict) and isinstance(node.get("key"), str))}
    return snapshot, rules_by_key


def _directory_ancestor_keys(directory, directories_by_id):
    result = []
    visited = {directory.pk}
    parent_id = directory.parent_id
    while parent_id is not None:
        if parent_id in visited:
            raise DirectoryServiceError(
                "directory_cycle",
                "目录父链存在循环",
                details={"directory_id": directory.pk},
            )
        visited.add(parent_id)
        parent = directories_by_id.get(parent_id)
        if parent is None:
            raise DirectoryServiceError(
                "directory_parent_missing",
                "目录父链缺少同知识库节点",
                details={
                    "directory_id": directory.pk,
                    "parent_id": parent_id,
                },
            )
        result.append(parent.key)
        parent_id = parent.parent_id
    result.reverse()
    return tuple(result)


def _routing_snapshot(knowledge_base, revision):
    snapshot, rules_by_key = _snapshot_rules(revision)
    rows = list(WikiDirectory.objects.filter(knowledge_base=knowledge_base).select_related("merged_into").order_by("id"))
    rows_by_id = {row.pk: row for row in rows}
    directories = {}
    for row in rows:
        rules = rules_by_key.get(row.key) or {}
        allowed = rules.get("allowed_page_types")
        try:
            status = DirectoryStatus(row.status)
            directories[row.key] = DirectorySnapshot(
                key=row.key,
                knowledge_base_id=knowledge_base.pk,
                status=status,
                accepts_pages=row.accepts_pages,
                ancestor_keys=_directory_ancestor_keys(row, rows_by_id),
                merged_into_key=(row.merged_into.key if row.merged_into_id else None),
                allowed_page_types=(frozenset(allowed) if isinstance(allowed, list) and allowed else None),
                is_unclassified=(row.key == UNCLASSIFIED_DIRECTORY_KEY),
            )
        except (ValueError, DirectoryRoutingInvariantError) as error:
            raise DirectoryServiceError(
                "directory_projection_invalid",
                "目录投影不满足自动路由契约",
                details={
                    "directory_id": row.pk,
                    "status": row.status,
                },
            ) from error
    page_types = snapshot.get("page_types")
    if not isinstance(page_types, list) or not all(isinstance(value, str) and value for value in page_types):
        raise DirectoryServiceError(
            "structure_page_types_invalid",
            "active structure 缺少合法 page_types",
            details={"structure_revision_id": revision.pk},
        )
    return (
        snapshot,
        rows,
        directories,
        frozenset(page_types),
    )


def _page_type(member):
    display = member.page_display_snapshot or {}
    value = display.get("page_type") or member.page.page_type
    return value if isinstance(value, str) else ""


def _allowed_by_target(target, page_type, rules_by_key):
    rules = rules_by_key.get(target.key) or {}
    allowed = rules.get("allowed_page_types")
    return not isinstance(allowed, list) or not allowed or page_type in allowed


def _prepare_candidate(
    knowledge_base,
    revision,
    base_generation,
    assignments,
    operator,
):
    candidate = None
    try:
        candidate = begin_generation(
            knowledge_base=knowledge_base,
            kind="governance",
            base_generation_id=base_generation.pk,
            structure_revision_id=revision.pk,
            pipeline_version=PAGE_DIRECTORY_PIPELINE_VERSION,
            source_fingerprints=list(base_generation.source_fingerprints or []),
            operator=operator,
        )
        clone_base_snapshot(candidate.pk)
        for assignment in assignments:
            put_generation_member(
                candidate.pk,
                page_id=assignment.member.page_id,
                page_version_id=assignment.member.page_version_id,
                directory_id=assignment.target.pk,
                assignment_mode=assignment.mode,
                page_status="active",
                display_snapshot=(assignment.member.page_display_snapshot),
            )
        mark_generation_ready(candidate.pk)
        return candidate
    except GenerationServiceError as error:
        if candidate is not None:
            WikiGeneration.objects.filter(
                pk=candidate.pk,
                status__in=("preparing", "ready"),
            ).update(status="failed")
        raise _generation_error(error) from error
    except Exception:
        if candidate is not None:
            WikiGeneration.objects.filter(
                pk=candidate.pk,
                status__in=("preparing", "ready"),
            ).update(status="failed")
        raise


def _activate_with_audit(
    candidate,
    assignments,
    *,
    operator,
    base_generation_id,
    revision,
):
    try:
        with transaction.atomic():
            PageDirectoryChange.objects.bulk_create(
                [
                    PageDirectoryChange(
                        page_id=assignment.member.page_id,
                        generation=candidate,
                        structure_revision=revision,
                        from_directory_id=(assignment.member.directory_id),
                        to_directory=assignment.target,
                        from_assignment_mode=(assignment.member.assignment_mode),
                        to_assignment_mode=assignment.mode,
                        source=assignment.source,
                        operator=operator,
                        reason=assignment.reason,
                        created_by=operator,
                        updated_by=operator,
                    )
                    for assignment in assignments
                ],
                batch_size=500,
            )
            activation = activate_generation(
                candidate.pk,
                requested_base_generation_id=base_generation_id,
                expected_structure_revision_id=revision.pk,
                expected_structure_version=revision.revision_no,
            )
            if activation.outcome != "active":
                raise _ActivationRejected(activation)
    except _ActivationRejected as error:
        WikiGeneration.objects.filter(pk=candidate.pk).update(status="superseded")
        raise DirectoryServiceError(
            error.activation.code,
            "页面目录治理 generation 激活失败",
            status_code=409,
            retryable=error.activation.retryable,
            details={
                "candidate_generation_id": candidate.pk,
                "base_generation_id": base_generation_id,
                "active_generation_id": (error.activation.active_generation_id),
            },
        ) from error
    except GenerationServiceError as error:
        WikiGeneration.objects.filter(
            pk=candidate.pk,
            status__in=("preparing", "ready"),
        ).update(status="failed")
        raise _generation_error(error) from error
    return activation


def _result(
    knowledge_base,
    revision,
    activation,
    assignments,
):
    knowledge_base.refresh_from_db(fields=["active_generation"])
    return {
        "generation_id": activation.candidate_generation_id,
        "previous_generation_id": (activation.previous_generation_id),
        "active_generation_id": (knowledge_base.active_generation_id),
        "structure_revision_id": revision.pk,
        "structure_version": revision.revision_no,
        "changed": len(assignments),
        "pages": [
            {
                "id": assignment.member.page_id,
                "directory_id": assignment.target.pk,
                "directory_key": assignment.target.key,
                "directory_assignment_mode": assignment.mode,
                "source": assignment.source,
            }
            for assignment in assignments
        ],
    }


def _no_change_result(base_generation, revision):
    return {
        "generation_id": base_generation.pk,
        "previous_generation_id": None,
        "active_generation_id": base_generation.pk,
        "structure_revision_id": revision.pk,
        "structure_version": revision.revision_no,
        "changed": 0,
        "pages": [],
    }


def move_pages(
    knowledge_base,
    *,
    page_ids,
    target_directory_id,
    base_generation_id,
    structure_version,
    operator="",
):
    """Move active pages and publish a manual-lock snapshot."""

    parsed_page_ids = _page_ids(page_ids)
    target_directory_id = _positive_int(
        target_directory_id,
        "target_directory_id",
    )
    base_generation_id = _positive_int(
        base_generation_id,
        "base_generation_id",
    )
    structure_version = _positive_int(
        structure_version,
        "structure_version",
    )
    knowledge_base, revision, base_generation = _active_pair(
        knowledge_base,
        base_generation_id=base_generation_id,
        structure_version=structure_version,
    )
    snapshot, rules_by_key = _snapshot_rules(revision)
    target = WikiDirectory.objects.filter(
        pk=target_directory_id,
        knowledge_base=knowledge_base,
        status="active",
        accepts_pages=True,
    ).first()
    snapshot_has_target = any((isinstance(node, dict) and node.get("id") == target_directory_id) for node in snapshot["directories"])
    if target is None or not snapshot_has_target:
        raise DirectoryServiceError(
            "directory_not_assignable",
            "目标目录不属于当前活动结构或不可接收页面",
            details={"directory_id": target_directory_id},
        )
    members = _active_members(
        base_generation,
        parsed_page_ids,
    )
    invalid_page_ids = [
        member.page_id
        for member in members
        if not _allowed_by_target(
            target,
            _page_type(member),
            rules_by_key,
        )
    ]
    if invalid_page_ids:
        raise DirectoryServiceError(
            "directory_page_type_mismatch",
            "目标目录不允许部分页面的 page_type",
            details={
                "directory_id": target.pk,
                "page_ids": invalid_page_ids,
            },
        )
    assignments = [
        _PageAssignment(
            member=member,
            target=target,
            mode=AssignmentMode.MANUAL.value,
            source="manual_move",
            reason="管理员手工移动页面",
        )
        for member in members
        if (member.directory_id != target.pk or member.assignment_mode != AssignmentMode.MANUAL.value)
    ]
    if not assignments:
        return _no_change_result(base_generation, revision)
    candidate = _prepare_candidate(
        knowledge_base,
        revision,
        base_generation,
        assignments,
        operator,
    )
    activation = _activate_with_audit(
        candidate,
        assignments,
        operator=operator,
        base_generation_id=base_generation.pk,
        revision=revision,
    )
    return _result(
        knowledge_base,
        revision,
        activation,
        assignments,
    )


def restore_pages_auto(
    knowledge_base,
    *,
    page_ids,
    base_generation_id,
    structure_version,
    operator="",
):
    """Restore manual pages to deterministic auto routing."""

    parsed_page_ids = _page_ids(page_ids)
    base_generation_id = _positive_int(
        base_generation_id,
        "base_generation_id",
    )
    structure_version = _positive_int(
        structure_version,
        "structure_version",
    )
    knowledge_base, revision, base_generation = _active_pair(
        knowledge_base,
        base_generation_id=base_generation_id,
        structure_version=structure_version,
    )
    (
        snapshot,
        rows,
        directories,
        page_types,
    ) = _routing_snapshot(knowledge_base, revision)
    rows_by_key = {row.key: row for row in rows}
    members = _active_members(
        base_generation,
        parsed_page_ids,
    )
    assignments = []
    for member in members:
        page_type = _page_type(member)
        defaults = [
            node.get("key")
            for node in snapshot["directories"]
            if (isinstance(node, dict) and page_type in ((node.get("rules") or {}).get("default_for_page_types") or []))
        ]
        try:
            decision = route_directory(
                knowledge_base_id=knowledge_base.pk,
                page_type=page_type,
                revision_page_types=page_types,
                assignment_mode=AssignmentMode.AUTO,
                directories=directories,
                current_directory_key=(member.directory_key_snapshot),
                suggested_key=None,
                suggestion_source=(DirectoryReferenceSource.LLM),
                classification_root_key=None,
                type_default_keys=defaults,
                unclassified_key=(UNCLASSIFIED_DIRECTORY_KEY),
                suggestion_schema_mismatch=False,
                low_confidence=False,
            )
        except DirectoryRoutingInvariantError as error:
            raise DirectoryServiceError(
                "directory_routing_invalid",
                str(error),
                details={"page_id": member.page_id},
            ) from error
        target = rows_by_key.get(decision.directory_key)
        if target is None:
            raise DirectoryServiceError(
                "directory_routing_target_missing",
                "自动归类结果缺少规范化目录投影",
                details={
                    "page_id": member.page_id,
                    "directory_key": decision.directory_key,
                },
            )
        if member.directory_id == target.pk and member.assignment_mode == AssignmentMode.AUTO.value:
            continue
        trace = ",".join(code.value for code in decision.trace)
        assignments.append(
            _PageAssignment(
                member=member,
                target=target,
                mode=AssignmentMode.AUTO.value,
                source="restore_auto",
                reason=("恢复自动归类: " f"{decision.source.value}; trace={trace}"),
            )
        )
    if not assignments:
        return _no_change_result(base_generation, revision)
    candidate = _prepare_candidate(
        knowledge_base,
        revision,
        base_generation,
        assignments,
        operator,
    )
    activation = _activate_with_audit(
        candidate,
        assignments,
        operator=operator,
        base_generation_id=base_generation.pk,
        revision=revision,
    )
    return _result(
        knowledge_base,
        revision,
        activation,
        assignments,
    )


def _page_lifecycle_record(
    knowledge_base,
    trigger,
    page_ids,
    *,
    operator,
    actions=None,
):
    return BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger=trigger,
        operator=operator or "",
        inputs={
            "base_generation_id": knowledge_base.active_generation_id,
            "structure_revision_id": (knowledge_base.active_structure_revision_id),
        },
        stage="generation_preparing",
        progress=0,
        counts={},
        affected_pages=list(page_ids),
        errors=[],
        maintenance={
            GENERATION_PAGE_ACTIONS_KEY: list(actions or []),
        },
        status="running",
        created_by=operator or "",
        updated_by=operator or "",
    )


def _finish_page_lifecycle_record(
    record,
    *,
    candidate,
    activation,
    counts,
):
    maintenance = dict(record.maintenance or {})
    maintenance.update(
        {
            "generation_id": candidate.pk,
            "base_generation_id": candidate.base_generation_id,
            "structure_revision_id": candidate.structure_revision_id,
            "structure_fingerprint": candidate.structure_fingerprint,
            "pipeline_version": candidate.pipeline_version,
            "activation": activation.outcome,
        }
    )
    record.maintenance = maintenance
    record.counts = counts
    record.stage = "completed"
    record.progress = 100
    record.status = "success"
    record.save(
        update_fields=[
            "maintenance",
            "counts",
            "stage",
            "progress",
            "status",
            "updated_at",
        ]
    )


def archive_pages(
    knowledge_base,
    *,
    page_ids,
    base_generation_id,
    structure_version,
    operator="",
):
    """Logically remove pages through a rollback-safe governance generation."""

    parsed_page_ids = _page_ids(page_ids)
    knowledge_base, revision, base_generation = _active_pair(
        knowledge_base,
        base_generation_id=_positive_int(
            base_generation_id,
            "base_generation_id",
        ),
        structure_version=_positive_int(
            structure_version,
            "structure_version",
        ),
    )
    members = _active_members(
        base_generation,
        parsed_page_ids,
    )
    record = _page_lifecycle_record(
        knowledge_base,
        "page_archive",
        parsed_page_ids,
        operator=operator,
        actions=[
            {
                "page_id": member.page_id,
                "action": "archive",
                "target_status": "archived",
            }
            for member in members
        ],
    )
    candidate = None
    try:
        candidate = begin_generation(
            knowledge_base=knowledge_base,
            kind="governance",
            base_generation_id=base_generation.pk,
            structure_revision_id=revision.pk,
            pipeline_version=PAGE_LIFECYCLE_PIPELINE_VERSION,
            source_fingerprints=list(base_generation.source_fingerprints or []),
            build_record=record,
            operator=operator,
        )
        clone_base_snapshot(candidate.pk)
        for member in members:
            remove_generation_member(
                candidate.pk,
                page_id=member.page_id,
            )
        mark_generation_ready(candidate.pk)
        activation = _activate_with_audit(
            candidate,
            [],
            operator=operator,
            base_generation_id=base_generation.pk,
            revision=revision,
        )
    except Exception as error:
        record.status = "failed"
        record.stage = "failed"
        record.progress = 100
        record.errors = [str(error)]
        record.save(
            update_fields=[
                "status",
                "stage",
                "progress",
                "errors",
                "updated_at",
            ]
        )
        raise
    _finish_page_lifecycle_record(
        record,
        candidate=candidate,
        activation=activation,
        counts={"archived": len(members)},
    )
    result = _result(
        knowledge_base,
        revision,
        activation,
        [],
    )
    result.update(
        {
            "changed": len(members),
            "pages": [{"id": member.page_id, "status": "archived"} for member in members],
            "build_record_id": record.pk,
        }
    )
    return result


def _restorable_member(page, current_generation):
    return (
        WikiGenerationPage.objects.filter(
            page=page,
            generation__knowledge_base_id=(current_generation.knowledge_base_id),
            generation__status__in=("active", "superseded"),
        )
        .exclude(generation=current_generation)
        .select_related(
            "generation",
            "page_version",
            "directory",
            "page",
        )
        .order_by("-generation_id", "-id")
        .first()
    )


def restore_archived_pages(
    knowledge_base,
    *,
    page_ids,
    base_generation_id,
    structure_version,
    operator="",
):
    """Restore archived identities from retained versions into a new generation."""

    parsed_page_ids = _page_ids(page_ids)
    knowledge_base, revision, base_generation = _active_pair(
        knowledge_base,
        base_generation_id=_positive_int(
            base_generation_id,
            "base_generation_id",
        ),
        structure_version=_positive_int(
            structure_version,
            "structure_version",
        ),
    )
    pages = {
        page.pk: page
        for page in KnowledgePage.objects.filter(
            knowledge_base=knowledge_base,
            pk__in=parsed_page_ids,
        )
    }
    missing = [page_id for page_id in parsed_page_ids if page_id not in pages]
    invalid = [page_id for page_id, page in pages.items() if page.status != "archived"]
    if missing or invalid:
        raise DirectoryServiceError(
            "page_not_archived",
            "只有同知识库的已归档页面可以恢复",
            details={
                "missing_page_ids": missing,
                "invalid_page_ids": invalid,
            },
        )

    snapshot, rows, directories, page_types = _routing_snapshot(
        knowledge_base,
        revision,
    )
    rows_by_key = {row.key: row for row in rows}
    assignments = []
    for page_id in parsed_page_ids:
        page = pages[page_id]
        member = _restorable_member(page, base_generation)
        if member is None:
            raise DirectoryServiceError(
                "retained_page_snapshot_missing",
                "已归档页面缺少可恢复的历史 generation 快照",
                details={"page_id": page_id},
            )
        current = rows_by_key.get(member.directory_key_snapshot)
        if current is not None and current.status == "active" and current.accepts_pages:
            target = current
            mode = member.assignment_mode
            source = "archive_restore"
            reason = "从 retained generation 恢复原目录"
        elif member.assignment_mode == AssignmentMode.MANUAL.value:
            raise DirectoryServiceError(
                "manual_directory_not_restorable",
                "人工归类页面的历史目录已不可用，请先恢复目录结构",
                details={
                    "page_id": page_id,
                    "directory_key": (member.directory_key_snapshot),
                },
            )
        else:
            page_type = _page_type(member)
            defaults = [
                node.get("key") for node in snapshot["directories"] if page_type in ((node.get("rules") or {}).get("default_for_page_types") or [])
            ]
            try:
                decision = route_directory(
                    knowledge_base_id=knowledge_base.pk,
                    page_type=page_type,
                    revision_page_types=page_types,
                    assignment_mode=AssignmentMode.AUTO,
                    directories=directories,
                    current_directory_key=(member.directory_key_snapshot),
                    suggested_key=(member.directory_key_snapshot),
                    suggestion_source=(DirectoryReferenceSource.HISTORICAL_LINK),
                    classification_root_key=None,
                    type_default_keys=defaults,
                    unclassified_key=UNCLASSIFIED_DIRECTORY_KEY,
                    suggestion_schema_mismatch=False,
                    low_confidence=False,
                )
            except DirectoryRoutingInvariantError as error:
                raise DirectoryServiceError(
                    "directory_routing_invalid",
                    str(error),
                    details={"page_id": page_id},
                ) from error
            target = rows_by_key.get(decision.directory_key)
            if target is None:
                raise DirectoryServiceError(
                    "directory_routing_target_missing",
                    "恢复归类结果缺少目录投影",
                    details={
                        "page_id": page_id,
                        "directory_key": decision.directory_key,
                    },
                )
            mode = decision.assignment_mode.value
            source = "archive_restore_routed"
            reason = ",".join(code.value for code in decision.trace) or decision.source.value
        assignments.append(
            _PageAssignment(
                member=member,
                target=target,
                mode=mode,
                source=source,
                reason=reason,
            )
        )

    record = _page_lifecycle_record(
        knowledge_base,
        "page_restore_archive",
        parsed_page_ids,
        operator=operator,
    )
    candidate = None
    try:
        candidate = begin_generation(
            knowledge_base=knowledge_base,
            kind="governance",
            base_generation_id=base_generation.pk,
            structure_revision_id=revision.pk,
            pipeline_version=PAGE_LIFECYCLE_PIPELINE_VERSION,
            source_fingerprints=list(base_generation.source_fingerprints or []),
            build_record=record,
            operator=operator,
        )
        clone_base_snapshot(candidate.pk)
        for assignment in assignments:
            put_generation_member(
                candidate.pk,
                page_id=assignment.member.page_id,
                page_version_id=(assignment.member.page_version_id),
                directory_id=assignment.target.pk,
                assignment_mode=assignment.mode,
                page_status="active",
                display_snapshot=(assignment.member.page_display_snapshot),
            )
        mark_generation_ready(candidate.pk)
        activation = _activate_with_audit(
            candidate,
            assignments,
            operator=operator,
            base_generation_id=base_generation.pk,
            revision=revision,
        )
    except Exception as error:
        record.status = "failed"
        record.stage = "failed"
        record.progress = 100
        record.errors = [str(error)]
        record.save(
            update_fields=[
                "status",
                "stage",
                "progress",
                "errors",
                "updated_at",
            ]
        )
        raise
    _finish_page_lifecycle_record(
        record,
        candidate=candidate,
        activation=activation,
        counts={"restored": len(assignments)},
    )
    result = _result(
        knowledge_base,
        revision,
        activation,
        assignments,
    )
    result["build_record_id"] = record.pk
    return result


__all__ = [
    "DirectoryServiceError",
    "archive_pages",
    "move_pages",
    "restore_pages_auto",
    "restore_archived_pages",
]
