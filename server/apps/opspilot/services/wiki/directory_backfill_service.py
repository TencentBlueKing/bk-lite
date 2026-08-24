"""存量 Wiki 知识库目录/generation 基线回填。

新空库走 ``bootstrap_knowledge_base``；已有资料的线上旧库必须用本模块
（管理命令 ``backfill_wiki_directory_governance``）补齐 active structure +
active generation。
"""

from __future__ import annotations

import unicodedata
from copy import deepcopy
from dataclasses import dataclass

from django.db import transaction

from apps.opspilot.models import (
    BuildRecord,
    KnowledgePage,
    PageDirectoryChange,
    PageRelation,
    PageVersion,
    WikiDirectory,
    WikiGeneration,
    WikiKnowledgeBase,
    WikiStructureRevision,
)
from apps.opspilot.services.wiki.directory_readiness_service import KNOWN_PAGE_STATUSES
from apps.opspilot.services.wiki.generation_service import GenerationServiceError, activate_generation, mark_generation_ready, put_generation_member
from apps.opspilot.services.wiki.governance_contract import DirectoryMigrationState, advance_migration_state
from apps.opspilot.services.wiki.structure_service import (
    UNCLASSIFIED_DIRECTORY_KEY,
    UNCLASSIFIED_DIRECTORY_NAME,
    _apply_projection,
    _bootstrap_snapshot,
    _bootstrap_template_nodes,
    _fingerprint,
)
from apps.opspilot.services.wiki.title_service import title_identity_key

BACKFILL_PIPELINE_VERSION = "wiki-directory-baseline-backfill-v1"
BACKFILL_SOURCE_FINGERPRINTS = [
    {"kind": "wiki_directory_baseline_backfill", "version": 1},
]
BACKFILL_CHANGE_SOURCE = "baseline_backfill"


@dataclass(frozen=True)
class BackfillContext:
    knowledge_base_id: int
    generation_id: int
    structure_revision_id: int
    unclassified_directory_id: int


