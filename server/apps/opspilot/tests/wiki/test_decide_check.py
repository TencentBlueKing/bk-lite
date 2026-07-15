"""phase 3: 语义化 decide API + 知识冲突决策中心 3 选 1 + 规则写入。

TDD:先失败测试,锁住 phase 3 行为:
- decide_check 三种动作语义化(keep_current / use_new / edit_accept)
- edit_accept 空正文拒绝
- 错误动作拒绝
- 决策结果必须写 WikiDecisionRule
- use_new / edit_accept 触发 PageEvidence 补齐
- keep_current 不补证据
- decide 拒绝错误的 decision_type 错误动作
- accept_candidate 锁当前版本竞态:候选创建后到决策前页面变化,过期决策不覆盖

revert 修复(删除 decide_check 或决策服务)后,所有 import 失败,测试报错。
"""

import pytest

# ============================================================================
# phase 3.1: 知识冲突 3 选 1 语义化
# ============================================================================


@pytest.mark.django_db
def test_decide_check_keep_current_marks_resolved_without_evicting_candidate():
    """3.1: keep_current 把 check 标 resolved,候选版本不删除(供审计),不补证据。"""
    from apps.opspilot.models import KnowledgePage, Material, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="new", content_hash="h1")
    check = create_candidate(
        page,
        body="candidate",
        reason="conflict",
        check_type="cannot_merge",
        incoming_material=mat,
    )
    check.candidate_version.page = page
    check.candidate_version.save()

    decide_check(check, action="keep_current", operator="u")

    check.refresh_from_db()
    page.refresh_from_db()
    assert check.status == "resolved"
    # 当前版本保持原样
    assert page.current_version.body == "current"
    # keep_current 不补证据
    assert PageEvidence.objects.filter(material=mat, page=page).count() == 0
    # 候选版本保留(供审计)
    assert PageVersion.objects.filter(id=check.candidate_version_id).exists()


@pytest.mark.django_db
def test_decide_check_use_new_promotes_candidate_and_records_evidence():
    """3.1: use_new 把候选正文置为 current,新资料写入 PageEvidence。"""
    from apps.opspilot.models import KnowledgePage, Material, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="new", content_hash="h1")
    check = create_candidate(
        page,
        body="candidate",
        reason="conflict",
        check_type="cannot_merge",
        incoming_material=mat,
    )

    decide_check(check, action="use_new", operator="u", material=mat)

    check.refresh_from_db()
    page.refresh_from_db()
    assert check.status == "resolved"
    assert page.current_version.body == "candidate"
    # use_new 必须补证据
    assert PageEvidence.objects.filter(material=mat, page=page).exists()


@pytest.mark.django_db
def test_decide_check_edit_accept_uses_edited_body_and_records_evidence():
    """3.1: edit_accept 用编辑后正文创建新当前版本,并补证据。"""
    from apps.opspilot.models import KnowledgePage, Material, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="new", content_hash="h1")
    check = create_candidate(
        page,
        body="candidate",
        reason="conflict",
        check_type="cannot_merge",
        incoming_material=mat,
    )

    decide_check(
        check,
        action="edit_accept",
        operator="u",
        body="EDITED-BODY",
        material=mat,
    )

    page.refresh_from_db()
    assert check.status == "resolved"
    assert page.current_version.body == "EDITED-BODY"
    assert PageEvidence.objects.filter(material=mat, page=page).exists()


@pytest.mark.django_db
def test_decide_check_edit_accept_empty_body_rejected():
    """3.1: edit_accept 空正文拒绝,check / page / candidate 保持不变。"""
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    check = create_candidate(page, body="candidate", reason="conflict", check_type="cannot_merge")

    with pytest.raises(ValueError):
        decide_check(check, action="edit_accept", operator="u", body="")
    with pytest.raises(ValueError):
        decide_check(check, action="edit_accept", operator="u", body="   ")

    check.refresh_from_db()
    page.refresh_from_db()
    assert check.status == "open"
    assert page.current_version.body == "current"
    assert PageVersion.objects.filter(id=check.candidate_version_id).exists()


@pytest.mark.django_db
def test_decide_check_rejects_page_merge_action_for_knowledge_conflict():
    """3.1: 知识冲突不接受页面合并动作;页面合并决策通过别的 check_type 路径。"""
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    check = create_candidate(page, body="candidate", reason="conflict", check_type="cannot_merge")

    with pytest.raises(ValueError):
        decide_check(check, action="merge", operator="u")
    with pytest.raises(ValueError):
        decide_check(check, action="keep_separate", operator="u")
    with pytest.raises(ValueError):
        decide_check(check, action="not_a_real_action", operator="u")


# ============================================================================
# phase 3.2: 决策结果必须写 WikiDecisionRule
# ============================================================================


