"""Generation candidate preparation, validation, and atomic activation.

All public mutating functions acquire locks in knowledge-base then generation or
page order. Long-running generation work happens outside the activation
transaction; only validation, compatibility mirror refresh, and pointer switch
run while the knowledge-base row is locked.
"""

import logging
from dataclasses import dataclass

from django.db import transaction

from apps.opspilot.models import (
    BuildRecord,
    KnowledgePage,
    PageRelation,
    PageVersion,
    WikiDirectory,
    WikiGeneration,
    WikiGenerationPage,
    WikiKnowledgeBase,
    WikiStructureRevision,
)
from apps.opspilot.services.wiki.generation_consistency_contract import ActivationFacts, ActivationOutcome, decide_activation
from apps.opspilot.services.wiki.title_service import title_identity_key

ACTIVE_GENERATION_PAGE_STATUS = "active"
logger = logging.getLogger("opspilot")
GENERATION_PAGE_ACTIONS_KEY = "generation_page_actions"
GENERATION_PAGE_ACTION_STATUSES = {
    "archive": "archived",
    "source_invalid": "source_invalid",
}


class GenerationServiceError(Exception):
    """Stable service error suitable for API and task result mapping."""

    def __init__(self, code, message, *, retryable=False, details=None):
        self.code = str(code)
        self.retryable = bool(retryable)
        self.details = dict(details or {})
        super().__init__(message)


@dataclass(frozen=True)
class GenerationActivationResult:
    candidate_generation_id: int
    previous_generation_id: int | None
    active_generation_id: int | None
    outcome: str
    code: str
    retryable: bool


def _non_empty(value, field_name):
    normalized = str(value or "").strip()
    if not normalized:
        raise GenerationServiceError(
            "generation_invalid_argument",
            f"{field_name} 不能为空",
            details={"field": field_name},
        )
    return normalized


def _candidate_lock_order(candidate_id):
    candidate_identity = WikiGeneration.objects.filter(pk=candidate_id).values("id", "knowledge_base_id").first()
    if candidate_identity is None:
        raise GenerationServiceError(
            "generation_not_found",
            "generation 不存在",
            details={"generation_id": candidate_id},
        )
    knowledge_base = WikiKnowledgeBase.objects.select_for_update().get(pk=candidate_identity["knowledge_base_id"])
    candidate = WikiGeneration.objects.select_for_update().select_related("structure_revision").get(pk=candidate_id, knowledge_base=knowledge_base)
    return knowledge_base, candidate


def _require_candidate_status(candidate, *statuses):
    if candidate.status not in statuses:
        raise GenerationServiceError(
            "generation_status_conflict",
            "generation 当前状态不允许该操作",
            details={
                "generation_id": candidate.pk,
                "status": candidate.status,
                "allowed": list(statuses),
            },
        )


def _directory_breadcrumb(directory):
    rows = {
        row["id"]: row for row in WikiDirectory.objects.filter(knowledge_base_id=directory.knowledge_base_id).values("id", "key", "name", "parent_id")
    }
    breadcrumb = []
    current_id = directory.pk
    visited = set()
    while current_id is not None:
        if current_id in visited:
            raise GenerationServiceError(
                "directory_cycle",
                "目录父链存在循环",
                details={"directory_id": directory.pk},
            )
        visited.add(current_id)
        row = rows.get(current_id)
        if row is None:
            raise GenerationServiceError(
                "directory_parent_missing",
                "目录父链不完整",
                details={"directory_id": directory.pk, "missing_id": current_id},
            )
        breadcrumb.append({"id": row["id"], "key": row["key"], "name": row["name"]})
        current_id = row["parent_id"]
    breadcrumb.reverse()
    return breadcrumb


def _page_display_snapshot(page, extra=None):
    snapshot = {
        "title": page.title,
        "page_type": page.page_type,
        "tags": list(page.tags or []),
        "contribution": page.contribution,
        "update_method": page.update_method,
        "created_by": page.created_by,
        "updated_by": page.updated_by,
        "created_at": page.created_at.isoformat() if page.created_at else None,
        "updated_at": page.updated_at.isoformat() if page.updated_at else None,
    }
    snapshot.update(dict(extra or {}))

    return snapshot


