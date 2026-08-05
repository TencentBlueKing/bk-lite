"""知识库整库删除服务测试。"""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_delete_knowledge_base_clears_protected_generation_graph():
    from apps.opspilot.models import KnowledgePage, Material, WikiGeneration, WikiKnowledgeBase, WikiStructureRevision
    from apps.opspilot.services.wiki.kb_delete_service import delete_knowledge_base
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = WikiKnowledgeBase.objects.create(name="kb-to-delete", team=[1])
    bootstrap_knowledge_base(kb, operator="tester")
    kb.refresh_from_db()
    assert kb.active_generation_id
    assert kb.active_structure_revision_id

    Material.objects.create(
        knowledge_base=kb,
        name="m",
        material_type="text",
        text_content="hello",
        status="done",
    )
    KnowledgePage.objects.create(
        knowledge_base=kb,
        page_type="concept",
        title="残留页",
        status="source_invalid",
    )

    result = delete_knowledge_base(kb)

    assert result["knowledge_base_id"] == kb.id
    assert not WikiKnowledgeBase.objects.filter(pk=kb.id).exists()
    assert not WikiGeneration.objects.filter(knowledge_base_id=kb.id).exists()
    assert not WikiStructureRevision.objects.filter(knowledge_base_id=kb.id).exists()
    assert not KnowledgePage.objects.filter(knowledge_base_id=kb.id).exists()
    assert not Material.objects.filter(knowledge_base_id=kb.id).exists()
