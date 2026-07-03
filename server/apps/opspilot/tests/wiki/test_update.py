from types import SimpleNamespace

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


def test_default_generator_uses_parsed_markdown_and_llm(monkeypatch):
    from apps.opspilot.services.wiki import update_service

    prompts = []
    page = SimpleNamespace(id=1, title="重启服务", current_version_id=1, current_version=SimpleNamespace(body="old body"))
    material = SimpleNamespace(ai_summary="summary", text_content="text")
    monkeypatch.setattr(update_service, "load_parsed_markdown", lambda material: "parsed markdown")
    monkeypatch.setattr(
        update_service.LLMModel.objects,
        "get",
        lambda id: SimpleNamespace(openai_api_base="http://llm", openai_api_key="key", model_name="model"),
    )

    def fake_invoke(request, messages):
        prompts.append(messages[0]["content"])
        return "new body"

    monkeypatch.setattr(update_service.LLMClientFactory, "invoke_isolated", fake_invoke)

    assert update_service._default_generator(page, material, llm_model_id=1) == "new body"
    assert "parsed markdown" in prompts[0]
    assert "old body" in prompts[0]


def test_default_generator_uses_full_current_and_material_text(monkeypatch):
    from apps.opspilot.services.wiki import update_service

    prompts = []
    current_tail = "CURRENT_TAIL_SHOULD_NOT_BE_DROPPED"
    material_tail = "MATERIAL_TAIL_SHOULD_NOT_BE_DROPPED"
    page = SimpleNamespace(
        id=1,
        title="长文档页面",
        current_version_id=1,
        current_version=SimpleNamespace(body=("current\n" * 900) + current_tail),
    )
    material = SimpleNamespace(ai_summary="", text_content="fallback")
    monkeypatch.setattr(update_service, "load_parsed_markdown", lambda material: ("material\n" * 1200) + material_tail)
    monkeypatch.setattr(
        update_service.LLMModel.objects,
        "get",
        lambda id: SimpleNamespace(openai_api_base="http://llm", openai_api_key="key", model_name="model"),
    )

    def fake_invoke(request, messages):
        prompts.append(messages[0]["content"])
        return "new body"

    monkeypatch.setattr(update_service.LLMClientFactory, "invoke_isolated", fake_invoke)

    assert update_service._default_generator(page, material, llm_model_id=1) == "new body"
    assert current_tail in prompts[0]
    assert material_tail in prompts[0]


def test_default_generator_returns_empty_without_model_or_when_llm_fails(monkeypatch):
    from apps.opspilot.services.wiki import update_service

    page = SimpleNamespace(id=1, title="T", current_version_id=None, current_version=None)
    material = SimpleNamespace(ai_summary="summary", text_content="text")

    assert update_service._default_generator(page, material, llm_model_id=None) == ""

    monkeypatch.setattr(update_service, "load_parsed_markdown", lambda material: "")
    monkeypatch.setattr(update_service.LLMModel.objects, "get", lambda id: (_ for _ in ()).throw(RuntimeError("llm down")))
    assert update_service._default_generator(page, material, llm_model_id=1) == ""


@pytest.mark.django_db
def test_propose_update_skips_empty_generated_body():
    from apps.opspilot.models import PageEvidence
    from apps.opspilot.services.wiki.update_service import propose_update

    kb = _kb()
    material = _material(kb)
    page = _page(kb, "Skip", "ai", body="kept")
    PageEvidence.objects.create(page=page, material=material)

    build = propose_update(material, generator=lambda p, m: "  ")

    assert build.status == "success"
    assert build.counts == {"new": 0, "updated": 0, "unchanged": 0, "pending_review": 0}
    assert build.affected_pages == []


@pytest.mark.django_db
def test_propose_update_marks_build_failed_when_generator_raises():
    from apps.opspilot.models import BuildRecord, PageEvidence
    from apps.opspilot.services.wiki.update_service import propose_update

    kb = _kb()
    material = _material(kb)
    page = _page(kb, "Boom", "ai", body="kept")
    PageEvidence.objects.create(page=page, material=material)

    def raise_error(page, material):
        raise RuntimeError("generator exploded")

    with pytest.raises(RuntimeError):
        propose_update(material, generator=raise_error)

    record = BuildRecord.objects.filter(knowledge_base=kb, trigger="material_update").latest("id")
    assert record.status == "failed"
    assert record.stage == "failed"
    assert record.errors == ["generator exploded"]


@pytest.mark.django_db
class TestUpdateView:
    def test_update_impact_endpoint_reports_pending_review_without_mutation(self, api_client):
        from apps.opspilot.models import CheckItem, MaterialVersion, PageEvidence

        kb = _kb()
        mat = _material(kb)
        first = MaterialVersion.objects.create(material=mat, content_hash="old", content_locator="wiki/parsed/1/1/old.md")
        second = MaterialVersion.objects.create(material=mat, content_hash="new", content_locator="wiki/parsed/1/1/new.md")
        mat.current_version = second
        mat.content_hash = "new"
        mat.status = "updated"
        mat.save(update_fields=["current_version", "content_hash", "status", "updated_at"])
        ai_page = _page(kb, "AI", "ai", body="ai-kept")
        human_page = _page(kb, "Human", "mixed", body="human-kept")
        untouched = _page(kb, "Untouched", "ai", body="untouched")
        PageEvidence.objects.create(page=human_page, material=mat)
        PageEvidence.objects.create(page=ai_page, material=mat)

        r = api_client.get(f"/api/v1/opspilot/wiki_mgmt/material/{mat.id}/update_impact/")

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["material_id"] == mat.id
        assert data["content_changed"] is True
        assert data["affected_count"] == 2
        assert data["pending_review_count"] == 2
        assert [p["id"] for p in data["pending_review_pages"]] == [ai_page.id, human_page.id]
        assert data["latest_version"]["id"] == second.id
        assert data["previous_version"]["id"] == first.id
        assert CheckItem.objects.filter(knowledge_base=kb, check_type="material_update").count() == 0
        ai_page.refresh_from_db()
        human_page.refresh_from_db()
        untouched.refresh_from_db()
        assert ai_page.current_version.body == "ai-kept"
        assert human_page.current_version.body == "human-kept"
        assert untouched.current_version.body == "untouched"

    def test_propose_update_endpoint_no_affected(self, api_client):
        kb = _kb()
        mat = _material(kb)
        r = api_client.post(f"/api/v1/opspilot/wiki_mgmt/material/{mat.id}/propose_update/", {}, format="json")
        assert r.status_code == 200
        assert r.json()["data"]["counts"]["updated"] == 0