def _page_version_source_issue(
    candidate,
    *,
    page,
    version,
    base_page_versions,
    rollback_page_versions,
):
    if version.created_in_generation_id == candidate.pk:
        if version.is_current:
            return {
                "code": "candidate_page_version_is_current",
                "page_id": page.pk,
                "page_version_id": version.pk,
            }
        return None

    if candidate.base_generation_id is None:
        if version.created_in_generation_id is None and page.current_version_id == version.pk and version.is_current:
            return None
        return {
            "code": "baseline_page_version_not_current_mirror",
            "page_id": page.pk,
            "page_version_id": version.pk,
        }

    if base_page_versions.get(page.pk) == version.pk:
        return None
    if candidate.kind == "rollback" and rollback_page_versions.get(page.pk) == version.pk:
        return None
    if (
        candidate.kind == "governance"
        and WikiGenerationPage.objects.filter(
            generation__knowledge_base_id=candidate.knowledge_base_id,
            generation__status__in=("active", "superseded"),
            page=page,
            page_version=version,
        ).exists()
    ):
        return None
    return {
        "code": "page_version_source_invalid",
        "page_id": page.pk,
        "page_version_id": version.pk,
        "created_in_generation_id": version.created_in_generation_id,
    }


def _generation_page_actions(candidate):
    """Read explicit removals from transitional build metadata.

    This is intentionally strict and namespaced. A future generation-owned
    action model can replace this bridge without overloading affected_pages.
    """

    issues = []
    actions = {}
    maintenance = candidate.build_record.maintenance if candidate.build_record_id is not None else {}
    if not isinstance(maintenance, dict):
        maintenance = {}
    raw_actions = maintenance.get(GENERATION_PAGE_ACTIONS_KEY)
    if raw_actions is None:
        return actions, issues
    if not isinstance(raw_actions, list):
        return actions, [{"code": "generation_page_actions_invalid"}]

    for index, raw_action in enumerate(raw_actions):
        if not isinstance(raw_action, dict):
            issues.append(
                {
                    "code": "generation_page_action_invalid",
                    "index": index,
                }
            )
            continue
        page_id = raw_action.get("page_id")
        action = raw_action.get("action")
        target_status = GENERATION_PAGE_ACTION_STATUSES.get(action)
        if (
            isinstance(page_id, bool)
            or not isinstance(page_id, int)
            or page_id <= 0
            or target_status is None
            or (raw_action.get("target_status") is not None and raw_action.get("target_status") != target_status)
        ):
            issues.append(
                {
                    "code": "generation_page_action_invalid",
                    "index": index,
                    "page_id": page_id,
                    "action": action,
                }
            )
            continue
        if page_id in actions:
            issues.append(
                {
                    "code": "generation_page_action_duplicate",
                    "page_id": page_id,
                }
            )
            continue
        actions[page_id] = target_status
    return actions, issues


