"""phase 6: 物理删除资料/页面后,决策规则自动撤销(避免脏数据)。

TDD:
- 6.1: 物理删除资料 → 引用此资料的所有 active 规则被撤销
- 6.3: 物理删除知识页面 → 引用此页面的 active 规则被撤销
- 6.2: 决定命中但不创建 source_invalid 审批
"""

import pytest


@pytest.mark.django_db
def test_delete_material_revokes_referencing_rules():
    """6.1: 物理删除资料 → 引用此资料的所有 active 规则被撤销。"""
    from apps.opspilot.models import KnowledgePage, Material, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.decision_service import build_participants_from_materials, create_rule_if_eligible, revoke_rules_for_materials

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="v", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="x", content_hash="h1")

    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        subject_key="p",
        schema_fingerprint="sf",
        participants=build_participants_from_materials([mat]),
        action="use_new",
        result_page=page,
        result_version=page.current_version,
    )
    assert rule.status == "active"

    affected = revoke_rules_for_materials([mat])
    assert affected == 1
    rule.refresh_from_db()
    assert rule.status == "revoked"


@pytest.mark.django_db
def test_delete_page_revokes_referencing_rules():
    """6.3: 物理删除知识页面 → result_page 引用此页面的 active 规则被撤销。"""
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, revoke_rules_for_pages

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="v", is_current=True, change_type="ai_create")
    page.save()

    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="page_identity",
        subject_key="p",
        schema_fingerprint="sf",
        participants=[],
        action="merge",
        result_page=page,
    )
    assert rule.status == "active"

    affected = revoke_rules_for_pages([page])
    assert affected == 1
    rule.refresh_from_db()
    assert rule.status == "revoked"


@pytest.mark.django_db
def test_handle_material_deletion_revokes_rules_before_physical_delete(monkeypatch):
    from apps.opspilot.models import CheckItem, KnowledgePage, Material, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import decision_service, update_service
    from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible

    kb = WikiKnowledgeBase.objects.create(name="kb-delete-integration", team=[1])
    material = Material.objects.create(
        knowledge_base=kb,
        name="source",
        material_type="text",
        text_content="facts",
        content_hash="material-hash",
    )
    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        title="page",
        page_type="concept",
        contribution="ai",
    )
    version = PageVersion.objects.create(
        page=page,
        no=1,
        body="body",
        is_current=True,
        change_type="ai_create",
    )
    page.current_version = version
    page.save(update_fields=["current_version", "updated_at"])
    PageEvidence.objects.create(page=page, material=material)
    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        subject_key="page::concept::page",
        schema_fingerprint="schema",
        participants=[{"material_id": material.id, "content_hash": material.content_hash}],
        action="keep_current",
        result_page=page,
        result_version=version,
    )
    material_id = material.id
    events = []
    original_revoke = decision_service.revoke_rules_for_materials
    original_delete = Material.delete

    def track_revoke(materials, **kwargs):
        assert Material.objects.filter(pk=material_id).exists()
        events.append("revoke")
        return original_revoke(materials, **kwargs)

    def track_delete(instance, *args, **kwargs):
        events.append("delete")
        return original_delete(instance, *args, **kwargs)

    monkeypatch.setattr(decision_service, "revoke_rules_for_materials", track_revoke)
    monkeypatch.setattr(Material, "delete", track_delete)

    build = update_service.handle_material_deletion(material, operator="admin")

    rule.refresh_from_db()
    assert events[:2] == ["revoke", "delete"]
    assert rule.status == "revoked"
    assert rule.result_snapshot["revoked_reason"] == "资料已物理删除"
    assert rule.updated_by == "admin"
    assert build.counts["pending_review"] == 0
    assert not CheckItem.objects.filter(knowledge_base=kb, status="open").exists()
    assert not Material.objects.filter(pk=material_id).exists()
