"""知识页面版本管理:人工创建/编辑/恢复都生成新版本,当前有效版本始终明确。

对应 spec §8(页面编辑)、§9(版本管理:每次变化生成新版本,可比较与恢复)。
"""

import difflib

from django.db import transaction

from apps.opspilot.models import KnowledgePage, PageVersion, WikiDirectory, WikiKnowledgeBase
from apps.opspilot.services.wiki.decision_service import revoke_rules_for_identity_change, subject_key_for_page
from apps.opspilot.services.wiki.generation_relation_service import GenerationRelationError, rebuild_generation_relations
from apps.opspilot.services.wiki.generation_service import (
    GenerationServiceError,
    activate_generation,
    begin_generation,
    clone_base_snapshot,
    mark_generation_ready,
    put_generation_member,
)
from apps.opspilot.services.wiki.title_service import InvalidWikiTitle, WikiTitleConflict, assert_unique_title_locked, canonical_title

UNCLASSIFIED_DIRECTORY_KEY = "__unclassified__"
MANUAL_PAGE_PIPELINE_VERSION = "wiki-manual-page-governance-v1"


class PageServiceError(Exception):
    """Stable page-write error suitable for API mapping."""

    def __init__(self, code, message, *, status_code=422, retryable=False, details=None):
        super().__init__(message)
        self.code = str(code)
        self.status_code = status_code
        self.retryable = bool(retryable)
        self.details = dict(details or {})


def _unique_title(*, knowledge_base_id, title, exclude_page_id=None):
    try:
        return assert_unique_title_locked(
            knowledge_base_id=knowledge_base_id,
            title=title,
            exclude_page_id=exclude_page_id,
        )
    except WikiTitleConflict as error:
        raise PageServiceError(
            "page_title_conflict",
            str(error),
            status_code=409,
            details={
                "title": error.title,
                "conflict_page_id": error.conflict_page_id,
                "conflict_title": error.conflict_title,
                "conflict_status": error.conflict_status,
            },
        ) from error
    except InvalidWikiTitle as error:
        raise PageServiceError(
            "page_title_invalid",
            str(error),
            status_code=422,
        ) from error


def _generation_error(error):
    conflict_codes = {
        "active_structure_missing",
        "base_generation_conflict",
        "structure_revision_conflict",
        "generation_status_conflict",
    }
    conflict = error.retryable or error.code in conflict_codes
    return PageServiceError(
        error.code,
        str(error),
        status_code=409 if conflict else 422,
        retryable=conflict,
        details=error.details,
    )


def _active_pair_locked(locked_kb):
    if locked_kb.active_structure_revision_id is None or locked_kb.active_generation_id is None:
        raise PageServiceError(
            "active_snapshot_missing",
            "知识库缺少可写入的 active structure/generation",
            status_code=409,
            retryable=True,
        )
    revision = locked_kb.structure_revisions.get(pk=locked_kb.active_structure_revision_id)
    generation = locked_kb.generations.get(pk=locked_kb.active_generation_id)
    if generation.status != "active" or generation.structure_revision_id != revision.pk:
        raise PageServiceError(
            "active_snapshot_mismatch",
            "active structure/generation 指针不一致",
            status_code=409,
            retryable=True,
            details={
                "active_structure_revision_id": revision.pk,
                "active_generation_id": generation.pk,
                "generation_structure_revision_id": generation.structure_revision_id,
                "generation_status": generation.status,
            },
        )
    return revision, generation


def _target_directory(locked_kb, revision, page_type, directory_id=None):
    snapshot = revision.structure_snapshot or {}
    nodes = snapshot.get("directories")
    if snapshot.get("format_version") != 1 or not isinstance(nodes, list):
        raise PageServiceError(
            "structure_snapshot_invalid",
            "active structure snapshot 不是受支持的完整结构格式",
            details={"structure_revision_id": revision.pk},
        )

    if directory_id is None:
        target_node = next(
            (node for node in nodes if isinstance(node, dict) and node.get("key") == UNCLASSIFIED_DIRECTORY_KEY),
            None,
        )
    else:
        try:
            normalized_directory_id = int(directory_id)
        except (TypeError, ValueError) as error:
            raise PageServiceError("directory_id_invalid", "directory_id 非法") from error
        target_node = next(
            (node for node in nodes if isinstance(node, dict) and node.get("id") == normalized_directory_id),
            None,
        )
    if target_node is None:
        raise PageServiceError(
            "directory_not_in_active_structure",
            "目标目录不属于 active structure",
            details={"directory_id": directory_id},
        )

    target = WikiDirectory.objects.filter(
        pk=target_node.get("id"),
        knowledge_base=locked_kb,
        status="active",
        accepts_pages=True,
    ).first()
    if target is None:
        raise PageServiceError(
            "directory_not_assignable",
            "目标目录不可接收页面",
            details={"directory_id": target_node.get("id")},
        )
    rules = target_node.get("rules") or {}
    allowed = rules.get("allowed_page_types")
    if isinstance(allowed, list) and allowed and page_type not in allowed:
        raise PageServiceError(
            "directory_page_type_not_allowed",
            "目标目录不接收该页面类型",
            details={"directory_id": target.pk, "page_type": page_type},
        )
    return target