def _candidate_validation_issues(candidate):  # noqa: C901
    issues = []
    if candidate.structure_revision.knowledge_base_id != candidate.knowledge_base_id:
        issues.append(
            {
                "code": "structure_knowledge_base_mismatch",
                "structure_revision_id": candidate.structure_revision_id,
            }
        )
    if candidate.structure_fingerprint != candidate.structure_revision.fingerprint:
        issues.append(
            {
                "code": "structure_fingerprint_mismatch",
                "expected": candidate.structure_revision.fingerprint,
                "actual": candidate.structure_fingerprint,
            }
        )
    if candidate.base_generation_id is not None and candidate.base_generation.knowledge_base_id != candidate.knowledge_base_id:
        issues.append(
            {
                "code": "base_generation_knowledge_base_mismatch",
                "base_generation_id": candidate.base_generation_id,
            }
        )
    if candidate.rollback_of_id is not None and candidate.rollback_of.knowledge_base_id != candidate.knowledge_base_id:
        issues.append(
            {
                "code": "rollback_generation_knowledge_base_mismatch",
                "rollback_of_id": candidate.rollback_of_id,
            }
        )

    title_owners = {}
    page_ids = set()
    base_page_versions = (
        dict(candidate.base_generation.page_members.values_list("page_id", "page_version_id")) if candidate.base_generation_id is not None else {}
    )
    rollback_page_versions = (
        dict(candidate.rollback_of.page_members.values_list("page_id", "page_version_id"))
        if candidate.kind == "rollback" and candidate.rollback_of_id is not None
        else {}
    )
    page_actions, action_issues = _generation_page_actions(candidate)
    issues.extend(action_issues)
    members = list(
        candidate.page_members.select_related(
            "page",
            "page_version",
            "directory",
        ).order_by("id")
    )
    for member in members:
        page_ids.add(member.page_id)
        if member.page.knowledge_base_id != candidate.knowledge_base_id:
            issues.append(
                {
                    "code": "page_knowledge_base_mismatch",
                    "page_id": member.page_id,
                }
            )
        if member.page_version.page_id != member.page_id:
            issues.append(
                {
                    "code": "page_version_owner_mismatch",
                    "page_id": member.page_id,
                    "page_version_id": member.page_version_id,
                }
            )
        version_source_issue = _page_version_source_issue(
            candidate,
            page=member.page,
            version=member.page_version,
            base_page_versions=base_page_versions,
            rollback_page_versions=rollback_page_versions,
        )
        if version_source_issue is not None:
            issues.append(version_source_issue)
        if member.directory.knowledge_base_id != candidate.knowledge_base_id:
            issues.append(
                {
                    "code": "directory_knowledge_base_mismatch",
                    "page_id": member.page_id,
                    "directory_id": member.directory_id,
                }
            )
        if member.directory.status != "active" or not member.directory.accepts_pages:
            issues.append(
                {
                    "code": "directory_not_assignable",
                    "page_id": member.page_id,
                    "directory_id": member.directory_id,
                    "directory_status": member.directory.status,
                }
            )
        if member.directory_key_snapshot != member.directory.key:
            issues.append(
                {
                    "code": "directory_key_snapshot_mismatch",
                    "page_id": member.page_id,
                    "directory_id": member.directory_id,
                }
            )
        if member.assignment_mode not in {choice[0] for choice in KnowledgePage.DIRECTORY_ASSIGNMENT_MODES}:
            issues.append(
                {
                    "code": "assignment_mode_invalid",
                    "page_id": member.page_id,
                    "assignment_mode": member.assignment_mode,
                }
            )
        if member.page_status != ACTIVE_GENERATION_PAGE_STATUS:
            issues.append(
                {
                    "code": "page_status_invalid",
                    "page_id": member.page_id,
                    "page_status": member.page_status,
                }
            )
        title = (member.page_display_snapshot or {}).get("title") or member.page.title
        identity = title_identity_key(title)
        if not identity:
            issues.append({"code": "page_title_empty", "page_id": member.page_id})
        elif identity in title_owners:
            issues.append(
                {
                    "code": "page_title_conflict",
                    "page_id": member.page_id,
                    "conflict_page_id": title_owners[identity],
                    "title_identity": identity,
                }
            )
        else:
            title_owners[identity] = member.page_id

    for page in KnowledgePage.objects.filter(knowledge_base_id=candidate.knowledge_base_id).exclude(pk__in=page_ids).values("id", "title"):
        identity = title_identity_key(page["title"])
        if not identity:
            continue
        conflict_page_id = title_owners.get(identity)
        if conflict_page_id is not None:
            issues.append(
                {
                    "code": "page_title_conflict",
                    "page_id": page["id"],
                    "conflict_page_id": conflict_page_id,
                    "title_identity": identity,
                    "scope": "knowledge_base_all_states",
                }
            )
        else:
            title_owners[identity] = page["id"]

    if candidate.base_generation_id is None:
        baseline_active_page_ids = set(
            KnowledgePage.objects.filter(
                knowledge_base_id=candidate.knowledge_base_id,
                status=ACTIVE_GENERATION_PAGE_STATUS,
            ).values_list("id", flat=True)
        )
        for missing_page_id in sorted(baseline_active_page_ids - page_ids):
            issues.append(
                {
                    "code": "baseline_active_page_missing",
                    "page_id": missing_page_id,
                }
            )
        for action_page_id in sorted(page_actions):
            issues.append(
                {
                    "code": "generation_page_action_unexpected",
                    "page_id": action_page_id,
                }
            )
    else:
        base_page_ids = set()
        for base_member in candidate.base_generation.page_members.values(
            "page_id",
            "page_status",
        ):
            base_page_id = base_member["page_id"]
            base_page_ids.add(base_page_id)
            if base_member["page_status"] != ACTIVE_GENERATION_PAGE_STATUS:
                issues.append(
                    {
                        "code": "base_generation_member_status_invalid",
                        "page_id": base_page_id,
                        "page_status": base_member["page_status"],
                    }
                )
        missing_base_page_ids = base_page_ids - page_ids
        for missing_page_id in sorted(missing_base_page_ids):
            if missing_page_id not in page_actions:
                issues.append(
                    {
                        "code": "generation_page_action_missing",
                        "page_id": missing_page_id,
                    }
                )
        for action_page_id in sorted(page_actions):
            if action_page_id not in missing_base_page_ids:
                issues.append(
                    {
                        "code": "generation_page_action_unexpected",
                        "page_id": action_page_id,
                    }
                )

    for relation in candidate.relations.values(
        "id",
        "from_page_id",
        "to_page_id",
    ):
        missing = [page_id for page_id in (relation["from_page_id"], relation["to_page_id"]) if page_id not in page_ids]
        if missing:
            issues.append(
                {
                    "code": "relation_endpoint_outside_generation",
                    "relation_id": relation["id"],
                    "missing_page_ids": missing,
                }
            )
    from apps.opspilot.services.wiki.generation_navigation_service import navigation_validation_issues

    issues.extend(navigation_validation_issues(candidate))
    return issues