class BackfillPreflightError(Exception):
    """回填前检查失败；知识库应保持 legacy，不进入 fence。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _actor(operator: str = "") -> str:
    return unicodedata.normalize("NFKC", str(operator or "")).strip()[:32] or "system"


def repair_missing_current_versions(knowledge_base_id: int) -> int:
    """修复「有 PageVersion 但 current_version 指针为空」的存量脏数据。

    取该页最新版本（no、id 降序）设为 current，并纠正 is_current。
    返回修复页数。没有任何历史版本的页不会被静默跳过以外的处理。
    """

    repaired = 0
    page_ids = list(
        KnowledgePage.objects.filter(
            knowledge_base_id=knowledge_base_id,
            current_version_id__isnull=True,
        )
        .order_by("id")
        .values_list("id", flat=True)
    )
    for page_id in page_ids:
        with transaction.atomic():
            page = KnowledgePage.objects.select_for_update().filter(pk=page_id).first()
            if page is None or page.current_version_id is not None:
                continue
            latest = PageVersion.objects.filter(page_id=page.pk).order_by("-no", "-id").first()
            if latest is None:
                continue
            PageVersion.objects.filter(page_id=page.pk, is_current=True).exclude(pk=latest.pk).update(is_current=False)
            if not latest.is_current:
                latest.is_current = True
                latest.save(update_fields=["is_current"])
            page.current_version = latest
            page.save(update_fields=["current_version", "updated_at"])
            repaired += 1
    return repaired


def preflight_legacy_knowledge_base(knowledge_base_id: int) -> None:
    """在开启 backfilling fence 前做只读检查。"""

    knowledge_base = WikiKnowledgeBase.objects.filter(pk=knowledge_base_id).first()
    if knowledge_base is None:
        raise BackfillPreflightError(f"knowledge_base_not_found id={knowledge_base_id}")

    running = list(BuildRecord.objects.filter(knowledge_base_id=knowledge_base_id, status="running").order_by("id").values_list("id", flat=True)[:20])
    if running:
        raise BackfillPreflightError(f"running builds block backfill build_record_ids={','.join(str(item) for item in running)}")

    pages = list(
        KnowledgePage.objects.filter(knowledge_base_id=knowledge_base_id).values("id", "title", "status", "current_version_id").order_by("id")
    )
    version_page_ids = set(PageVersion.objects.filter(page_id__in=[page["id"] for page in pages]).values_list("page_id", flat=True).distinct())
    title_owners: dict[str, int] = {}
    for page in pages:
        status = page["status"]
        if status not in KNOWN_PAGE_STATUSES:
            raise BackfillPreflightError(f"invalid_status={status} page_id={page['id']}")
        # 有历史版本但指针丢失：回填过程可修复；无任何版本才硬失败。
        # active 页必须最终可进 generation member，因此无版本不可放行。
        if page["current_version_id"] is None and page["id"] not in version_page_ids:
            if status == "active":
                raise BackfillPreflightError(f"page_current_version_missing page_id={page['id']}")
            # 非 active 且无版本：目录归属仍可做，但不进 member；与 complete 路径一致。
        identity = title_identity_key(page["title"])
        if not identity:
            raise BackfillPreflightError(f"invalid_page_title page_id={page['id']}")
        owner = title_owners.get(identity)
        if owner is not None and owner != page["id"]:
            raise BackfillPreflightError(f"duplicate_page_title_identity page_ids={owner},{page['id']} identity={identity}")
        title_owners[identity] = page["id"]


def baseline_already_complete(knowledge_base: WikiKnowledgeBase) -> bool:
    return bool(
        knowledge_base.directory_migration_state in {DirectoryMigrationState.READY.value, DirectoryMigrationState.ENABLED.value}
        and knowledge_base.active_generation_id
        and knowledge_base.active_structure_revision_id
    )


@transaction.atomic
def begin_backfill(knowledge_base_id: int, *, operator: str = "") -> BackfillContext:
    """开启或恢复 backfilling fence，返回可续跑的 preparing generation。"""

    locked = WikiKnowledgeBase.objects.select_for_update().filter(pk=knowledge_base_id).first()
    if locked is None:
        raise BackfillPreflightError(f"knowledge_base_not_found id={knowledge_base_id}")

    if baseline_already_complete(locked):
        raise BackfillPreflightError("baseline_already_complete")

    actor = _actor(operator)

    if locked.directory_migration_state == DirectoryMigrationState.BACKFILLING.value:
        generation = (
            WikiGeneration.objects.select_for_update()
            .filter(
                knowledge_base=locked,
                kind="governance",
                status="preparing",
                base_generation__isnull=True,
            )
            .order_by("-id")
            .first()
        )
        if generation is None:
            raise BackfillPreflightError("backfilling_generation_missing")
        unclassified = WikiDirectory.objects.filter(
            knowledge_base=locked,
            key=UNCLASSIFIED_DIRECTORY_KEY,
        ).first()
        if unclassified is None:
            raise BackfillPreflightError("unclassified_directory_missing")
        return BackfillContext(
            knowledge_base_id=locked.pk,
            generation_id=generation.pk,
            structure_revision_id=generation.structure_revision_id,
            unclassified_directory_id=unclassified.pk,
        )

    if locked.directory_migration_state != DirectoryMigrationState.LEGACY.value:
        raise BackfillPreflightError(f"unexpected_migration_state={locked.directory_migration_state}")

    preflight_legacy_knowledge_base(locked.pk)

    if locked.active_generation_id or locked.active_structure_revision_id:
        raise BackfillPreflightError("legacy_kb_has_partial_active_pointers")
    if WikiGeneration.objects.filter(knowledge_base=locked).exists():
        raise BackfillPreflightError("legacy_kb_has_existing_generations")
    if WikiStructureRevision.objects.filter(knowledge_base=locked).exists():
        raise BackfillPreflightError("legacy_kb_has_existing_structure_revisions")

    advance_migration_state(locked.directory_migration_state, DirectoryMigrationState.BACKFILLING)
    locked.directory_migration_state = DirectoryMigrationState.BACKFILLING.value
    locked.updated_by = actor
    locked.save(update_fields=["directory_migration_state", "updated_by", "updated_at"])

    unclassified = WikiDirectory.objects.filter(
        knowledge_base=locked,
        key=UNCLASSIFIED_DIRECTORY_KEY,
    ).first()
    if unclassified is None:
        unclassified = WikiDirectory.objects.create(
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

    existing_dirs = list(WikiDirectory.objects.filter(knowledge_base=locked).order_by("id"))
    expected_template_keys = {node["restore_key"] for node in _bootstrap_template_nodes(locked.template_key)[1]}
    existing_keys = {directory.key for directory in existing_dirs}
    if not expected_template_keys.issubset(existing_keys - {UNCLASSIFIED_DIRECTORY_KEY}):
        _, template_nodes = _bootstrap_template_nodes(locked.template_key)
        _apply_projection(
            locked,
            template_nodes,
            [],
            [unclassified],
            actor,
        )

    bootstrap_directories = list(WikiDirectory.objects.filter(knowledge_base=locked).order_by("id"))
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
        pipeline_version=BACKFILL_PIPELINE_VERSION,
        source_fingerprints=deepcopy(BACKFILL_SOURCE_FINGERPRINTS),
        status="preparing",
        created_by=actor,
        updated_by=actor,
    )
    return BackfillContext(
        knowledge_base_id=locked.pk,
        generation_id=generation.pk,
        structure_revision_id=revision.pk,
        unclassified_directory_id=unclassified.pk,
    )


def _ensure_page_directory_assignment(
    *,
    page: KnowledgePage,
    unclassified: WikiDirectory,
    generation: WikiGeneration,
    revision: WikiStructureRevision,
    operator: str,
) -> None:
    from_directory_id = page.directory_id
    from_mode = page.directory_assignment_mode or ""
    changed = from_directory_id != unclassified.pk or page.directory_assignment_mode != "auto"
    if changed:
        page.directory = unclassified
        page.directory_assignment_mode = "auto"
        page.save(update_fields=["directory", "directory_assignment_mode", "updated_at"])

    exists = PageDirectoryChange.objects.filter(
        page=page,
        generation=generation,
        source=BACKFILL_CHANGE_SOURCE,
    ).exists()
    if exists:
        return
    PageDirectoryChange.objects.create(
        page=page,
        generation=generation,
        structure_revision=revision,
        from_directory_id=from_directory_id,
        to_directory=unclassified,
        from_assignment_mode=from_mode if from_mode in {"auto", "manual"} else "",
        to_assignment_mode="auto",
        source=BACKFILL_CHANGE_SOURCE,
        operator=operator,
        reason="legacy baseline backfill",
        created_by=operator,
        updated_by=operator,
    )


@transaction.atomic
def complete_backfill(context: BackfillContext, *, batch_size: int = 50, operator: str = "") -> None:
    """把存量页挂入 preparing generation 并激活为 ready baseline。"""

    actor = _actor(operator)
    locked = WikiKnowledgeBase.objects.select_for_update().get(pk=context.knowledge_base_id)
    generation = WikiGeneration.objects.select_for_update().get(
        pk=context.generation_id,
        knowledge_base=locked,
    )
    revision = WikiStructureRevision.objects.get(
        pk=context.structure_revision_id,
        knowledge_base=locked,
    )
    unclassified = WikiDirectory.objects.get(
        pk=context.unclassified_directory_id,
        knowledge_base=locked,
    )
    if generation.status not in {"preparing", "ready"}:
        raise BackfillPreflightError(f"unexpected_generation_status={generation.status}")

    page_ids = list(KnowledgePage.objects.filter(knowledge_base=locked).order_by("id").values_list("id", flat=True))
    for offset in range(0, len(page_ids), max(int(batch_size), 1)):
        batch = page_ids[offset : offset + max(int(batch_size), 1)]
        pages = list(KnowledgePage.objects.select_for_update().filter(pk__in=batch).order_by("id"))
        for page in pages:
            if page.current_version_id is None:
                latest = PageVersion.objects.filter(page_id=page.pk).order_by("-no", "-id").first()
                if latest is not None:
                    PageVersion.objects.filter(page_id=page.pk, is_current=True).exclude(pk=latest.pk).update(is_current=False)
                    if not latest.is_current:
                        latest.is_current = True
                        latest.save(update_fields=["is_current"])
                    page.current_version = latest
                    page.save(update_fields=["current_version", "updated_at"])
            _ensure_page_directory_assignment(
                page=page,
                unclassified=unclassified,
                generation=generation,
                revision=revision,
                operator=actor,
            )
            if page.status != "active":
                continue
            if page.current_version_id is None:
                raise BackfillPreflightError(f"page_current_version_missing page_id={page.pk}")
            put_generation_member(
                generation.pk,
                page_id=page.pk,
                page_version_id=page.current_version_id,
                directory_id=unclassified.pk,
                assignment_mode="auto",
                page_status="active",
            )

    PageRelation.objects.filter(
        from_page__knowledge_base=locked,
        to_page__knowledge_base=locked,
        generation__isnull=True,
    ).update(generation_id=generation.pk)

    if locked.active_structure_revision_id != revision.pk:
        locked.active_structure_revision = revision
        locked.updated_by = actor
        locked.save(update_fields=["active_structure_revision", "updated_by", "updated_at"])

    try:
        mark_generation_ready(generation.pk)
        activation = activate_generation(
            generation.pk,
            requested_base_generation_id=None,
            expected_structure_revision_id=revision.pk,
            expected_structure_version=revision.revision_no,
        )
    except GenerationServiceError as error:
        raise BackfillPreflightError(f"{error.code}: {error}") from error

    if activation.outcome != "active":
        raise BackfillPreflightError(f"activation_failed outcome={activation.outcome} code={activation.code}")

    locked.refresh_from_db()
    advance_migration_state(locked.directory_migration_state, DirectoryMigrationState.READY)
    locked.directory_migration_state = DirectoryMigrationState.READY.value
    locked.directory_enabled = False
    locked.active_generation_id = generation.pk
    locked.updated_by = actor
    locked.save(
        update_fields=[
            "directory_migration_state",
            "directory_enabled",
            "active_generation",
            "updated_by",
            "updated_at",
        ]
    )


# 兼容管理命令 / 测试期望的私有命名。
_begin_backfill = begin_backfill
