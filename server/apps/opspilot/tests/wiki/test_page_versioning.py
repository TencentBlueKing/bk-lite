import pytest


@pytest.mark.django_db
def test_manual_create_edit_restore_versions():
    from apps.opspilot.models import PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.page_service import create_manual_page, edit_page, restore_version

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = create_manual_page(kb, page_type="concept", title="T", body="v1", created_by="u1")
    assert page.contribution == "human"
    assert page.current_version.no == 1 and page.current_version.body == "v1"

    edit_page(page, body="v2", updated_by="u1")
    page.refresh_from_db()
    assert page.current_version.no == 2 and page.current_version.body == "v2"
    assert PageVersion.objects.filter(page=page, is_current=True).count() == 1

    # restore to version 1
    v1 = PageVersion.objects.get(page=page, no=1)
    restore_version(page, v1.id, operator="u1")
    page.refresh_from_db()
    assert page.current_version.body == "v1"
    assert page.current_version.change_type == "restore"
    assert PageVersion.objects.filter(page=page).count() == 3  # v1, v2, restore


@pytest.mark.django_db
def test_ai_page_edited_becomes_mixed():
    from apps.opspilot.models import KnowledgePage, WikiKnowledgeBase
    from apps.opspilot.services.wiki.page_service import _new_current_version, edit_page

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, page_type="concept", title="AI", contribution="ai")
    _new_current_version(page, body="ai-body", change_type="ai_create", created_by="")
    edit_page(page, body="human-edit", updated_by="u1")
    page.refresh_from_db()
    assert page.contribution == "mixed"


@pytest.mark.django_db
class TestPageViews:
    BASE = "/api/v1/opspilot/wiki_mgmt/page/"

    def test_create_edit_versions_restore(self, api_client):
        from apps.opspilot.models import WikiKnowledgeBase

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        resp = api_client.post(self.BASE, {"knowledge_base": kb.id, "page_type": "concept", "title": "P", "body": "b1"}, format="json")
        assert resp.status_code in (200, 201), resp.content
        pid = resp.json()["data"]["id"]

        up = api_client.put(f"{self.BASE}{pid}/", {"body": "b2"}, format="json")
        assert up.status_code == 200
        assert up.json()["data"]["body"] == "b2"

        vers = api_client.get(f"{self.BASE}{pid}/versions/")
        assert vers.status_code == 200
        data = vers.json()["data"]
        assert len(data) == 2
        v1_id = [v["id"] for v in data if v["no"] == 1][0]

        rs = api_client.post(f"{self.BASE}{pid}/restore/", {"version_id": v1_id}, format="json")
        assert rs.status_code == 200
        assert rs.json()["data"]["body"] == "b1"