@transaction.atomic
def begin_generation(
    *,
    knowledge_base,
    kind,
    base_generation_id,
    structure_revision_id,
    pipeline_version,
    source_fingerprints=None,
    build_record=None,
    rollback_of_id=None,
    operator="",
):
    """Create a fixed preparing candidate under a short KB-lock transaction."""

    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    locked_kb = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base_id)
    kind = _non_empty(kind, "kind")
    if kind not in {choice[0] for choice in WikiGeneration.KIND_CHOICES}:
        raise GenerationServiceError(
            "generation_kind_invalid",
            "generation kind 非法",
            details={"kind": kind},
        )
    if locked_kb.active_generation_id != base_generation_id:
        raise GenerationServiceError(
            "base_generation_conflict",
            "active generation 已变化",
            retryable=True,
            details={
                "expected": base_generation_id,
                "actual": locked_kb.active_generation_id,
            },
        )
    if locked_kb.active_structure_revision_id != structure_revision_id:
        raise GenerationServiceError(
            "structure_revision_conflict",
            "active structure revision 已变化",
            retryable=True,
            details={
                "expected": structure_revision_id,
                "actual": locked_kb.active_structure_revision_id,
            },
        )
    structure_revision = WikiStructureRevision.objects.get(
        pk=structure_revision_id,
        knowledge_base=locked_kb,
    )
    if kind == "rollback" and rollback_of_id is None:
        raise GenerationServiceError(
            "rollback_target_required",
            "rollback generation 必须指定 rollback_of",
        )
    if kind != "rollback" and rollback_of_id is not None:
        raise GenerationServiceError(
            "rollback_target_not_allowed",
            "非 rollback generation 不得指定 rollback_of",
        )
    rollback_of = None
    if rollback_of_id is not None:
        rollback_of = WikiGeneration.objects.get(
            pk=rollback_of_id,
            knowledge_base=locked_kb,
        )
    if base_generation_id is not None:
        WikiGeneration.objects.get(
            pk=base_generation_id,
            knowledge_base=locked_kb,
        )
    if build_record is not None and build_record.knowledge_base_id != locked_kb.pk:
        raise GenerationServiceError(
            "build_record_knowledge_base_mismatch",
            "BuildRecord 不属于该知识库",
        )
    return WikiGeneration.objects.create(
        knowledge_base=locked_kb,
        build_record=build_record,
        structure_revision=structure_revision,
        base_generation_id=base_generation_id,
        rollback_of=rollback_of,
        kind=kind,
        structure_fingerprint=structure_revision.fingerprint,
        pipeline_version=_non_empty(pipeline_version, "pipeline_version"),
        source_fingerprints=list(source_fingerprints or []),
        status="preparing",
        created_by=operator or "",
    )


