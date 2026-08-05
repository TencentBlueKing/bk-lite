"""Shared staging-generation orchestration for Wiki build pipelines."""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Max

from apps.opspilot.models import BuildRecord, KnowledgePage, PageEvidence, PageVersion, WikiGeneration, WikiKnowledgeBase
from apps.opspilot.services.wiki.generation_relation_service import rebuild_generation_relations
from apps.opspilot.services.wiki.generation_service import (
    activate_generation,
    begin_generation,
    clone_base_snapshot,
    mark_generation_ready,
    put_generation_member,
)
from apps.opspilot.services.wiki.title_service import canonical_title, title_identity_key, validate_display_title

PIPELINE_VERSION = "wiki-directory-generation-v1"


class BuildGenerationError(Exception):
    def __init__(self, code, message, *, retryable=False, details=None):
        self.code = str(code)
        self.retryable = bool(retryable)
        self.details = dict(details or {})
        super().__init__(message)


@dataclass(frozen=True)
class FrozenBuildGeneration:
    candidate_generation_id: int
    base_generation_id: int | None
    structure_revision_id: int
    structure_version: int
    structure_fingerprint: str
    pipeline_version: str
    source_fingerprints: tuple


@dataclass(frozen=True)
class StagedPageResult:
    page_id: int
    page_version_id: int
    action: str
    title: str
    directory_id: int
    assignment_mode: str


def material_fingerprint(material):
    current_version = getattr(material, "current_version", None)
    return {
        "material_id": material.pk,
        "material_version_id": getattr(current_version, "pk", None),
        "content_hash": (getattr(current_version, "content_hash", "") or material.content_hash or "").strip(),
        "source_identity": (material.source_identity or "").strip(),
    }


def freeze_source_fingerprints(materials):
    return [material_fingerprint(material) for material in sorted(materials, key=lambda item: item.pk)]


def freeze_generation_identity(
    knowledge_base,
    materials,
    *,
    classification_root_id=None,
):
    """Capture the complete governance/source identity for a synchronous job."""

    revision = knowledge_base.active_structure_revision
    if revision is None or knowledge_base.active_generation_id is None:
        raise BuildGenerationError(
            "active_governance_snapshot_missing",
            "知识库缺少 active structure/generation",
        )
    source_fingerprints = freeze_source_fingerprints(materials)
    incomplete = [
        fingerprint
        for fingerprint in source_fingerprints
        if not fingerprint.get("material_version_id")
        or not str(fingerprint.get("content_hash") or "").strip()
        or not str(fingerprint.get("source_identity") or "").strip()
    ]
    if incomplete:
        raise BuildGenerationError(
            "source_identity_incomplete",
            "generation 任务缺少完整资料来源身份",
            details={"source_fingerprints": incomplete},
        )
    return {
        "base_generation_id": knowledge_base.active_generation_id,
        "structure_revision_id": revision.pk,
        "structure_version": revision.revision_no,
        "structure_fingerprint": revision.fingerprint,
        "pipeline_version": PIPELINE_VERSION,
        "source_fingerprints": source_fingerprints,
        "classification_root_id": classification_root_id,
    }


def _frozen_payload(context):
    return {
        "generation_id": context.candidate_generation_id,
        "base_generation_id": context.base_generation_id,
        "structure_revision_id": context.structure_revision_id,
        "structure_version": context.structure_version,
        "structure_fingerprint": context.structure_fingerprint,
        "pipeline_version": context.pipeline_version,
        "source_fingerprints": list(context.source_fingerprints),
    }


