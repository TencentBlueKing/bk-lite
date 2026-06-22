import pytest


def _kb(name="kb"):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name=name, team=[1])


def _page(kb, title, body):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title=title, body=body, created_by="u")


@pytest.mark.django_db
def test_build_context_merges_across_kbs_and_numbers_citations():
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb1, kb2 = _kb("运维库"), _kb("产品库")
    _page(kb1, "重启服务", "执行 systemctl restart 重启服务")
    _page(kb2, "重启流程", "重启前先摘流量再重启")

    out = build_context([kb1.id, kb2.id], "重启服务", top_k=5)

    assert len(out["citations"]) == 2
    assert out["citations"][0]["n"] == 1
    # 不同知识库的命中都被纳入,且上下文带来源标注
    titles = {c["title"] for c in out["citations"]}
    assert {"重启服务", "重启流程"} <= titles
    assert "知识库:" in out["context"]


@pytest.mark.django_db
def test_build_context_empty_when_no_match():
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    _page(kb, "网络配置", "配置静态路由")
    out = build_context([kb.id], "数据库备份")
    assert out["citations"] == [] and out["context"] == ""


@pytest.mark.django_db
class TestContextView:
    def test_context_endpoint(self, api_client):
        kb = _kb()
        _page(kb, "重启服务", "systemctl restart")
        r = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/knowledge_base/context/",
            {"kb_ids": [kb.id], "query": "重启服务"},
            format="json",
        )
        assert r.status_code == 200
        assert r.json()["data"]["citations"][0]["title"] == "重启服务"