@transaction.atomic
def clone_base_snapshot(candidate_id, *, batch_size=500):
    """Idempotently clone unchanged members and relations from the fixed base."""

    locked_kb, candidate = _candidate_lock_order(candidate_id)
    _require_candidate_status(candidate, "preparing")
    if candidate.base_generation_id is None:
        return {"members": 0, "relations": 0}
    base = WikiGeneration.objects.get(
        pk=candidate.base_generation_id,
        knowledge_base=locked_kb,
    )
    member_rows = []
    for member in base.page_members.all().iterator(chunk_size=batch_size):
        if member.page_status != ACTIVE_GENERATION_PAGE_STATUS:
            raise GenerationServiceError(
                "base_generation_member_status_invalid",
                "base generation 只能包含 active 页面",
                details={
                    "generation_id": base.pk,
                    "page_id": member.page_id,
                    "page_status": member.page_status,
                },
            )
        member_rows.append(
            WikiGenerationPage(
                generation=candidate,
                page_id=member.page_id,
                page_version_id=member.page_version_id,
                directory_id=member.directory_id,
                directory_key_snapshot=member.directory_key_snapshot,
                directory_breadcrumb_snapshot=member.directory_breadcrumb_snapshot,
                assignment_mode=member.assignment_mode,
                page_status=member.page_status,
                page_display_snapshot=member.page_display_snapshot,
            )
        )
    WikiGenerationPage.objects.bulk_create(
        member_rows,
        batch_size=batch_size,
        ignore_conflicts=True,
    )

    relation_rows = []
    for relation in PageRelation.objects.filter(generation=base).iterator(chunk_size=batch_size):
        relation_rows.append(
            PageRelation(
                generation=candidate,
                from_page_id=relation.from_page_id,
                to_page_id=relation.to_page_id,
                relation_type=relation.relation_type,
                weight=relation.weight,
                via_material_id=relation.via_material_id,
            )
        )
    PageRelation.objects.bulk_create(
        relation_rows,
        batch_size=batch_size,
        ignore_conflicts=True,
    )
    return {
        "members": candidate.page_members.count(),
        "relations": candidate.relations.count(),
    }


@transaction.atomic
def clone_rollback_snapshot(candidate_id, *, batch_size=500):
    """Copy the retained rollback target without mutating the frozen source."""

    locked_kb, candidate = _candidate_lock_order(candidate_id)
    _require_candidate_status(candidate, "preparing")
    if candidate.kind != "rollback" or candidate.rollback_of_id is None:
        raise GenerationServiceError(
            "rollback_target_required",
            "只有 rollback generation 可以复制回退快照",
            details={"generation_id": candidate.pk},
        )
    target = WikiGeneration.objects.get(
        pk=candidate.rollback_of_id,
        knowledge_base=locked_kb,
    )
    if target.status not in {"active", "superseded"}:
        raise GenerationServiceError(
            "rollback_target_not_successful",
            "回退目标不是成功的历史 generation",
            details={
                "target_generation_id": target.pk,
                "status": target.status,
            },
        )

    candidate.page_members.all().delete()
    candidate.relations.all().delete()
    WikiGenerationPage.objects.bulk_create(
        [
            WikiGenerationPage(
                generation=candidate,
                page_id=member.page_id,
                page_version_id=member.page_version_id,
                directory_id=member.directory_id,
                directory_key_snapshot=member.directory_key_snapshot,
                directory_breadcrumb_snapshot=member.directory_breadcrumb_snapshot,
                assignment_mode=member.assignment_mode,
                page_status=member.page_status,
                page_display_snapshot=member.page_display_snapshot,
            )
            for member in target.page_members.all().iterator(chunk_size=batch_size)
        ],
        batch_size=batch_size,
    )
    PageRelation.objects.bulk_create(
        [
            PageRelation(
                generation=candidate,
                from_page_id=relation.from_page_id,
                to_page_id=relation.to_page_id,
                relation_type=relation.relation_type,
                weight=relation.weight,
                via_material_id=relation.via_material_id,
            )
            for relation in PageRelation.objects.filter(generation=target).iterator(chunk_size=batch_size)
        ],
        batch_size=batch_size,
    )
    return {
        "members": candidate.page_members.count(),
        "relations": candidate.relations.count(),
    }