@pytest.mark.django_db
def test_decide_check_writes_decision_rule():
    """3.2: 决策结果必须写 WikiDecisionRule,签名含 material_id + content_hash,subject_key 稳定。"""
    from apps.opspilot.models import KnowledgePage, Material, PageVersion, WikiDecisionRule, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="服务操作手册", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="new", content_hash="h1")
    check = create_candidate(page, body="candidate", reason="conflict", check_type="cannot_merge", incoming_material=mat)

    decide_check(check, action="use_new", operator="u", material=mat)

    rules = WikiDecisionRule.objects.all()
    assert rules.count() == 1
    rule = rules.first()
    assert rule.action == "use_new"
    assert rule.decision_type == "knowledge_conflict"
    assert rule.status == "active"
    assert len(rule.decision_key) == 64  # SHA-256 hex
    # subject_key 与 KB 绑定
    assert rule.subject_key.startswith("page::concept::")
    # result_page 指向该页
    assert rule.result_page_id == page.id
    # match_snapshot 含参与者
    assert rule.match_snapshot["participants"][0]["material_id"] == mat.id


@pytest.mark.django_db
def test_keep_current_without_complete_frozen_context_auto_resolves_without_rule():
    """缺 frozen incoming 时不可人工处理，应自动关闭且不得写回放规则。"""
    from apps.opspilot.models import KnowledgePage, Material, PageEvidence, PageVersion, WikiDecisionRule, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    material = Material.objects.create(
        knowledge_base=kb,
        name="m",
        material_type="text",
        content_hash="h-current",
    )
    PageEvidence.objects.create(page=page, material=material, locator="")
    check = create_candidate(
        page,
        body="candidate",
        reason="conflict",
        check_type="cannot_merge",
    )

    rule = decide_check(check, action="keep_current", operator="u")

    check.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.related["resolution"]["reason"] == "decision_context_incomplete"
    assert rule is None
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


# ============================================================================
# phase 3.4: 当前版本竞态保护
# ============================================================================


@pytest.mark.django_db
def test_decide_check_auto_resolves_if_page_current_version_changed():
    """3.4: 候选创建时锁定 current_version,审批时重新校验,过期决策不覆盖。"""
    from apps.opspilot.models import KnowledgePage, Material, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="v1", is_current=True, change_type="ai_create")
    page.save()
    material = Material.objects.create(
        knowledge_base=kb,
        name="incoming",
        material_type="text",
        content_hash="incoming-v1",
    )
    check = create_candidate(
        page,
        body="candidate",
        reason="conflict",
        check_type="cannot_merge",
        incoming_material=material,
    )
    # 检查点:candidate 创建时记下当时的 current_version_id
    locked_version_id = check.decision_context.get("locked_current_version_id") or page.current_version_id
    # 模拟后台有人更新了 current_version
    new_version = PageVersion.objects.create(page=page, no=2, body="v2", is_current=True, change_type="ai_merge")
    PageVersion.objects.filter(id=locked_version_id).update(is_current=False)
    page.current_version = new_version
    page.save()

    # 旧决定用新 current 校验，过期后自动关闭，避免继续出现在待决策列表。
    assert decide_check(check, action="use_new", operator="u") is None

    check.refresh_from_db()
    page.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.related["resolution"]["action"] == "automatic_maintenance"
    assert check.related["resolution"]["reason"] == "decision_context_stale"
    assert page.current_version.body == "v2"


# ============================================================================
# phase 3.5: 决策中心 API
# ============================================================================


@pytest.mark.django_db
def test_decide_api_endpoint_accepts_semantic_actions():
    """3.5: POST /check_item/{id}/decide/ 接受语义化动作,按 decision_type 校验。"""
    from unittest.mock import patch

    from apps.opspilot.models import KnowledgePage, Material, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="new", content_hash="h1")
    check = create_candidate(page, body="candidate", reason="conflict", check_type="cannot_merge")
    with patch("apps.opspilot.viewsets.wiki_check_view.decide_check") as mocked_decide:
        # 端点:POST /api/v1/opspilot/check_item/{id}/decide/
        from rest_framework.test import APIRequestFactory, force_authenticate

        from apps.base.models import User
        from apps.opspilot.viewsets.wiki_check_view import WikiCheckViewSet

        mocked_decide.return_value = check
        user = User.objects.create_user(
            username="api_user", password="x", domain="domain.com", locale="en", group_list=[{"id": 1, "name": "T"}], roles=["admin"]
        )
        user.is_superuser = True
        user.save()

        factory = APIRequestFactory()
        request = factory.post(
            f"/api/v1/opspilot/check_item/{check.id}/decide/",
            data={"action": "use_new", "material_id": mat.id},
            format="json",
        )
        force_authenticate(request, user=user)
        view = WikiCheckViewSet.as_view({"post": "decide"})
        view(request, pk=check.id)
        assert mocked_decide.called


@pytest.mark.django_db
def test_decide_api_endpoint_rejects_unknown_action():
    """3.5: 未知 action 返回 400,不动数据。"""
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.base.models import User
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate
    from apps.opspilot.viewsets.wiki_check_view import WikiCheckViewSet

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    check = create_candidate(page, body="candidate", reason="conflict", check_type="cannot_merge")
    user = User.objects.create_user(
        username="api_user2", password="x", domain="domain.com", locale="en", group_list=[{"id": 1, "name": "T"}], roles=["admin"]
    )
    user.is_superuser = True
    user.save()

    factory = APIRequestFactory()
    request = factory.post(
        f"/api/v1/opspilot/check_item/{check.id}/decide/",
        data={"action": "garbage"},
        format="json",
    )
    force_authenticate(request, user=user)
    view = WikiCheckViewSet.as_view({"post": "decide"})
    response = view(request, pk=check.id)
    assert response.status_code == 400
    check.refresh_from_db()
    assert check.status == "open"