def begin_build_generation(
    knowledge_base,
    build_record,
    *,
    source_fingerprints,
    pipeline_version=PIPELINE_VERSION,
    kind="build",
    operator="",
):
    """Freeze identities and clone the complete active snapshot."""

    knowledge_base = WikiKnowledgeBase.objects.select_related("active_structure_revision").get(pk=knowledge_base.pk)
    if not (knowledge_base.active_generation_id and knowledge_base.active_structure_revision_id):
        raise BuildGenerationError(
            "generation_pipeline_not_enabled",
            "知识库尚未进入 generation truth 状态",
        )
    revision = knowledge_base.active_structure_revision
    if revision is None or knowledge_base.active_generation_id is None:
        raise BuildGenerationError(
            "active_governance_snapshot_missing",
            "知识库缺少 active structure/generation",
        )
    candidate = begin_generation(
        knowledge_base=knowledge_base,
        kind=kind,
        base_generation_id=knowledge_base.active_generation_id,
        structure_revision_id=revision.pk,
        pipeline_version=pipeline_version,
        source_fingerprints=list(source_fingerprints),
        build_record=build_record,
        operator=operator,
    )
    clone_base_snapshot(candidate.pk)
    context = FrozenBuildGeneration(
        candidate_generation_id=candidate.pk,
        base_generation_id=candidate.base_generation_id,
        structure_revision_id=revision.pk,
        structure_version=revision.revision_no,
        structure_fingerprint=revision.fingerprint,
        pipeline_version=pipeline_version,
        source_fingerprints=tuple(source_fingerprints),
    )
    BuildRecord.objects.filter(pk=build_record.pk).update(
        generation=candidate,
        base_generation_id=candidate.base_generation_id,
        structure_revision=revision,
        structure_fingerprint=revision.fingerprint,
        pipeline_version=pipeline_version,
        source_fingerprints=list(source_fingerprints),
        inputs={**(build_record.inputs or {}), "generation": _frozen_payload(context)},
    )
    return context


def _page_by_title_locked(knowledge_base_id, title):
    identity = title_identity_key(title)
    for page in KnowledgePage.objects.select_for_update().filter(knowledge_base_id=knowledge_base_id).order_by("id"):
        if title_identity_key(page.title) == identity:
            return page
    return None


def _next_version_no(page):
    maximum = page.page_versions.aggregate(value=Max("no"))["value"]
    return (maximum or 0) + 1


def _merge_body(current_body, incoming_body, strategy):
    current = current_body or ""
    incoming = (incoming_body or "").strip()
    if strategy == "replace":
        return incoming
    if strategy != "merge":
        raise BuildGenerationError(
            "body_strategy_invalid",
            "body strategy 非法",
            details={"strategy": strategy},
        )
    if not incoming or incoming == current or incoming in current:
        return current
    if not current:
        return incoming
    return "\n\n".join((current, incoming))