@transaction.atomic
def put_generation_member(
    candidate_id,
    *,
    page_id,
    page_version_id,
    directory_id,
    assignment_mode=None,
    page_status=None,
    display_snapshot=None,
):
    """Create or replace one member while preserving the page identity."""

    locked_kb, candidate = _candidate_lock_order(candidate_id)
    _require_candidate_status(candidate, "preparing")
    page = KnowledgePage.objects.select_for_update().get(
        pk=page_id,
        knowledge_base=locked_kb,
    )
    version = PageVersion.objects.get(pk=page_version_id, page=page)
    base_page_versions = {}
    if candidate.base_generation_id is not None:
        base_version_id = candidate.base_generation.page_members.filter(page=page).values_list("page_version_id", flat=True).first()
        if base_version_id is not None:
            base_page_versions[page.pk] = base_version_id
    rollback_page_versions = {}
    if candidate.kind == "rollback" and candidate.rollback_of_id is not None:
        rollback_version_id = candidate.rollback_of.page_members.filter(page=page).values_list("page_version_id", flat=True).first()
        if rollback_version_id is not None:
            rollback_page_versions[page.pk] = rollback_version_id
    version_source_issue = _page_version_source_issue(
        candidate,
        page=page,
        version=version,
        base_page_versions=base_page_versions,
        rollback_page_versions=rollback_page_versions,
    )
    if version_source_issue is not None:
        raise GenerationServiceError(
            "generation_page_version_invalid",
            "页面版本不属于 generation 允许的固定来源",
            details=version_source_issue,
        )
    directory = WikiDirectory.objects.get(
        pk=directory_id,
        knowledge_base=locked_kb,
    )
    if directory.status != "active" or not directory.accepts_pages:
        raise GenerationServiceError(
            "directory_not_assignable",
            "目标目录不可接收页面",
            details={
                "directory_id": directory.pk,
                "status": directory.status,
            },
        )
    assignment_mode = assignment_mode or page.directory_assignment_mode
    if assignment_mode not in {choice[0] for choice in KnowledgePage.DIRECTORY_ASSIGNMENT_MODES}:
        raise GenerationServiceError(
            "assignment_mode_invalid",
            "目录归类模式非法",
            details={"assignment_mode": assignment_mode},
        )
    requested_page_status = page_status if page_status is not None else page.status
    if requested_page_status != ACTIVE_GENERATION_PAGE_STATUS:
        raise GenerationServiceError(
            "generation_member_status_invalid",
            "generation 成员只能是 active 页面",
            details={
                "page_id": page.pk,
                "page_status": requested_page_status,
            },
        )
    membership, _ = WikiGenerationPage.objects.update_or_create(
        generation=candidate,
        page=page,
        defaults={
            "page_version": version,
            "directory": directory,
            "directory_key_snapshot": directory.key,
            "directory_breadcrumb_snapshot": _directory_breadcrumb(directory),
            "assignment_mode": assignment_mode,
            "page_status": requested_page_status,
            "page_display_snapshot": _page_display_snapshot(
                page,
                display_snapshot,
            ),
        },
    )
    return membership


@transaction.atomic
def remove_generation_member(candidate_id, *, page_id):
    """Remove one page and candidate-local relations without touching history."""

    locked_kb, candidate = _candidate_lock_order(candidate_id)
    _require_candidate_status(candidate, "preparing")
    KnowledgePage.objects.get(pk=page_id, knowledge_base=locked_kb)
    relations_deleted, _ = candidate.relations.filter(from_page_id=page_id).delete()
    reverse_deleted, _ = candidate.relations.filter(to_page_id=page_id).delete()
    members_deleted, _ = candidate.page_members.filter(page_id=page_id).delete()
    return {
        "members_deleted": members_deleted,
        "relations_deleted": relations_deleted + reverse_deleted,
    }


