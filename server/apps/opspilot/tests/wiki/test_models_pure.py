import pytest


@pytest.mark.django_db
def test_wiki_models_importable_and_defaults():
    from apps.opspilot.models import (
        BuildRecord,
        CheckItem,
        KnowledgePage,
        Material,
        MaterialVersion,
        PageEvidence,
        PageRelation,
        PageVersion,
        WikiKnowledgeBase,
    )

    kb = WikiKnowledgeBase.objects.create(name="kb1", team=[1], purpose_md="# P", schema_md="# S")
    assert kb.status == "active"
    assert kb.generation_language == "zh"

    material = Material.objects.create(knowledge_base=kb, name="m1", material_type="text", status="pending")
    assert material.material_type == "text" and material.status == "pending"
    mv = MaterialVersion.objects.create(material=material, content_locator="loc", content_hash="h")
    material.current_version = mv
    material.save()

    page = KnowledgePage.objects.create(knowledge_base=kb, page_type="concept", title="t", contribution="ai")
    pv = PageVersion.objects.create(page=page, no=1, body="b", change_type="ai_create", is_current=True)
    page.current_version = pv
    page.save()
    assert pv.is_current is True

    page2 = KnowledgePage.objects.create(knowledge_base=kb, page_type="entity", title="t2")
    rel = PageRelation.objects.create(from_page=page, to_page=page2, relation_type="reference")
    assert rel.weight == 1.0

    PageEvidence.objects.create(page=page, material=material, material_version=mv, locator="p1")

    br = BuildRecord.objects.create(knowledge_base=kb, trigger="material", stage="queued")
    assert br.status == "running"

    chk = CheckItem.objects.create(knowledge_base=kb, check_type="conflict")
    assert chk.status == "open"
