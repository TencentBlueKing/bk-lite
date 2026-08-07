"""知识库整库删除：按 PROTECT 依赖顺序拆链后删除。

直接 `WikiKnowledgeBase.delete()` 会撞上 active_generation / generation 成员 /
PageRelation 等 PROTECT 外键（ProtectedError）。本服务先断开指针、删掉受保护
子表，再删知识库本体，并清理 parsed/media 对象存储。
"""

from __future__ import annotations

from django.db import transaction

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import (
    BuildRecord,
    KnowledgePage,
    Material,
    PageDirectoryChange,
    PageRelation,
    PageVersion,
    WikiDirectory,
    WikiGeneration,
    WikiGenerationIndexEntry,
    WikiGenerationOverview,
    WikiGenerationPage,
    WikiImportPreflight,
    WikiKnowledgeBase,
    WikiStructureRevision,
)
from apps.opspilot.services.wiki.parsed_media_service import delete_knowledge_base_media
from apps.opspilot.services.wiki.parsed_storage_service import delete_knowledge_base_parsed_markdown


@transaction.atomic
def delete_knowledge_base(knowledge_base: WikiKnowledgeBase) -> dict:
    """物理删除整个知识库及其治理/页面/资料产物。"""

    kb_id = int(knowledge_base.pk)
    WikiKnowledgeBase.objects.filter(pk=kb_id).update(
        active_generation=None,
        active_structure_revision=None,
    )

    gen_ids = list(WikiGeneration.objects.filter(knowledge_base_id=kb_id).values_list("id", flat=True))
    page_ids = list(KnowledgePage.objects.filter(knowledge_base_id=kb_id).values_list("id", flat=True))

    # generation / page 侧受 PROTECT 的派生表先删
    if gen_ids:
        PageRelation.objects.filter(generation_id__in=gen_ids).delete()
        WikiGenerationIndexEntry.objects.filter(generation_id__in=gen_ids).delete()
        WikiGenerationOverview.objects.filter(generation_id__in=gen_ids).delete()
        WikiGenerationPage.objects.filter(generation_id__in=gen_ids).delete()
        PageDirectoryChange.objects.filter(generation_id__in=gen_ids).delete()

    if page_ids:
        PageRelation.objects.filter(from_page_id__in=page_ids).delete()
        PageRelation.objects.filter(to_page_id__in=page_ids).delete()
        PageDirectoryChange.objects.filter(page_id__in=page_ids).delete()
        PageVersion.objects.filter(page_id__in=page_ids).update(created_in_generation=None)
        KnowledgePage.objects.filter(id__in=page_ids).update(
            directory=None,
            current_version=None,
        )

    BuildRecord.objects.filter(knowledge_base_id=kb_id).update(
        generation=None,
        base_generation=None,
        rollback_of_generation=None,
        structure_revision=None,
    )
    WikiImportPreflight.objects.filter(knowledge_base_id=kb_id).update(
        base_generation=None,
        structure_revision=None,
        classification_root=None,
    )
    Material.objects.filter(knowledge_base_id=kb_id).update(classification_root=None)

    WikiGeneration.objects.filter(knowledge_base_id=kb_id).update(
        build_record=None,
        base_generation=None,
        rollback_of=None,
    )
    WikiDirectory.objects.filter(knowledge_base_id=kb_id).update(
        parent=None,
        merged_into=None,
    )

    WikiGeneration.objects.filter(knowledge_base_id=kb_id).delete()
    BuildRecord.objects.filter(knowledge_base_id=kb_id).delete()

    if page_ids:
        PageVersion.objects.filter(page_id__in=page_ids).delete()
    KnowledgePage.objects.filter(knowledge_base_id=kb_id).delete()

    WikiDirectory.objects.filter(knowledge_base_id=kb_id).delete()
    WikiStructureRevision.objects.filter(knowledge_base_id=kb_id).delete()

    # Material / CheckItem / DecisionRule / ImportPreflight 等对 KB 为 CASCADE
    Material.objects.filter(knowledge_base_id=kb_id).delete()

    deleted, _ = WikiKnowledgeBase.objects.filter(pk=kb_id).delete()
    if deleted == 0:
        raise RuntimeError(f"knowledge base {kb_id} was not deleted")

    parsed = delete_knowledge_base_parsed_markdown(kb_id)
    media = delete_knowledge_base_media(kb_id)
    logger.info(
        "wiki knowledge base deleted kb=%s parsed=%s media=%s",
        kb_id,
        parsed,
        media,
    )
    return {
        "knowledge_base_id": kb_id,
        "parsed": parsed,
        "media": media,
    }