# ============================================================================
# phase 3.6: serializer 暴露字段
# ============================================================================


@pytest.mark.django_db
def test_check_serializer_exposes_decision_fields():
    """3.6: CheckItem serializer 暴露 decision_type / decision_key / decision_context 给前端决策中心。"""
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.serializers.wiki_serializers import CheckItemSerializer
    from apps.opspilot.services.wiki.check_service import create_candidate

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    check = create_candidate(page, body="candidate", reason="conflict", check_type="cannot_merge")
    check.decision_key = "a" * 64
    check.decision_context = {"snap": "v1"}
    check.save()

    data = CheckItemSerializer(check).data
    assert data.get("decision_key") == "a" * 64
    assert data.get("decision_context") == {}


def _create_frozen_conflict():
    from apps.opspilot.models import KnowledgePage, Material, MaterialVersion, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate

    kb = WikiKnowledgeBase.objects.create(name="kb-frozen-conflict", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="服务手册", page_type="concept")
    current = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.current_version = current
    page.save(update_fields=["current_version", "updated_at"])
    source = Material.objects.create(knowledge_base=kb, name="source-a", material_type="text", content_hash="material-a")
    source_version = MaterialVersion.objects.create(material=source, content_hash="version-a")
    PageEvidence.objects.create(page=page, material=source, material_version=source_version)
    incoming = Material.objects.create(knowledge_base=kb, name="incoming-b", material_type="text", content_hash="material-b")
    incoming_version = MaterialVersion.objects.create(material=incoming, content_hash="version-b")
    incoming.current_version = incoming_version
    incoming.save(update_fields=["current_version", "updated_at"])
    check = create_candidate(
        page,
        body="candidate",
        reason="cannot merge",
        check_type="cannot_merge",
        incoming_material=incoming,
        incoming_material_version=incoming_version,
    )
    return kb, page, current, source, source_version, incoming, incoming_version, check


@pytest.mark.django_db
def test_create_candidate_freezes_complete_decision_context():
    from apps.opspilot.services.wiki.check_service import _body_hash

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()

    context = check.decision_context
    assert len(check.decision_key) == 64
    assert context["locked_current_version_id"] == current.id
    assert context["decision_type"] == "knowledge_conflict"
    assert context["subject_key"].startswith("page::concept::")
    assert context["schema_fingerprint"]
    assert context["incoming"] == {
        "material_id": incoming.id,
        "material_version_id": incoming_version.id,
        "content_hash": "version-b",
    }
    assert {(item["material_id"], item["content_hash"]) for item in context["participants"]} == {
        (source.id, "version-a"),
        (incoming.id, "version-b"),
    }
    assert context["current_body_hash"] == _body_hash("current")
    assert context["candidate_body_hash"] == _body_hash("candidate")
    assert context["page_identity"]["page_id"] == page.id


@pytest.mark.django_db
@pytest.mark.parametrize("invalid_context", ["missing_hash", "missing_participant"])
def test_incomplete_frozen_incoming_auto_resolves_without_creating_rule(invalid_context):
    from apps.opspilot.models import WikiDecisionRule
    from apps.opspilot.services.wiki.check_service import decide_check

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()
    context = dict(check.decision_context)
    if invalid_context == "missing_hash":
        context["incoming"] = {
            **context["incoming"],
            "content_hash": "",
        }
    else:
        context["participants"] = [item for item in context["participants"] if item["material_id"] != incoming.id]
    check.decision_context = context
    check.save(update_fields=["decision_context", "updated_at"])

    rule = decide_check(check, action="use_new", operator="reviewer")

    page.refresh_from_db()
    check.refresh_from_db()
    assert page.current_version.body == "current"
    assert check.status == "auto_resolved"
    assert check.related["resolution"]["reason"] == "decision_context_incomplete"
    assert rule is None
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


@pytest.mark.django_db
def test_result_snapshot_preserves_winner_sources_across_role_reversal():
    from apps.opspilot.services.wiki.check_service import decide_check

    first = _create_frozen_conflict()
    source = first[3]
    incoming = first[5]
    incoming_version = first[6]
    use_new_rule = decide_check(
        first[7],
        action="use_new",
        operator="reviewer",
    )
    assert use_new_rule.result_snapshot["winner_participants"] == [
        {
            "material_id": incoming.id,
            "material_version_id": incoming_version.id,
            "content_hash": "version-b",
        }
    ]

    second = _create_frozen_conflict()
    current_source = second[3]
    current_source_version = second[4]
    rejected_incoming = second[5]
    keep_rule = decide_check(
        second[7],
        action="keep_current",
        operator="reviewer",
    )
    assert keep_rule.result_snapshot["winner_participants"] == [
        {
            "material_id": current_source.id,
            "material_version_id": current_source_version.id,
            "content_hash": "version-a",
        }
    ]
    assert all(item["material_id"] != rejected_incoming.id for item in keep_rule.result_snapshot["winner_participants"])
    assert source.id != incoming.id


