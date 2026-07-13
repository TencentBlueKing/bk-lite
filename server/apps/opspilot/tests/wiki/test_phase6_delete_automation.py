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
    from apps.opspilot.models import (
        CheckItem,
        KnowledgePage,
        Material,
        PageVersion,
        WikiDecisionRule,
        WikiKnowledgeBase,
    )
    from apps.opspilot.services.wiki.decision_service import (
        build_participants_from_materials,
        create_rule_if_eligible,
        revoke_rules_for_materials,
    )

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(
        page=page, no=1, body="v", is_current=True, change_type="ai_create"
    )
    page.save()
    mat = Material.objects.create(
        knowledge_base=kb, name="m", material_type="text", text_content="x", content_hash="h1"
    )

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
    from apps.opspilot.models import (
        KnowledgePage,
        PageVersion,
        WikiDecisionRule,
        WikiKnowledgeBase,
    )
    from apps.opspilot.services.wiki.decision_service import (
        create_rule_if_eligible,
        revoke_rules_for_pages,
    )

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(
        page=page, no=1, body="v", is_current=True, change_type="ai_create"
    )
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