@transaction.atomic
def mark_generation_ready(candidate_id):
    """Build required navigation artifacts, validate, and make the snapshot ready."""

    _, candidate = _candidate_lock_order(candidate_id)
    _require_candidate_status(candidate, "preparing", "ready")
    from apps.opspilot.services.wiki.generation_navigation_service import rebuild_generation_navigation

    rebuild_generation_navigation(candidate.pk)
    candidate.refresh_from_db()
    issues = _candidate_validation_issues(candidate)
    if issues:
        raise GenerationServiceError(
            "generation_incomplete",
            "generation 完整性校验失败",
            details={"issues": issues},
        )
    if candidate.status != "ready":
        candidate.status = "ready"
        candidate.save(update_fields=["status", "updated_at"])
    return candidate


def _apply_compatibility_mirror(candidate, previous_generation_id):
    page_actions, action_issues = _generation_page_actions(candidate)
    if action_issues:
        raise GenerationServiceError(
            "generation_page_actions_invalid",
            "generation 页面动作记录非法",
            details={"issues": action_issues},
        )

    members = list(candidate.page_members.select_related("page").order_by("id"))
    candidate_page_ids = {member.page_id for member in members}
    candidate_version_ids = {member.page_version_id for member in members}
    invalid_members = [
        {
            "page_id": member.page_id,
            "page_status": member.page_status,
        }
        for member in members
        if member.page_status != ACTIVE_GENERATION_PAGE_STATUS
    ]
    if invalid_members:
        raise GenerationServiceError(
            "generation_member_status_invalid",
            "generation 成员只能是 active 页面",
            details={"members": invalid_members},
        )

    previous_page_ids = set()
    if previous_generation_id is not None:
        previous_page_ids = set(
            WikiGenerationPage.objects.filter(
                generation_id=previous_generation_id,
                generation__knowledge_base_id=candidate.knowledge_base_id,
            ).values_list("page_id", flat=True)
        )
    omitted_page_ids = previous_page_ids - candidate_page_ids
    action_page_ids = set(page_actions)
    missing_action_ids = omitted_page_ids - action_page_ids
    unexpected_action_ids = action_page_ids - omitted_page_ids
    if missing_action_ids or unexpected_action_ids:
        raise GenerationServiceError(
            "generation_page_action_mismatch",
            "generation 页面差异必须由显式动作完整解释",
            details={
                "missing_page_ids": sorted(missing_action_ids),
                "unexpected_page_ids": sorted(unexpected_action_ids),
            },
        )

    pages = []
    fields = [
        "title",
        "page_type",
        "tags",
        "contribution",
        "update_method",
        "current_version",
        "directory",
        "directory_assignment_mode",
        "status",
    ]
    for member in members:
        page = member.page
        display = member.page_display_snapshot or {}
        page.title = display.get("title") or page.title
        page.page_type = display.get("page_type") or page.page_type
        page.tags = list(display.get("tags") or [])
        page.contribution = display.get("contribution") or page.contribution
        page.update_method = display.get("update_method") or page.update_method
        page.current_version_id = member.page_version_id
        page.directory_id = member.directory_id
        page.directory_assignment_mode = member.assignment_mode
        page.status = ACTIVE_GENERATION_PAGE_STATUS
        pages.append(page)
    if pages:
        KnowledgePage.objects.bulk_update(pages, fields, batch_size=500)

    if candidate_page_ids:
        (
            PageVersion.objects.filter(
                page_id__in=candidate_page_ids,
                is_current=True,
            )
            .exclude(pk__in=candidate_version_ids)
            .update(is_current=False)
        )
        PageVersion.objects.filter(pk__in=candidate_version_ids).update(is_current=True)

    if omitted_page_ids:
        omitted_pages = list(
            KnowledgePage.objects.filter(
                knowledge_base_id=candidate.knowledge_base_id,
                pk__in=omitted_page_ids,
            )
        )
        for page in omitted_pages:
            page.status = page_actions[page.pk]
        KnowledgePage.objects.bulk_update(
            omitted_pages,
            ["status"],
            batch_size=500,
        )


