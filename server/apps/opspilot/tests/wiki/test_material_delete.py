import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _material(kb, name="m"):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name=name, material_type="text", text_content="x")


def _page(kb, title="A"):
    from apps.opspilot.models import KnowledgePage, PageVersion

    page = KnowledgePage.objects.create(knowledge_base=kb, page_type="concept", title=title, contribution="ai")
    v = PageVersion.objects.create(page=page, no=1, body="b", change_type="ai_create", is_current=True)
    page.current_version = v
    page.save(update_fields=["current_version"])
    return page


@pytest.mark.django_db
def test_deleting_only_source_flags_page_for_review():
    from apps.opspilot.models import CheckItem, Material, PageEvidence
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    kb = _kb()
    mat = _material(kb)
    page = _page(kb)
    PageEvidence.objects.create(page=page, material=mat)

    build = handle_material_deletion(mat, operator="sys")

    assert not Material.objects.filter(id=mat.id).exists()
    assert build.counts["pending_review"] == 1
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="source_invalid", related__pages__contains=[page.id]).exists()


@pytest.mark.django_db
def test_page_with_remaining_source_not_flagged():
    from apps.opspilot.models import CheckItem, PageEvidence
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    kb = _kb()
    m1, m2 = _material(kb, "m1"), _material(kb, "m2")
    page = _page(kb)
    PageEvidence.objects.create(page=page, material=m1)
    PageEvidence.objects.create(page=page, material=m2)

    build = handle_material_deletion(m1, operator="sys")

    assert build.counts["pending_review"] == 0
    assert not CheckItem.objects.filter(knowledge_base=kb, check_type="source_invalid").exists()


@pytest.mark.django_db
class TestDeleteView:
    def test_destroy_endpoint_reports_impact(self, api_client):
        from apps.opspilot.models import Material, PageEvidence

        kb = _kb()
        mat = _material(kb)
        page = _page(kb)
        PageEvidence.objects.create(page=page, material=mat)

        r = api_client.delete(f"/api/v1/opspilot/wiki_mgmt/material/{mat.id}/")
        assert r.status_code == 200
        assert r.json()["data"]["pending_review"] == 1
        assert not Material.objects.filter(id=mat.id).exists()
