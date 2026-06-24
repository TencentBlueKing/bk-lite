import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _material(kb):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="new facts")


def _page(kb, title, contribution, body="old"):
    from apps.opspilot.models import KnowledgePage, PageVersion

    page = KnowledgePage.objects.create(knowledge_base=kb, page_type="concept", title=title, contribution=contribution)
    v = PageVersion.objects.create(page=page, no=1, body=body, change_type="ai_create", is_current=True)
    page.current_version = v
    page.save(update_fields=["current_version"])
    return page


@pytest.mark.django_db
def test_ai_page_also_goes_to_review():
    """全部人工审批:纯 AI 页面的资料更新也不再自动生效,改为生成候选 + 检查项。"""
    from apps.opspilot.models import CheckItem
    from apps.opspilot.services.wiki.update_service import apply_material_update

    kb = _kb()
    page = _page(kb, "A", "ai", body="ai-old")
    action, check = apply_material_update(page, "new body", operator="sys")

    assert action == "pending_review"
    page.refresh_from_db()
    assert page.current_version.body == "ai-old"  # 不自动覆盖,当前有效版本不变
    assert check.status == "open"
    assert check.candidate_version.body == "new body"
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="material_update").count() == 1


@pytest.mark.django_db
def test_human_page_goes_to_review_without_polluting_current():
    from apps.opspilot.models import CheckItem
    from apps.opspilot.services.wiki.update_service import apply_material_update

    kb = _kb()
    page = _page(kb, "B", "human", body="human-written")
    action, check = apply_material_update(page, "ai-rewrite", operator="sys")

    assert action == "pending_review"
    page.refresh_from_db()
    assert page.current_version.body == "human-written"  # 当前有效版本未被污染
    assert check.status == "open"
    assert check.candidate_version.body == "ai-rewrite"
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="material_update").count() == 1


@pytest.mark.django_db
def test_propose_update_all_go_to_review():
    """全部人工审批:受影响页面(含纯 AI)统一进审核,当前有效版本都不被覆盖。"""
    from apps.opspilot.models import PageEvidence
    from apps.opspilot.services.wiki.update_service import propose_update

    kb = _kb()
    mat = _material(kb)
    ai_page = _page(kb, "AI", "ai", body="ai-kept")
    human_page = _page(kb, "H", "mixed", body="kept")
    PageEvidence.objects.create(page=ai_page, material=mat)
    PageEvidence.objects.create(page=human_page, material=mat)

    build = propose_update(mat, generator=lambda p, m: f"NEW {p.title}")

    assert build.counts == {"new": 0, "updated": 0, "unchanged": 0, "pending_review": 2}
    ai_page.refresh_from_db()
    human_page.refresh_from_db()
    assert ai_page.current_version.body == "ai-kept"  # 一律进审核,当前版本不变
    assert human_page.current_version.body == "kept"


@pytest.mark.django_db
class TestUpdateView:
    def test_propose_update_endpoint_no_affected(self, api_client):
        kb = _kb()
        mat = _material(kb)
        r = api_client.post(f"/api/v1/opspilot/wiki_mgmt/material/{mat.id}/propose_update/", {}, format="json")
        assert r.status_code == 200
        assert r.json()["data"]["counts"]["updated"] == 0