def _begin_manual_candidate(locked_kb, revision, base_generation, operator):
    try:
        candidate = begin_generation(
            knowledge_base=locked_kb,
            kind="governance",
            base_generation_id=base_generation.pk,
            structure_revision_id=revision.pk,
            pipeline_version=MANUAL_PAGE_PIPELINE_VERSION,
            source_fingerprints=list(base_generation.source_fingerprints or []),
            operator=operator or "",
        )
        clone_base_snapshot(candidate.pk)
        return candidate
    except GenerationServiceError as error:
        raise _generation_error(error) from error


def _activate_manual_candidate(candidate, revision, base_generation):
    try:
        rebuild_generation_relations(candidate.pk)
        mark_generation_ready(candidate.pk)
        activation = activate_generation(
            candidate.pk,
            requested_base_generation_id=base_generation.pk,
            expected_structure_revision_id=revision.pk,
            expected_structure_version=revision.revision_no,
        )
    except GenerationServiceError as error:
        raise _generation_error(error) from error
    except GenerationRelationError as error:
        raise PageServiceError(
            error.code,
            str(error),
            status_code=422,
            details=error.details,
        ) from error
    if activation.outcome != "active":
        raise PageServiceError(
            activation.code,
            "页面 generation 激活失败",
            status_code=409,
            retryable=activation.retryable,
            details={
                "candidate_generation_id": candidate.pk,
                "base_generation_id": base_generation.pk,
                "active_generation_id": activation.active_generation_id,
            },
        )
    return activation


def _next_no(page):
    last = page.page_versions.order_by("-no").first()
    return (last.no + 1) if last else 1


@transaction.atomic
def _new_candidate_version(
    page,
    candidate,
    body,
    change_type,
    created_by,
    meta_snapshot=None,
    build_record=None,
):
    return PageVersion.objects.create(
        page=page,
        no=_next_no(page),
        body=body,
        change_type=change_type,
        created_in_generation=candidate,
        is_current=False,
        created_by=created_by or "",
        meta_snapshot=meta_snapshot or {},
        build_record=build_record,
    )


@transaction.atomic
def create_manual_page(
    knowledge_base,
    page_type,
    title,
    body="",
    tags=None,
    created_by="",
    directory_id=None,
    contribution="human",
    update_method="human_edit",
    change_type="human_edit",
    meta_snapshot=None,
):
    """人工创建知识页面；ready/enabled 下通过完整 generation 候选发布。"""
    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    locked_kb = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base_id)
    display_title = _unique_title(
        knowledge_base_id=locked_kb.pk,
        title=title,
    )
    revision, base_generation = _active_pair_locked(locked_kb)
    target = _target_directory(locked_kb, revision, page_type, directory_id)
    candidate = _begin_manual_candidate(locked_kb, revision, base_generation, created_by)
    page = KnowledgePage.objects.create(
        knowledge_base=locked_kb,
        page_type=page_type,
        title=display_title,
        tags=tags or [],
        contribution=contribution,
        update_method=update_method,
        status="staging",
        directory=target,
        directory_assignment_mode="manual",
        created_by=created_by or "",
    )
    version = _new_candidate_version(
        page,
        candidate,
        body=body,
        change_type=change_type,
        created_by=created_by,
        meta_snapshot=meta_snapshot,
    )
    try:
        put_generation_member(
            candidate.pk,
            page_id=page.pk,
            page_version_id=version.pk,
            directory_id=target.pk,
            assignment_mode="manual",
            page_status="active",
        )
    except GenerationServiceError as error:
        raise _generation_error(error) from error
    _activate_manual_candidate(candidate, revision, base_generation)
    page.refresh_from_db()
    return page


def _answer_source_meta(source_conversation_id="", source_message_id="", source_channel="qa"):
    return {
        "type": "qa_answer",
        "conversation_id": str(source_conversation_id),
        "message_id": str(source_message_id or ""),
        "channel": str(source_channel or "qa"),
    }


@transaction.atomic
def save_answer_page(
    knowledge_base,
    page_type,
    title,
    body,
    tags=None,
    source_conversation_id="",
    source_message_id="",
    source_channel="qa",
    created_by="",
):
    """将 QA/Bot 回答沉淀为知识页面,并记录来源对话。"""
    return create_manual_page(
        knowledge_base=knowledge_base,
        page_type=page_type,
        title=title,
        body=body,
        tags=tags,
        created_by=created_by,
        contribution="mixed",
        update_method="qa_answer",
        change_type="qa_answer",
        meta_snapshot={
            "source": _answer_source_meta(
                source_conversation_id,
                source_message_id,
                source_channel,
            )
        },
    )