@pytest.mark.django_db
def test_edit_accept_records_final_version_hash_and_adopted_participants():
    from apps.opspilot.services.wiki.check_service import _body_hash, decide_check

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()

    rule = decide_check(
        check,
        action="edit_accept",
        operator="reviewer",
        body="human edited result",
    )

    page.refresh_from_db()
    adopted = {(item["material_id"], item["content_hash"]) for item in rule.result_snapshot["adopted_participants"]}
    assert adopted == {
        (source.id, "version-a"),
        (incoming.id, "version-b"),
    }
    assert rule.result_snapshot["edited_result"] == {
        "result_version_id": page.current_version_id,
        "body_hash": _body_hash("human edited result"),
    }


@pytest.mark.django_db
def test_create_candidate_reuses_same_open_decision_key():
    from apps.opspilot.models import CheckItem, PageVersion
    from apps.opspilot.services.wiki.check_service import create_candidate

    kb, page, current, source, source_version, incoming, incoming_version, first = _create_frozen_conflict()
    second = create_candidate(
        page,
        body="candidate",
        reason="duplicate delivery",
        check_type="cannot_merge",
        incoming_material=incoming,
        incoming_material_version=incoming_version,
    )

    assert second.id == first.id
    assert CheckItem.objects.filter(knowledge_base=kb, decision_key=first.decision_key, status="open").count() == 1
    assert PageVersion.objects.filter(page=page, change_type="candidate").count() == 1


@pytest.mark.django_db
def test_use_new_uses_frozen_incoming_evidence_without_client_material():
    from apps.opspilot.models import PageEvidence
    from apps.opspilot.services.wiki.check_service import decide_check

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()

    decide_check(check, action="use_new", operator="reviewer")

    assert PageEvidence.objects.filter(
        page=page,
        material=incoming,
        material_version=incoming_version,
    ).exists()


@pytest.mark.django_db
def test_use_new_leaves_exactly_one_current_version():
    from apps.opspilot.models import PageVersion
    from apps.opspilot.services.wiki.check_service import decide_check

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()

    decide_check(check, action="use_new", operator="reviewer")

    current.refresh_from_db()
    assert not current.is_current
    assert PageVersion.objects.filter(page=page, is_current=True).count() == 1


@pytest.mark.django_db
def test_decision_rule_records_semantic_action_operator_and_full_snapshots():
    from apps.opspilot.services.wiki.check_service import decide_check

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()

    rule = decide_check(check, action="use_new", operator="reviewer")

    assert rule.action == "use_new"
    assert rule.created_by == "reviewer"
    assert rule.result_snapshot["action"] == "use_new"
    assert rule.result_snapshot["operator"] == "reviewer"
    assert len(rule.match_snapshot["participants"]) == 2


@pytest.mark.django_db
def test_decide_api_rejects_material_from_another_knowledge_base():
    import json

    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.base.models import User
    from apps.opspilot.models import Material, WikiKnowledgeBase
    from apps.opspilot.viewsets.wiki_check_view import WikiCheckViewSet

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()
    other_kb = WikiKnowledgeBase.objects.create(name="other-kb", team=[1])
    other_material = Material.objects.create(
        knowledge_base=other_kb,
        name="cross-kb",
        material_type="text",
        content_hash="cross-hash",
    )
    user = User.objects.create_user(
        username="cross_kb_user",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T"}],
        roles=["admin"],
    )
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    request = APIRequestFactory().post(
        f"/api/v1/opspilot/check_item/{check.id}/decide/",
        data={"action": "use_new", "material_id": other_material.id},
        format="json",
    )
    force_authenticate(request, user=user)

    response = WikiCheckViewSet.as_view({"post": "decide"})(request, pk=check.id)

    assert response.status_code == 400
    assert "同一知识库" in json.loads(response.content)["message"]
    check.refresh_from_db()
    assert check.status == "open"


@pytest.mark.django_db
def test_create_candidate_can_lock_page_without_current_version():
    from apps.opspilot.models import KnowledgePage, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate

    kb = WikiKnowledgeBase.objects.create(name="kb-no-current", team=[1])
    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        title="new page",
        page_type="concept",
    )

    assert create_candidate(page, body="candidate", reason="new").candidate_version_id


@pytest.mark.django_db
def test_processed_decision_serializer_exposes_rule_audit_contract():
    from apps.opspilot.serializers.wiki_serializers import CheckItemSerializer
    from apps.opspilot.services.wiki.check_service import decide_check

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()
    rule = decide_check(check, action="use_new", operator="reviewer")

    data = CheckItemSerializer(check).data

    assert data["decision_type"] == "knowledge_conflict"
    assert data["decision_action"] == "use_new"
    assert data["decision_operator"] == "reviewer"
    assert data["decision_processed_at"]
    assert data["decision_rule"] == {
        "id": rule.id,
        "status": "active",
        "action": "use_new",
        "match_snapshot": rule.match_snapshot,
        "result_snapshot": rule.result_snapshot,
        "replay_count": 0,
        "last_replayed_at": None,
        "revoked_reason": "",
    }


