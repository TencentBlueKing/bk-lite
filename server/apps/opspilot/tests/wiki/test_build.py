from unittest.mock import patch

import pytest

_FAKE_PAGES = [
    {"page_type": "concept", "title": "重启服务", "tags": ["ops"], "body": "用 systemctl restart 重启。"},
    {"page_type": "qa", "title": "如何重启", "tags": [], "body": "问:如何重启?答:systemctl restart。"},
]


@pytest.mark.django_db
def test_build_from_material_creates_pages_versions_evidence():
    from apps.opspilot.models import KnowledgePage, Material, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="t", ai_summary="重启服务摘要")

    with patch.object(build_service, "_llm_generate_pages", return_value=_FAKE_PAGES):
        record = build_service.build_from_material(material, llm_model_id=1)

    assert record.status == "success"
    assert record.counts["new"] == 2
    assert KnowledgePage.objects.filter(knowledge_base=kb).count() == 2
    page = KnowledgePage.objects.get(title="重启服务")
    assert page.current_version is not None
    assert PageVersion.objects.filter(page=page, is_current=True).count() == 1
    assert PageEvidence.objects.filter(page=page, material=material).count() == 1


@pytest.mark.django_db
def test_build_no_model_yields_zero_pages():
    from apps.opspilot.models import KnowledgePage, Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", ai_summary="x")
    record = build_service.build_from_material(material, llm_model_id=None)
    assert record.status == "success"
    assert record.counts["new"] == 0
    assert KnowledgePage.objects.filter(knowledge_base=kb).count() == 0


@pytest.mark.django_db
class TestBuildViews:
    def test_material_build_action_and_listings(self, api_client):
        from apps.opspilot.models import Material, WikiKnowledgeBase
        from apps.opspilot.services.wiki import build_service

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
        material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", ai_summary="重启服务摘要")

        with patch.object(build_service, "_llm_generate_pages", return_value=_FAKE_PAGES):
            resp = api_client.post(f"/api/v1/opspilot/wiki_mgmt/material/{material.id}/build/", {}, format="json")
        assert resp.status_code == 200, resp.content
        assert resp.json()["data"]["status"] == "success"

        pages = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/?knowledge_base={kb.id}")
        assert pages.status_code == 200
        titles = [p["title"] for p in pages.json()["data"]]
        assert "重启服务" in titles

        records = api_client.get(f"/api/v1/opspilot/wiki_mgmt/build_record/?knowledge_base={kb.id}")
        assert records.status_code == 200
        assert len(records.json()["data"]) == 1
