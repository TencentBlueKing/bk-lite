import pytest


def _kb(schema="# schema"):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1], schema_md=schema)


def _material(kb, name="m"):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name=name, material_type="text", text_content="facts")


def _page(kb, title, contribution):
    from apps.opspilot.models import KnowledgePage, PageVersion

    page = KnowledgePage.objects.create(knowledge_base=kb, page_type="concept", title=title, contribution=contribution)
    v = PageVersion.objects.create(page=page, no=1, body="old", change_type="ai_create", is_current=True)
    page.current_version = v
    page.save(update_fields=["current_version"])
    return page


@pytest.mark.django_db
def test_rebuild_archives_ai_keeps_human_and_regenerates():
    from apps.opspilot.models import CheckItem, KnowledgePage
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    mat = _material(kb)
    ai_page = _page(kb, "OldAI", "ai")
    human_page = _page(kb, "Human", "mixed")

    build = rebuild_knowledge_base(kb, generator=lambda m: [{"page_type": "concept", "title": f"New-{m.name}", "tags": [], "body": "fresh"}])

    ai_page.refresh_from_db()
    human_page.refresh_from_db()
    assert ai_page.status == "archived"  # 旧 AI 页归档
    assert human_page.status == "active"  # 人工页保留
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="schema_changed").exists()  # 人工页待核对

    new_pages = KnowledgePage.objects.filter(knowledge_base=kb, update_method="rebuild", status="active")
    assert new_pages.count() == 1 and new_pages.first().title == f"New-{mat.name}"
    assert build.counts == {"new": 1, "archived": 1, "unchanged": 0, "pending_review": 1}


@pytest.mark.django_db
def test_rebuild_with_no_generated_pages():
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    _material(kb)
    _page(kb, "AI", "ai")

    build = rebuild_knowledge_base(kb, generator=lambda m: [])
    assert build.counts["new"] == 0 and build.counts["archived"] == 1
    assert build.status == "success"


@pytest.mark.django_db
class TestRebuildView:
    def test_rebuild_endpoint(self, api_client):
        kb = _kb()
        r = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/rebuild/", {}, format="json")
        assert r.status_code == 200
        assert r.json()["data"]["trigger"] == "rebuild"
