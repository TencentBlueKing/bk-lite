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
    from apps.opspilot.models import CheckItem, KnowledgePage, Material, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="new", content_hash="h1")
    check = create_candidate(page, body="candidate", reason="conflict", check_type="conflict")
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
    from apps.opspilot.models import CheckItem, KnowledgePage, Material, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="new", content_hash="h1")
    check = create_candidate(page, body="candidate", reason="conflict", check_type="conflict")

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
    check = create_candidate(page, body="candidate", reason="conflict", check_type="conflict")

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
    from apps.opspilot.models import CheckItem, KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    check = create_candidate(page, body="candidate", reason="conflict", check_type="conflict")

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
    check = create_candidate(page, body="candidate", reason="conflict", check_type="conflict")

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
    check = create_candidate(page, body="candidate", reason="conflict", check_type="conflict")

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
def test_decide_check_keep_current_also_writes_rule_for_replay():
    """3.2: keep_current 也写规则(同签名下次自动回放),result_snapshot 含当前页正文指纹。"""
    from apps.opspilot.models import KnowledgePage, Material, PageEvidence, PageVersion, WikiDecisionRule, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="x", content_hash="h-current")
    PageEvidence.objects.create(page=page, material=mat, material_version=None, locator="")
    check = create_candidate(page, body="candidate", reason="conflict", check_type="conflict")

    decide_check(check, action="keep_current", operator="u")

    rules = WikiDecisionRule.objects.all()
    assert rules.count() == 1
    assert rules.first().action == "keep_current"
    # result_snapshot 含当前 page id(回放时校验不覆盖)
    assert rules.first().result_page_id == page.id
    # result_version 指向当前 PageVersion
    assert rules.first().result_version_id is not None
    # participants 来自 page 已有 evidence
    participants = rules.first().match_snapshot["participants"]
    assert any(p["material_id"] == mat.id and p["content_hash"] == "h-current" for p in participants)


# ============================================================================
# phase 3.4: 当前版本竞态保护
# ============================================================================


@pytest.mark.django_db
def test_decide_check_rejects_if_page_current_version_changed():
    """3.4: 候选创建时锁定 current_version,审批时重新校验,过期决策不覆盖。"""
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="v1", is_current=True, change_type="ai_create")
    page.save()
    check = create_candidate(page, body="candidate", reason="conflict", check_type="conflict")
    # 检查点:candidate 创建时记下当时的 current_version_id
    locked_version_id = check.decision_context.get("locked_current_version_id") or page.current_version_id
    # 模拟后台有人更新了 current_version
    new_version = PageVersion.objects.create(page=page, no=2, body="v2", is_current=True, change_type="ai_merge")
    PageVersion.objects.filter(id=locked_version_id).update(is_current=False)
    page.current_version = new_version
    page.save()

    # 旧决定用新 current 校验,过期 → 拒绝
    with pytest.raises(ValueError, match="过期|outdated|stale"):
        decide_check(check, action="use_new", operator="u")

    check.refresh_from_db()
    page.refresh_from_db()
    # 失败:check 保持 open,page.current_version 仍为 v2
    assert check.status == "open"
    assert page.current_version.body == "v2"


# ============================================================================
# phase 3.5: 决策中心 API
# ============================================================================


@pytest.mark.django_db
def test_decide_api_endpoint_accepts_semantic_actions():
    """3.5: POST /check_item/{id}/decide/ 接受语义化动作,按 decision_type 校验。"""
    from unittest.mock import patch

    from apps.opspilot.models import CheckItem, KnowledgePage, Material, PageVersion, WikiDecisionRule, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="current", is_current=True, change_type="ai_create")
    page.save()
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="new", content_hash="h1")
    check = create_candidate(page, body="candidate", reason="conflict", check_type="conflict")
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
        response = view(request, pk=check.id)
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
    check = create_candidate(page, body="candidate", reason="conflict", check_type="conflict")
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
    check = create_candidate(page, body="candidate", reason="conflict", check_type="conflict")
    check.decision_key = "a" * 64
    check.decision_context = {"snap": "v1"}
    check.save()

    data = CheckItemSerializer(check).data
    assert data.get("decision_key") == "a" * 64
    assert data.get("decision_context") == {"snap": "v1"}