@pytest.mark.django_db
def test_decision_list_filters_pending_and_processed_only():
    import json

    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.base.models import User
    from apps.opspilot.models import CheckItem
    from apps.opspilot.viewsets.wiki_check_view import WikiCheckViewSet

    kb, page, current, source, source_version, incoming, incoming_version, pending = _create_frozen_conflict()
    processed = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="material_update",
        status="resolved",
        decision_key="f" * 64,
        decision_context={"decision_type": "knowledge_conflict"},
    )
    CheckItem.objects.create(
        knowledge_base=kb,
        check_type="orphan",
        status="auto_resolved",
    )
    stale_decision = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="material_update",
        status="auto_resolved",
        decision_key="e" * 64,
        decision_context={"decision_type": "knowledge_conflict"},
        related={"resolution": {"reason_code": "decision_context_stale"}},
    )
    user = User.objects.create_user(
        username="decision_list_user",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T"}],
        roles=["admin"],
    )
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    view = WikiCheckViewSet.as_view({"get": "list"})
    factory = APIRequestFactory()

    pending_request = factory.get(
        "/api/v1/opspilot/check_item/",
        {"knowledge_base": kb.id, "view": "pending"},
    )
    force_authenticate(pending_request, user=user)
    pending_response = view(pending_request)
    processed_request = factory.get(
        "/api/v1/opspilot/check_item/",
        {"knowledge_base": kb.id, "view": "processed"},
    )
    force_authenticate(processed_request, user=user)
    processed_response = view(processed_request)

    assert [item["id"] for item in json.loads(pending_response.content)["data"]["items"]] == [pending.id]
    assert [item["id"] for item in json.loads(processed_response.content)["data"]["items"]] == [
        stale_decision.id,
        processed.id,
    ]


@pytest.mark.django_db
def test_approval_detail_hides_non_decision_diagnostic(api_client):
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    diagnostic = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="orphan",
        status="auto_resolved",
        related={
            "resolution": {"action": "automatic_maintenance"},
        },
    )

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/check_item/{diagnostic.id}/")
    assert response.status_code == 404, response.content
    diagnostic.refresh_from_db()
    assert diagnostic.status == "auto_resolved"


@pytest.mark.django_db
def test_revoke_rule_api_preserves_current_knowledge_and_exposes_reason():
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.base.models import User
    from apps.opspilot.serializers.wiki_serializers import CheckItemSerializer
    from apps.opspilot.services.wiki.check_service import decide_check
    from apps.opspilot.viewsets.wiki_check_view import WikiCheckViewSet

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()
    rule = decide_check(check, action="use_new", operator="reviewer")
    page.refresh_from_db()
    approved_version_id = page.current_version_id
    approved_body = page.current_version.body
    user = User.objects.create_user(
        username="decision_revoke_user",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T"}],
        roles=["admin"],
    )
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    request = APIRequestFactory().post(
        f"/api/v1/opspilot/check_item/{check.id}/revoke_rule/",
        {"rule_id": rule.id, "reason": "需要重新评估"},
        format="json",
    )
    force_authenticate(request, user=user)

    response = WikiCheckViewSet.as_view({"post": "revoke_rule"})(request, pk=check.id)

    assert response.status_code == 200
    rule.refresh_from_db()
    page.refresh_from_db()
    assert rule.status == "revoked"
    assert rule.result_snapshot["revoked_reason"] == "需要重新评估"
    assert page.current_version_id == approved_version_id
    assert page.current_version.body == approved_body
    check.refresh_from_db()
    serialized = CheckItemSerializer(check).data
    assert serialized["decision_rule"]["revoked_reason"] == "需要重新评估"


@pytest.mark.django_db
def test_knowledge_conflict_serializer_exposes_complete_two_sided_cards():
    from apps.opspilot.serializers.wiki_serializers import CheckItemSerializer

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()

    data = CheckItemSerializer(check).data

    current_card = data["current_knowledge"]
    new_card = data["new_knowledge"]
    assert current_card["page_id"] == page.id
    assert current_card["title"] == page.title
    assert current_card["body"] == "current"
    assert current_card["source_label"] == source.name
    assert current_card["version_label"] == "v1"
    assert current_card["source_count"] == 1
    assert current_card["relation_count"] == 0
    assert current_card["contribution"] == page.contribution
    assert new_card["page_id"] == page.id
    assert new_card["body"] == "candidate"
    assert new_card["source_label"] == incoming.name
    assert new_card["version_label"] == "v2"
    assert new_card["material_id"] == incoming.id
    assert new_card["material_version_id"] == incoming_version.id
    assert data["related_pages"][0]["contribution"] == page.contribution
    assert data["related_pages"][0]["source_count"] == 1
    assert data["related_pages"][0]["relation_count"] == 0
    assert data["related_pages"][0]["version_label"] == "v1"


