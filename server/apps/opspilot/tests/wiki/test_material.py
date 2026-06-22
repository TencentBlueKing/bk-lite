import pytest


@pytest.mark.django_db
def test_ingest_text_material_sets_summary_and_done():
    from apps.opspilot.models import Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki.material_service import ingest_material

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    m = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="运维知识:重启服务用 systemctl restart。")
    ingest_material(m, llm_model_id=None)
    m.refresh_from_db()
    assert m.status == "done"
    assert m.content_hash
    assert "systemctl" in m.ai_summary  # 无模型时回退为截断正文


@pytest.mark.django_db
def test_ingest_unsupported_type_marks_failed():
    from apps.opspilot.models import Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki.material_service import ingest_material

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    m = Material.objects.create(knowledge_base=kb, name="f", material_type="file")
    ingest_material(m, llm_model_id=None)
    m.refresh_from_db()
    assert m.status == "failed"


@pytest.mark.django_db
class TestMaterialViews:
    BASE = "/api/v1/opspilot/wiki_mgmt/material/"

    def _data(self, resp):
        body = resp.json()
        return body.get("data", body)

    def test_create_text_material_auto_ingests(self, api_client):
        from apps.opspilot.models import WikiKnowledgeBase

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        resp = api_client.post(
            self.BASE,
            {"knowledge_base": kb.id, "name": "m1", "material_type": "text", "text_content": "hello world content"},
            format="json",
        )
        assert resp.status_code in (200, 201), resp.content
        data = self._data(resp)
        assert data["status"] == "done"
        assert data["ai_summary"]

        lst = api_client.get(self.BASE + f"?knowledge_base={kb.id}")
        assert lst.status_code == 200
        assert any(x["name"] == "m1" for x in self._data(lst))