@transaction.atomic
def edit_page(
    page,
    body=None,
    title=None,
    tags=None,
    page_type=None,
    updated_by="",
    contribution=None,
    update_method="human_edit",
    change_type="human_edit",
    meta_snapshot=None,
    build_record=None,
):
    """人工编辑页面；ready/enabled 下只通过新的完整 generation 生效。"""
    locked_kb = WikiKnowledgeBase.objects.select_for_update().get(pk=page.knowledge_base_id)
    locked_page = KnowledgePage.objects.select_for_update().get(pk=page.pk, knowledge_base_id=locked_kb.pk)
    next_title = _unique_title(
        knowledge_base_id=locked_kb.pk,
        title=locked_page.title if title is None else title,
        exclude_page_id=locked_page.pk,
    )
    next_page_type = locked_page.page_type if page_type is None else page_type
    old_subject_key = subject_key_for_page(
        page_type=locked_page.page_type or "concept",
        canonical_title=canonical_title(locked_kb, locked_page.title),
    )
    next_subject_key = subject_key_for_page(
        page_type=next_page_type or "concept",
        canonical_title=canonical_title(locked_kb, next_title),
    )

    revision, base_generation = _active_pair_locked(locked_kb)
    try:
        member = base_generation.page_members.select_related("page_version", "directory").get(
            page=locked_page,
            page_status="active",
        )
    except base_generation.page_members.model.DoesNotExist as error:
        raise PageServiceError(
            "page_not_in_active_generation",
            "页面不属于当前 active generation",
            status_code=409,
            retryable=True,
            details={"page_id": locked_page.pk, "active_generation_id": base_generation.pk},
        ) from error
    target = _target_directory(locked_kb, revision, next_page_type, member.directory_id)
    candidate = _begin_manual_candidate(locked_kb, revision, base_generation, updated_by)
    if next_subject_key != old_subject_key:
        revoke_rules_for_identity_change(
            locked_kb,
            old_subject_key,
            reason="page identity changed",
            operator=updated_by,
        )
    locked_page.title = next_title
    locked_page.page_type = next_page_type
    if tags is not None:
        locked_page.tags = tags
    locked_page.contribution = (
        contribution if contribution is not None else ("mixed" if locked_page.contribution == "ai" else locked_page.contribution)
    )
    locked_page.update_method = update_method
    locked_page.updated_by = updated_by or ""
    locked_page.save(
        update_fields=[
            "title",
            "page_type",
            "tags",
            "contribution",
            "update_method",
            "updated_by",
            "updated_at",
        ]
    )
    version = _new_candidate_version(
        locked_page,
        candidate,
        body=body if body is not None else member.page_version.body,
        change_type=change_type,
        created_by=updated_by,
        meta_snapshot=meta_snapshot,
        build_record=build_record,
    )
    try:
        put_generation_member(
            candidate.pk,
            page_id=locked_page.pk,
            page_version_id=version.pk,
            directory_id=target.pk,
            assignment_mode=member.assignment_mode,
            page_status="active",
        )
    except GenerationServiceError as error:
        raise _generation_error(error) from error
    _activate_manual_candidate(candidate, revision, base_generation)
    locked_page.refresh_from_db()
    version.refresh_from_db(fields=["is_current"])
    return version


@transaction.atomic
def restore_version(page, version_id, operator=""):
    """恢复历史版本；ready/enabled 下复制正文到候选 generation 后再激活。"""
    locked_kb = WikiKnowledgeBase.objects.select_for_update().get(pk=page.knowledge_base_id)
    locked_page = KnowledgePage.objects.select_for_update().get(pk=page.pk, knowledge_base_id=locked_kb.pk)
    target_version = locked_page.page_versions.get(id=version_id)
    revision, base_generation = _active_pair_locked(locked_kb)
    try:
        member = base_generation.page_members.select_related("page_version", "directory").get(
            page=locked_page,
            page_status="active",
        )
    except base_generation.page_members.model.DoesNotExist as error:
        raise PageServiceError(
            "page_not_in_active_generation",
            "页面不属于当前 active generation",
            status_code=409,
            retryable=True,
            details={"page_id": locked_page.pk, "active_generation_id": base_generation.pk},
        ) from error
    target = _target_directory(locked_kb, revision, locked_page.page_type, member.directory_id)
    candidate = _begin_manual_candidate(locked_kb, revision, base_generation, operator)
    restored = _new_candidate_version(
        locked_page,
        candidate,
        body=target_version.body,
        change_type="restore",
        created_by=operator,
    )
    try:
        put_generation_member(
            candidate.pk,
            page_id=locked_page.pk,
            page_version_id=restored.pk,
            directory_id=target.pk,
            assignment_mode=member.assignment_mode,
            page_status="active",
        )
    except GenerationServiceError as error:
        raise _generation_error(error) from error
    _activate_manual_candidate(candidate, revision, base_generation)
    restored.refresh_from_db(fields=["is_current"])
    return restored


def diff_versions(page, from_id, to_id):
    """返回两个版本正文的逐行统一 diff(unified diff 行列表),用于版本对比可视化。"""
    versions = {v.id: v for v in page.page_versions.filter(id__in=[from_id, to_id])}
    a, b = versions.get(from_id), versions.get(to_id)
    if not a or not b:
        raise ValueError("version not found")
    return list(
        difflib.unified_diff(
            (a.body or "").splitlines(),
            (b.body or "").splitlines(),
            fromfile=f"v{a.no}",
            tofile=f"v{b.no}",
            lineterm="",
        )
    )