@transaction.atomic
def stage_ai_page(
    context,
    *,
    page_id=None,
    title,
    page_type,
    tags,
    body,
    directory_id,
    assignment_mode,
    build_record,
    operator="",
    update_method="ai_merge",
    change_type="ai_merge",
    body_strategy="merge",
    navigation_metadata=None,
):
    """Create or reconcile one AI page inside a preparing candidate."""

    candidate_identity = WikiGeneration.objects.filter(pk=context.candidate_generation_id).values("knowledge_base_id").first()
    if candidate_identity is None:
        raise BuildGenerationError("generation_not_found", "generation 不存在")
    knowledge_base = WikiKnowledgeBase.objects.select_for_update().get(pk=candidate_identity["knowledge_base_id"])
    candidate = WikiGeneration.objects.select_for_update().get(pk=context.candidate_generation_id, knowledge_base=knowledge_base)
    if candidate.status != "preparing":
        raise BuildGenerationError(
            "generation_status_conflict",
            "只有 preparing generation 可以写入页面",
            details={"status": candidate.status},
        )
    if (
        candidate.base_generation_id != context.base_generation_id
        or candidate.structure_revision_id != context.structure_revision_id
        or candidate.structure_fingerprint != context.structure_fingerprint
        or candidate.pipeline_version != context.pipeline_version
    ):
        raise BuildGenerationError("frozen_generation_identity_mismatch", "构建固定身份不一致")

    display_title = validate_display_title(canonical_title(knowledge_base, title))
    page = (
        KnowledgePage.objects.select_for_update().get(
            pk=page_id,
            knowledge_base=knowledge_base,
        )
        if page_id is not None
        else _page_by_title_locked(knowledge_base.pk, display_title)
    )
    created = page is None
    if created:
        page = KnowledgePage.objects.create(
            knowledge_base=knowledge_base,
            page_type=page_type or "concept",
            title=display_title,
            tags=list(tags or []),
            contribution="ai",
            update_method=update_method,
            status="archived",
            directory_id=directory_id,
            directory_assignment_mode=assignment_mode,
            created_by=operator or "",
            updated_by=operator or "",
        )
    elif page.contribution != "ai":
        raise BuildGenerationError(
            "human_content_requires_candidate",
            "human/mixed 页面正文不能由确定性构建覆盖",
            details={"page_id": page.pk, "contribution": page.contribution},
        )

    membership = candidate.page_members.select_related("page_version").filter(page=page).first()
    base_member = None
    if context.base_generation_id is not None:
        base_member = candidate.base_generation.page_members.select_related("page_version").filter(page=page).first()
    source_version = membership.page_version if membership is not None else getattr(base_member, "page_version", None)
    if source_version is None and page.current_version_id is not None:
        source_version = PageVersion.objects.get(pk=page.current_version_id, page=page)
    current_body = source_version.body if source_version is not None else ""
    merged_body = _merge_body(current_body, body, body_strategy)
    navigation_metadata = {
        key: value for key, value in dict(navigation_metadata or {}).items() if key in {"summary", "keywords", "entities", "aliases"}
    }
    source_meta = dict(source_version.meta_snapshot or {}) if source_version is not None else {}
    navigation_changed = any(source_meta.get(key) != value for key, value in navigation_metadata.items())
    current_display = dict(getattr(membership, "page_display_snapshot", None) or {})
    current_tags = list(current_display.get("tags") or page.tags or [])
    merged_tags = list(dict.fromkeys([*current_tags, *(tags or [])]))
    metadata_changed = (
        current_display.get("title", page.title) != display_title
        or current_display.get("page_type", page.page_type) != (page_type or "concept")
        or current_tags != merged_tags
        or current_display.get("update_method", page.update_method) != update_method
        or navigation_changed
    )
    body_changed = source_version is None or source_version.body != merged_body

    if membership is not None and membership.page_version.created_in_generation_id == candidate.pk:
        version = membership.page_version
        if body_changed:
            version.body = merged_body
            version.meta_snapshot = {
                **(version.meta_snapshot or {}),
                **navigation_metadata,
                "candidate_generation_id": candidate.pk,
            }
            version.save(update_fields=["body", "meta_snapshot", "updated_at"])
        elif navigation_changed:
            version.meta_snapshot = {
                **(version.meta_snapshot or {}),
                **navigation_metadata,
                "candidate_generation_id": candidate.pk,
            }
            version.save(update_fields=["meta_snapshot", "updated_at"])
    elif body_changed or metadata_changed or created or base_member is None:
        version = PageVersion.objects.create(
            page=page,
            no=_next_version_no(page),
            body=merged_body,
            meta_snapshot={**navigation_metadata, "candidate_generation_id": candidate.pk},
            change_type=change_type,
            build_record=build_record,
            created_in_generation=candidate,
            is_current=False,
            created_by=operator or "",
        )
    else:
        version = source_version

    put_generation_member(
        candidate.pk,
        page_id=page.pk,
        page_version_id=version.pk,
        directory_id=directory_id,
        assignment_mode=assignment_mode,
        page_status="active",
        display_snapshot={
            "title": display_title,
            "page_type": page_type or "concept",
            "tags": merged_tags,
            "contribution": "ai",
            "update_method": update_method,
            "updated_by": operator or "",
        },
    )
    if created:
        action = "create"
    elif page.status != "active" or base_member is None:
        action = "restore"
    elif body_changed or metadata_changed:
        action = "update"
    else:
        action = "unchanged"
    return StagedPageResult(
        page_id=page.pk,
        page_version_id=version.pk,
        action=action,
        title=display_title,
        directory_id=directory_id,
        assignment_mode=assignment_mode,
    )


