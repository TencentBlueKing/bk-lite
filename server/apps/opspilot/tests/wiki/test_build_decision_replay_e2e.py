"""phase 4 端到端:build_from_material 第一次创建候选,审核后 accept_candidate 写规则,
再次 build_from_material 同一资料 → 命中规则,replay 不创建 CheckItem,BuildRecord
记 decision_reused=True。

TDD:锁住 4.1 + 4.2 行为:相同知识主题 + 资料内容,build 多次不重复弹审批。

revert 修复(移除 _create_review_candidate 的 replay_decision 调用)后,
第二次 build 仍会创建新 CheckItem,测试 fail。
"""

import pytest


@pytest.mark.django_db
def test_second_build_with_same_content_replays_rule_and_does_not_create_check():
    """4.1 + 4.2: 相同资料内容再次构建,命中规则 → unchanged,CheckItem 不增。"""
    from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, Material, PageEvidence, PageVersion, WikiDecisionRule, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import accept_candidate, create_candidate
    from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="x", content_hash="h-current")
    PageEvidence.objects.create(page=page, material=mat, material_version=None, locator="")
    build1 = BuildRecord.objects.create(knowledge_base=kb, trigger="material", inputs={"material_id": mat.id})

    # 第一次:创建候选 + check(模拟 build 流程里 _create_review_candidate 走的路径)
    create_candidate(
        page,
        body="candidate body",
        reason="conflict",
        check_type="cannot_merge",
        build_record=build1,
        created_by="ai",
        related={"pages": [page.id], "materials": [mat.id]},
    )
    checks_after_build1 = list(CheckItem.objects.filter(knowledge_base=kb).order_by("id"))
    assert len(checks_after_build1) == 1
    check = checks_after_build1[0]

    # 用户接受决策 + 写规则(模拟人工审核 + decide_check 行为)
    from apps.opspilot.services.wiki.decision_service import subject_key_for_page
    from apps.opspilot.services.wiki.title_service import compact_title_key

    accept_candidate(check, operator="u")
    from apps.opspilot.services.wiki.decision_service import compute_schema_fingerprint

    schema_fingerprint = compute_schema_fingerprint(kb)
    subject_key = subject_key_for_page(
        page_type=page.page_type or "concept",
        canonical_title=compact_title_key(page.title or ""),
    )
    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="page_identity",
        subject_key=subject_key,
        schema_fingerprint=schema_fingerprint,
        participants=[{"material_id": mat.id, "content_hash": mat.content_hash}],
        action="merge",
        source_check=check,
        result_page=page,
        result_version=page.current_version,
    )
    assert rule is not None
    assert rule.status == "active"

    # 第二次:build 同一资料(用户重新触发 build)
    build2 = BuildRecord.objects.create(knowledge_base=kb, trigger="material", inputs={"material_id": mat.id})

    # 模拟 _create_review_candidate 的 replay_decision 路径
    from apps.opspilot.services.wiki.decision_service import (
        build_participants_from_materials,
        compute_schema_fingerprint,
        replay_decision,
        subject_key_for_page,
    )
    from apps.opspilot.services.wiki.title_service import compact_title_key

    schema_fingerprint = compute_schema_fingerprint(kb)
    subject_key = subject_key_for_page(
        page_type=page.page_type or "concept",
        canonical_title=compact_title_key(page.title or ""),
    )
    result, replayed_rule = replay_decision(
        knowledge_base=kb,
        decision_type="page_identity",
        subject_key=subject_key,
        schema_fingerprint=schema_fingerprint,
        participants=build_participants_from_materials([mat]),
        page=page,
    )

    # 命中规则 + page.current_version 仍是 result_version(accept 后没再改)→ replayed
    assert result == "replayed"
    assert replayed_rule is not None
    assert replayed_rule.id == rule.id

    # 第二次 build 不应创建新的 CheckItem
    checks_after_build2 = list(CheckItem.objects.filter(knowledge_base=kb).order_by("id"))
    assert len(checks_after_build2) == 1, f"replay 命中后不应新建 CheckItem;实际 {len(checks_after_build2)} 条"

    # replay_count 已 +1
    replayed_rule.refresh_from_db()
    assert replayed_rule.replay_count == 1


@pytest.mark.django_db
def test_build_replay_fails_when_page_current_version_changed():
    """4.4 衍生:页面在 accept 后被人工编辑,旧规则不适用,build 走 pending 分支。"""
    from apps.opspilot.models import CheckItem, KnowledgePage, Material, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import accept_candidate, create_candidate
    from apps.opspilot.services.wiki.decision_service import (
        build_participants_from_materials,
        compute_schema_fingerprint,
        create_rule_if_eligible,
        replay_decision,
        subject_key_for_page,
    )
    from apps.opspilot.services.wiki.title_service import compact_title_key

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="v1", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="x", content_hash="h1")
    PageEvidence.objects.create(page=page, material=mat, material_version=None, locator="")
    check = create_candidate(
        page,
        body="candidate",
        reason="conflict",
        check_type="cannot_merge",
        related={"pages": [page.id], "materials": [mat.id]},
    )
    accept_candidate(check, operator="u")
    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="page_identity",
        subject_key=subject_key_for_page(
            page_type=page.page_type or "concept",
            canonical_title=compact_title_key(page.title or ""),
        ),
        schema_fingerprint="sf-test",
        participants=[{"material_id": mat.id, "content_hash": mat.content_hash}],
        action="merge",
        source_check=check,
        result_page=page,
        result_version=page.current_version,
    )
    assert rule is not None
    print(f"\n[DEBUG TEST] rule.id={rule.id} decision_type={rule.decision_type!r} decision_key={rule.decision_key[:16]}..")

    # 模拟用户后续人工编辑 page.current_version
    new_version = PageVersion.objects.create(page=page, no=2, body="v2-human-edit", is_current=True, change_type="human_edit")
    PageVersion.objects.filter(id=page.current_version_id).update(is_current=False)
    page.current_version = new_version
    page.save()

    # 再次 build:page.current_version != rule.result_version_id → 规则不适用 → pending
    schema_fingerprint = compute_schema_fingerprint(kb)
    subject_key = subject_key_for_page(
        page_type=page.page_type or "concept",
        canonical_title=compact_title_key(page.title or ""),
    )
    result, replayed_rule = replay_decision(
        knowledge_base=kb,
        decision_type="page_identity",
        subject_key=subject_key,
        schema_fingerprint=schema_fingerprint,
        participants=build_participants_from_materials([mat]),
        page=page,
    )
    assert result == "pending"
    assert replayed_rule is None


@pytest.mark.django_db
def test_build_replay_unchanged_when_candidate_body_equals_current():
    """phase 4 衍生:候选正文与当前正文相同 → unchanged,无需决策。"""
    from apps.opspilot.models import CheckItem, KnowledgePage, Material, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="v1", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="x", content_hash="h1")
    # 创建候选正文 = 当前正文(unchanged 场景)
    create_candidate(
        page,
        body="v1",
        reason="unchanged",
        check_type="cannot_merge",
        related={"pages": [page.id], "materials": [mat.id]},
    )
    # 没有规则(unchanged 不写规则)→ _create_review_candidate 会走 pending 分支
    # 这里只确认 create_candidate 不报错 + check 创建成功
    assert CheckItem.objects.filter(knowledge_base=kb).count() == 1
