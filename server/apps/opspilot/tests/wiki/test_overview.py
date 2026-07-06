import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _page(kb, title, contribution="ai"):
    from apps.opspilot.models import KnowledgePage, PageVersion

    page = KnowledgePage.objects.create(knowledge_base=kb, page_type="concept", title=title, contribution=contribution)
    v = PageVersion.objects.create(page=page, no=1, body="b", change_type="ai_create", is_current=True)
    page.current_version = v
    page.save(update_fields=["current_version"])
    return page


@pytest.mark.django_db
def test_overview_aggregates_counts_and_contribution():
    from apps.opspilot.models import CheckItem, Material, PageRelation
    from apps.opspilot.services.wiki.overview_service import get_overview

    kb = _kb()
    a = _page(kb, "A", "ai")
    b = _page(kb, "B", "human")
    Material.objects.create(knowledge_base=kb, name="m", material_type="text", status="done")
    PageRelation.objects.create(from_page=a, to_page=b, relation_type="reference", weight=1.0)
    CheckItem.objects.create(knowledge_base=kb, check_type="orphan", status="open", related={"pages": [a.id]})

    ov = get_overview(kb)
    assert ov["counts"]["pages"] == 2
    assert ov["counts"]["materials"] == 1
    assert ov["counts"]["relations"] == 1
    assert ov["counts"]["open_checks"] == 1
    assert ov["contribution"] == {"ai": 1, "human": 1}
    assert ov["material_status"] == {"done": 1}
    assert ov["checks_by_type"] == {"orphan": 1}
    assert ov["health"]["clusters"] == 1  # A-B 同一社区


@pytest.mark.django_db
class TestOverviewView:
    def test_overview_endpoint(self, api_client):
        kb = _kb()
        _page(kb, "A")
        r = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/overview/")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["knowledge_base"]["id"] == kb.id
        assert data["counts"]["pages"] == 1