def _record_build_activation(candidate, result):
    if candidate.build_record_id is None:
        return
    BuildRecord.objects.filter(pk=candidate.build_record_id).update(
        generation=candidate,
        base_generation_id=candidate.base_generation_id,
        rollback_of_generation_id=candidate.rollback_of_id,
        structure_revision_id=candidate.structure_revision_id,
        structure_fingerprint=candidate.structure_fingerprint,
        pipeline_version=candidate.pipeline_version,
        source_fingerprints=candidate.source_fingerprints,
        activation={
            "candidate_generation_id": result.candidate_generation_id,
            "previous_generation_id": result.previous_generation_id,
            "active_generation_id": result.active_generation_id,
            "outcome": result.outcome,
            "code": result.code,
            "retryable": result.retryable,
        },
    )


@transaction.atomic
def activate_generation(
    candidate_id,
    *,
    requested_base_generation_id,
    expected_structure_revision_id,
    expected_structure_version,
    activation_hook=None,
):
    """Atomically CAS the active pointer and refresh page compatibility mirrors."""

    locked_kb, candidate = _candidate_lock_order(candidate_id)
    active_structure = locked_kb.active_structure_revision
    if active_structure is None:
        raise GenerationServiceError(
            "active_structure_missing",
            "知识库尚无 active structure revision",
        )
    issues = _candidate_validation_issues(candidate)
    facts = ActivationFacts(
        knowledge_base_id=locked_kb.pk,
        candidate_generation_id=candidate.pk,
        candidate_knowledge_base_id=candidate.knowledge_base_id,
        candidate_status=candidate.status,
        candidate_base_generation_id=candidate.base_generation_id,
        candidate_structure_revision_id=candidate.structure_revision_id,
        candidate_structure_version=candidate.structure_revision.revision_no,
        candidate_structure_fingerprint=candidate.structure_fingerprint,
        requested_base_generation_id=requested_base_generation_id,
        expected_structure_revision_id=expected_structure_revision_id,
        expected_structure_version=expected_structure_version,
        active_generation_id=locked_kb.active_generation_id,
        active_structure_revision_id=active_structure.pk,
        active_structure_version=active_structure.revision_no,
        active_structure_fingerprint=active_structure.fingerprint,
        candidate_complete=not issues,
    )
    decision = decide_activation(facts)
    previous_generation_id = locked_kb.active_generation_id
    if decision.outcome is not ActivationOutcome.ACTIVE:
        candidate.status = decision.outcome.value
        candidate.save(update_fields=["status", "updated_at"])
        result = GenerationActivationResult(
            candidate_generation_id=candidate.pk,
            previous_generation_id=previous_generation_id,
            active_generation_id=locked_kb.active_generation_id,
            outcome=decision.outcome.value,
            code=decision.code.value,
            retryable=decision.retryable,
        )
        _record_build_activation(candidate, result)
        logger.warning(
            "wiki_generation_activation kb=%s candidate=%s base=%s outcome=%s code=%s retryable=%s",
            locked_kb.pk,
            candidate.pk,
            requested_base_generation_id,
            result.outcome,
            result.code,
            result.retryable,
        )
        return result

    _apply_compatibility_mirror(candidate, previous_generation_id)
    if activation_hook is not None:
        activation_hook(candidate, locked_kb)
    if previous_generation_id is not None:
        WikiGeneration.objects.filter(
            pk=previous_generation_id,
            knowledge_base=locked_kb,
            status="active",
        ).update(status="superseded")
    candidate.status = "active"
    candidate.save(update_fields=["status", "updated_at"])
    locked_kb.active_generation = candidate
    locked_kb.save(update_fields=["active_generation", "updated_at"])
    result = GenerationActivationResult(
        candidate_generation_id=candidate.pk,
        previous_generation_id=previous_generation_id,
        active_generation_id=candidate.pk,
        outcome=decision.outcome.value,
        code=decision.code.value,
        retryable=decision.retryable,
    )
    _record_build_activation(candidate, result)
    logger.info(
        "wiki_generation_activation kb=%s candidate=%s previous=%s outcome=%s pipeline=%s",
        locked_kb.pk,
        candidate.pk,
        previous_generation_id,
        result.outcome,
        candidate.pipeline_version,
    )
    return result