@pytest.mark.django_db
def test_page_identity_serializer_uses_frozen_target_not_related_order():
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.serializers.wiki_serializers import CheckItemSerializer
    from apps.opspilot.services.wiki.check_service import ensure_check

    kb = WikiKnowledgeBase.objects.create(name="kb-page-cards", team=[1])
    source = KnowledgePage.objects.create(
        knowledge_base=kb,
        title="CMDB",
        page_type="entity",
    )
    source_version = PageVersion.objects.create(
        page=source,
        no=3,
        body="source body",
        change_type="ai_create",
        is_current=True,
    )
    source.current_version = source_version
    source.save(update_fields=["current_version", "updated_at"])
    target = KnowledgePage.objects.create(
        knowledge_base=kb,
        title="配置平台",
        page_type="entity",
    )
    target_version = PageVersion.objects.create(
        page=target,
        no=7,
        body="target body",
        change_type="human_edit",
        is_current=True,
    )
    target.current_version = target_version
    target.save(update_fields=["current_version", "updated_at"])
    check = ensure_check(
        kb,
        "duplicate",
        source,
        related={
            "pages": [source.id, target.id],
            "canonical_title": "配置平台",
        },
    )[0]
    check.related = {
        "pages": [target.id, source.id],
        "canonical_title": "配置平台",
    }
    check.save(update_fields=["related", "updated_at"])

    data = CheckItemSerializer(check).data

    assert data["current_knowledge"]["page_id"] == target.id
    assert data["current_knowledge"]["body"] == "target body"
    assert data["current_knowledge"]["version_label"] == "v7"
    assert data["new_knowledge"]["page_id"] == source.id
    assert data["new_knowledge"]["body"] == "source body"
    assert data["new_knowledge"]["version_label"] == "v3"


def _semantic_check_for_generic_action(kb, check_type):
    from apps.opspilot.models import CheckItem, KnowledgePage, PageVersion

    related = {}
    if check_type == "duplicate":
        pages = []
        for title in ("target", "source"):
            page = KnowledgePage.objects.create(
                knowledge_base=kb,
                title=title,
                page_type="concept",
            )
            page.current_version = PageVersion.objects.create(
                page=page,
                no=1,
                body=title,
                is_current=True,
                change_type="ai_create",
            )
            page.save(update_fields=["current_version"])
            pages.append(page)
        related = {"pages": [page.id for page in pages]}
    return CheckItem.objects.create(
        knowledge_base=kb,
        check_type=check_type,
        status="open",
        related=related,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("check_type", ["cannot_merge", "material_update", "duplicate", "conflict"])
@pytest.mark.parametrize("endpoint", ["accept", "reject", "merge", "resolve"])
def test_generic_detail_actions_fail_closed_for_semantic_checks(api_client, check_type, endpoint):
    from apps.opspilot.models import WikiKnowledgeBase

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    check = _semantic_check_for_generic_action(kb, check_type)

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/{endpoint}/",
        {},
        format="json",
    )

    assert response.status_code == 410, response.content
    assert "decide" in response.json()["message"]
    check.refresh_from_db()
    assert check.status == "open"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("endpoint", "result_key"),
    [
        ("batch_accept", "accepted"),
        ("batch_reject", "rejected"),
        ("batch_resolve", "resolved"),
    ],
)
def test_generic_batch_actions_skip_all_semantic_checks(api_client, endpoint, result_key):
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    checks = [_semantic_check_for_generic_action(kb, check_type) for check_type in ("cannot_merge", "material_update", "duplicate", "conflict")]

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{endpoint}/",
        {"ids": [check.id for check in checks]},
        format="json",
    )

    assert response.status_code == 410, response.content
    assert "decide" in response.json()["message"]
    assert set(
        CheckItem.objects.filter(id__in=[check.id for check in checks], status="open").values_list(
            "id",
            flat=True,
        )
    ) == {check.id for check in checks}


@pytest.mark.django_db
def test_check_endpoints_are_scoped_to_user_knowledge_base_teams(api_client):
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase

    own_kb = WikiKnowledgeBase.objects.create(name="own", team=[1])
    foreign_kb = WikiKnowledgeBase.objects.create(name="foreign", team=[2])
    own_check = CheckItem.objects.create(
        knowledge_base=own_kb,
        check_type="conflict",
        status="open",
    )
    foreign_check = CheckItem.objects.create(
        knowledge_base=foreign_kb,
        check_type="conflict",
        status="open",
    )

    listed = api_client.get("/api/v1/opspilot/wiki_mgmt/check_item/")
    foreign_filtered = api_client.get(f"/api/v1/opspilot/wiki_mgmt/check_item/?knowledge_base={foreign_kb.id}")
    retrieved = api_client.get(f"/api/v1/opspilot/wiki_mgmt/check_item/{foreign_check.id}/")
    decided = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{foreign_check.id}/decide/",
        {"action": "keep_separate"},
        format="json",
    )
    revoked = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{foreign_check.id}/revoke_rule/",
        {},
        format="json",
    )

    assert listed.status_code == 200, listed.content
    assert [item["id"] for item in listed.json()["data"]["items"]] == [own_check.id]
    assert foreign_filtered.json()["data"]["count"] == 0
    assert retrieved.status_code == 403, retrieved.content
    assert decided.status_code == 403, decided.content
    assert revoked.status_code == 403, revoked.content


