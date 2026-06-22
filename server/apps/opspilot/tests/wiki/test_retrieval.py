import pytest


def _seed(kb):
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.page_service import create_manual_page

    create_manual_page(kb, page_type="concept", title="重启服务", body="使用 systemctl restart nginx 重启服务。", created_by="u")
    create_manual_page(kb, page_type="concept", title="磁盘清理", body="清理 /var/log 释放磁盘空间。", created_by="u")
    Material.objects.create(knowledge_base=kb, name="nginx手册", material_type="text", ai_summary="nginx 服务重启与配置说明。")


@pytest.mark.django_db
def test_search_ranks_relevant_pages():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.retrieval_service import search

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    _seed(kb)
    results = search(kb, "重启 服务")
    assert results, "should find results"
    assert results[0]["title"] in ("重启服务", "资料摘要: nginx手册")
    titles = [r["title"] for r in results]
    assert "重启服务" in titles


@pytest.mark.django_db
def test_answer_without_model_falls_back_with_citations():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.retrieval_service import answer

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    _seed(kb)
    out = answer(kb, "如何重启服务", llm_model_id=None)
    assert out["citations"], "should cite something"
    assert "systemctl" in out["answer"] or "重启" in out["answer"]


@pytest.mark.django_db
def test_answer_empty_kb():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.retrieval_service import answer

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    out = answer(kb, "anything", llm_model_id=None)
    assert out["citations"] == []


@pytest.mark.django_db
class TestRetrievalViews:
    def test_search_and_qa_endpoints(self, api_client):
        from apps.opspilot.models import WikiKnowledgeBase

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        _seed(kb)
        s = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/search/", {"query": "重启 服务"}, format="json")
        assert s.status_code == 200, s.content
        assert any("重启" in r["title"] for r in s.json()["data"])

        q = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/qa/", {"query": "如何重启服务"}, format="json")
        assert q.status_code == 200, q.content
        assert q.json()["data"]["citations"]