def _write_evidence(evidence_records):
    for record in evidence_records:
        page_id = record["page_id"]
        material = record["material"]
        material_version = record.get("material_version") or getattr(material, "current_version", None)
        evidence, _ = PageEvidence.objects.get_or_create(
            page_id=page_id,
            material=material,
            material_version=material_version,
            defaults={"locator": record.get("locator") or ""},
        )
        locator = record.get("locator") or ""
        if locator and evidence.locator != locator:
            evidence.locator = locator
            evidence.save(update_fields=["locator", "updated_at"])


def finalize_build_generation(
    context,
    *,
    build_record,
    page_actions,
    directory_trace,
    pending_material_ids_by_page=None,
    replace_material_ids_for_pages=None,
    evidence_records=None,
    pre_activation_hook=None,
    activation_hook=None,
):
    """Materialize derived relations, validate, and atomically activate."""

    relation_result = rebuild_generation_relations(
        context.candidate_generation_id,
        pending_material_ids_by_page=pending_material_ids_by_page,
        replace_material_ids_for_pages=replace_material_ids_for_pages,
    )
    BuildRecord.objects.filter(pk=build_record.pk).update(
        page_actions=list(page_actions),
        directory_trace=list(directory_trace),
        maintenance={
            **(build_record.maintenance or {}),
            "generation_relations": relation_result,
        },
    )
    mark_generation_ready(context.candidate_generation_id)
    if pre_activation_hook is not None:
        pre_activation_hook(WikiGeneration.objects.get(pk=context.candidate_generation_id))

    def combined_activation_hook(candidate, knowledge_base):
        if activation_hook is not None:
            activation_hook(candidate, knowledge_base, relation_result)
        _write_evidence(evidence_records or [])

    result = activate_generation(
        context.candidate_generation_id,
        requested_base_generation_id=context.base_generation_id,
        expected_structure_revision_id=context.structure_revision_id,
        expected_structure_version=context.structure_version,
        activation_hook=combined_activation_hook,
    )
    if result.outcome != "active":
        raise BuildGenerationError(
            result.code,
            "generation 激活竞争失败",
            retryable=result.retryable,
            details={
                "candidate_generation_id": result.candidate_generation_id,
                "active_generation_id": result.active_generation_id,
                "outcome": result.outcome,
            },
        )
    return result, relation_result


@transaction.atomic
def fail_build_generation(context, *, build_record=None, code="generation_failed", error=""):
    candidate = WikiGeneration.objects.select_for_update().get(pk=context.candidate_generation_id)
    if candidate.status in {"preparing", "ready"}:
        candidate.status = "failed"
        candidate.save(update_fields=["status", "updated_at"])
    if build_record is not None:
        BuildRecord.objects.filter(pk=build_record.pk).update(
            generation=candidate,
            activation={
                "candidate_generation_id": candidate.pk,
                "active_generation_id": candidate.knowledge_base.active_generation_id,
                "outcome": candidate.status,
                "code": code,
                "retryable": False,
                "error": str(error or ""),
            },
        )
    return candidate


__all__ = [
    "BuildGenerationError",
    "FrozenBuildGeneration",
    "PIPELINE_VERSION",
    "StagedPageResult",
    "begin_build_generation",
    "fail_build_generation",
    "finalize_build_generation",
    "freeze_generation_identity",
    "freeze_source_fingerprints",
    "material_fingerprint",
    "stage_ai_page",
]