@pytest.mark.django_db
def test_legacy_knowledge_decision_auto_resolves_without_applying_or_rule():
    from apps.opspilot.models import CheckItem, KnowledgePage, Material, PageEvidence, PageVersion, WikiDecisionRule, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], schema_md="# schema")
    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        title="legacy",
        page_type="concept",
    )
    current = PageVersion.objects.create(
        page=page,
        no=1,
        body="current",
        is_current=True,
        change_type="ai_create",
    )
    candidate = PageVersion.objects.create(
        page=page,
        no=2,
        body="candidate",
        is_current=False,
        change_type="candidate",
    )
    page.current_version = current
    page.save(update_fields=["current_version"])
    material = Material.objects.create(
        knowledge_base=kb,
        name="source",
        material_type="text",
        content_hash="stable-hash",
    )
    PageEvidence.objects.create(page=page, material=material, locator="legacy")
    check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="cannot_merge",
        status="open",
        candidate_version=candidate,
        related={"page_id": page.id},
    )

    rule = decide_check(check, "use_new", operator="alice")

    page.refresh_from_db()
    check.refresh_from_db()
    assert page.current_version_id == current.id
    assert check.status == "auto_resolved"
    assert check.related["resolution"]["reason"] == "decision_context_incomplete"
    assert rule is None
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


@pytest.mark.django_db
def test_legacy_page_identity_decision_fails_closed_without_inferring_context(api_client):
    from apps.opspilot.models import KnowledgePage, WikiDecisionRule, WikiKnowledgeBase

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    check = _semantic_check_for_generic_action(kb, "duplicate")
    page_ids = list(check.related["pages"])

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/decide/",
        {"action": "merge"},
        format="json",
    )

    assert response.status_code == 409, response.content
    assert response.json()["message"] == "审批上下文已失效，系统已自动关闭该待决策项"
    check.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.suggested_actions == []
    assert check.related["resolution"]["reason"] == "decision_context_stale"
    assert check.decision_key == ""
    assert check.decision_context == {}
    assert set(
        KnowledgePage.objects.filter(id__in=page_ids, status="active").values_list(
            "id",
            flat=True,
        )
    ) == set(page_ids)
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


@pytest.mark.django_db
def test_decide_api_returns_409_and_preserves_page_when_live_context_drifted(api_client):
    from apps.opspilot.models import WikiDecisionRule

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()
    kb.schema_md = "# changed after decision freeze"
    kb.save(update_fields=["schema_md", "updated_at"])

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/decide/",
        {"action": "use_new"},
        format="json",
    )

    assert response.status_code == 409, response.content
    payload = response.json()
    assert payload["message"] == "审批上下文已失效，系统已自动关闭该待决策项"
    assert payload["data"]["check"]["status"] == "auto_resolved"
    check.refresh_from_db()
    page.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.suggested_actions == []
    assert check.related["resolution"]["reason"] == "decision_context_stale"
    assert page.current_version_id == current.id
    assert page.current_version.body == "current"
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


@pytest.mark.django_db
def test_decide_api_auto_resolves_incomplete_frozen_conflict_without_applying_candidate(api_client):
    from apps.opspilot.models import WikiDecisionRule

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()
    context = dict(check.decision_context)
    context["participants"] = [item for item in context["participants"] if item["material_id"] != incoming.id]
    check.decision_context = context
    check.save(update_fields=["decision_context", "updated_at"])

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/decide/",
        {"action": "use_new"},
        format="json",
    )

    assert response.status_code == 409, response.content
    check.refresh_from_db()
    page.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.related["resolution"]["reason"] == "decision_context_incomplete"
    assert page.current_version_id == current.id
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("material_id", ["1", 1.5, True, {"id": 1}])
def test_decide_api_rejects_non_integer_material_id(api_client, material_id):
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        title="page",
        page_type="concept",
    )
    page.current_version = PageVersion.objects.create(
        page=page,
        no=1,
        body="current",
        is_current=True,
        change_type="ai_create",
    )
    page.save(update_fields=["current_version"])
    check = create_candidate(
        page,
        body="candidate",
        reason="conflict",
        check_type="cannot_merge",
    )

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/decide/",
        {"action": "keep_current", "material_id": material_id},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "material_id 必须为正整数"
    check.refresh_from_db()
    assert check.status == "open"


@pytest.mark.django_db
def test_reused_rule_row_does_not_rewrite_historical_or_pending_decision_audit():
    from apps.opspilot.serializers.wiki_serializers import CheckItemSerializer
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check
    from apps.opspilot.services.wiki.decision_service import revoke_rule

    (
        kb,
        page,
        current,
        source,
        source_version,
        incoming,
        incoming_version,
        first,
    ) = _create_frozen_conflict()
    first_rule = decide_check(first, action="keep_current", operator="alice")
    revoke_rule(first_rule, reason="superseded", operator="admin")

    second = create_candidate(
        page,
        body="second candidate",
        reason="same frozen decision",
        check_type="cannot_merge",
        incoming_material=incoming,
        incoming_material_version=incoming_version,
    )

    assert second.id != first.id
    assert second.decision_key == first.decision_key
    pending = CheckItemSerializer(second).data
    assert pending["decision_action"] == ""
    assert pending["decision_operator"] == ""
    assert pending["decision_rule"] is None

    second_rule = decide_check(second, action="use_new", operator="bob")

    assert second_rule.id == first_rule.id
    first.refresh_from_db()
    second.refresh_from_db()
    first_data = CheckItemSerializer(first).data
    second_data = CheckItemSerializer(second).data
    first_resolution = first.related["resolution"]
    assert first_resolution["action"] == "keep_current"
    assert first_resolution["operator"] == "alice"
    assert first_resolution["processed_at"]
    assert first_resolution["decision_type"] == "knowledge_conflict"
    assert first_resolution["rule_id"] == first_rule.id
    assert first_resolution["rule_status"] == "revoked"
    assert first_resolution["revoked_reason"] == "superseded"
    assert first.related["rule_snapshot"]["id"] == first_rule.id
    assert first.related["rule_snapshot"]["action"] == "keep_current"
    assert first.related["rule_snapshot"]["status"] == "revoked"
    assert first.related["rule_snapshot"]["revoked_reason"] == "superseded"
    assert first.related["rule_snapshot"]["result_snapshot"]["action"] == "keep_current"
    assert first_data["decision_action"] == "keep_current"
    assert first_data["decision_operator"] == "alice"
    assert first_data["decision_processed_at"] == first.related["resolution"]["processed_at"]
    assert first_data["decision_rule"]["action"] == "keep_current"
    assert first_data["decision_rule"]["status"] == "revoked"
    assert first_data["decision_rule"]["revoked_reason"] == "superseded"
    assert second.related["rule_snapshot"]["id"] == first_rule.id
    assert second.related["rule_snapshot"]["action"] == "use_new"
    assert second.related["rule_snapshot"]["status"] == "active"
    assert second_data["decision_action"] == "use_new"
    assert second_data["decision_operator"] == "bob"
    assert second_data["decision_rule"]["action"] == "use_new"
    assert second_data["decision_rule"]["status"] == "active"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "version_name",
    [
        pytest.param("current", id="current-body"),
        pytest.param("candidate", id="candidate-body"),
    ],
)
def test_decide_auto_resolves_when_frozen_knowledge_body_changes(version_name):
    from apps.opspilot.models import WikiDecisionRule
    from apps.opspilot.services.wiki.check_service import decide_check

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()
    version = current if version_name == "current" else check.candidate_version
    version.body = f"{version_name} body changed after freeze"
    version.save(update_fields=["body", "updated_at"])

    assert decide_check(check, action="use_new", operator="reviewer") is None

    check.refresh_from_db()
    page.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.suggested_actions == []
    assert check.related["resolution"]["action"] == "automatic_maintenance"
    assert check.related["resolution"]["reason"] == "decision_context_stale"
    assert "正文" in check.related["resolution"]["detail"]
    assert page.current_version_id == current.id
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


@pytest.mark.django_db
def test_decide_auto_resolves_new_page_evidence_added_after_candidate_freeze():
    from apps.opspilot.models import Material, MaterialVersion, PageEvidence, WikiDecisionRule
    from apps.opspilot.services.wiki.check_service import decide_check

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()
    extra = Material.objects.create(
        knowledge_base=kb,
        name="late-source",
        material_type="text",
        content_hash="late-material",
    )
    extra_version = MaterialVersion.objects.create(material=extra, content_hash="late-version")
    PageEvidence.objects.create(page=page, material=extra, material_version=extra_version)

    assert decide_check(check, action="keep_current", operator="reviewer") is None

    check.refresh_from_db()
    page.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.related["resolution"]["reason"] == "decision_context_stale"
    assert page.current_version_id == current.id
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


@pytest.mark.django_db
def test_decide_auto_resolves_incoming_material_current_version_drift():
    from apps.opspilot.models import MaterialVersion, WikiDecisionRule
    from apps.opspilot.services.wiki.check_service import decide_check

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()
    replacement = MaterialVersion.objects.create(
        material=incoming,
        content_hash="version-b-updated",
    )
    incoming.current_version = replacement
    incoming.content_hash = "material-b-updated"
    incoming.save(update_fields=["current_version", "content_hash", "updated_at"])

    assert decide_check(check, action="use_new", operator="reviewer") is None

    check.refresh_from_db()
    page.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.related["resolution"]["reason"] == "decision_context_stale"
    assert page.current_version_id == current.id
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


@pytest.mark.django_db
def test_decide_accepts_new_material_version_with_same_content_hash():
    from apps.opspilot.models import MaterialVersion
    from apps.opspilot.services.wiki.check_service import decide_check

    (
        kb,
        page,
        current,
        source,
        source_version,
        incoming,
        incoming_version,
        check,
    ) = _create_frozen_conflict()
    frozen_decision_key = check.decision_key
    replacement = MaterialVersion.objects.create(
        material=incoming,
        content_hash=incoming_version.content_hash,
    )
    incoming.current_version = replacement
    incoming.save(update_fields=["current_version", "updated_at"])

    rule = decide_check(check, action="keep_current", operator="reviewer")

    check.refresh_from_db()
    assert check.status == "resolved"
    assert rule is not None
    assert rule.decision_key == frozen_decision_key


@pytest.mark.django_db
def test_decide_auto_resolves_schema_change_after_candidate_freeze():
    from apps.opspilot.models import WikiDecisionRule
    from apps.opspilot.services.wiki.check_service import decide_check

    kb, page, current, source, source_version, incoming, incoming_version, check = _create_frozen_conflict()
    kb.schema_md = "# changed schema"
    kb.save(update_fields=["schema_md", "updated_at"])

    assert decide_check(check, action="edit_accept", body="edited", operator="reviewer") is None

    check.refresh_from_db()
    page.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.related["resolution"]["reason"] == "decision_context_stale"
    assert page.current_version_id == current.id
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()
