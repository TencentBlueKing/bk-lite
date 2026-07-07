import pytest


def _kb(name="kb"):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name=name, team=[1])


def _page(kb, title, body):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title=title, body=body, created_by="u")


def _relate(from_page, to_page, relation_type="reference", weight=1.0):
    from apps.opspilot.models import PageRelation

    return PageRelation.objects.create(
        from_page=from_page,
        to_page=to_page,
        relation_type=relation_type,
        weight=weight,
    )


def _chunk_embed_stub(texts):
    vectors = []
    for text in texts:
        if "restart" in text:
            vectors.append([1.0, 0.0])
        elif "backup" in text:
            vectors.append([0.0, 1.0])
        else:
            vectors.append([0.9, 0.1])
    return vectors


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
def test_build_context_expands_one_hop_graph_neighbors():
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    seed = _page(kb, "蓝鲸平台", "蓝鲸平台提供统一运维入口")
    related = _page(kb, "作业平台", "作业平台负责批量脚本执行")
    _relate(seed, related, relation_type="reference", weight=2.0)

    out = build_context([kb.id], "统一运维入口", top_k=3, graph_hops=1)

    titles = [item["title"] for item in out["citations"]]
    assert titles == ["蓝鲸平台", "作业平台"]
    assert out["citations"][1]["explanation"]["matched_by"] == ["graph"]
    assert out["citations"][1]["explanation"]["graph_source_title"] == "蓝鲸平台"


@pytest.mark.django_db
def test_build_context_respects_token_budget():
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    _page(kb, "重启主流程", "重启服务 " + "先摘流量再重启 " * 20)
    _page(kb, "重启补充说明", "重启服务 " + "观察指标确认恢复 " * 20)

    out = build_context([kb.id], "重启服务", top_k=5, token_budget=32)

    assert len(out["citations"]) == 1
    assert out["budget"]["token_budget"] == 32
    assert out["budget"]["used_tokens"] <= 32
    assert out["budget"]["truncated"] is True


@pytest.mark.django_db
def test_build_context_can_use_hybrid_search_explanations():
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    _page(kb, "重启服务", "使用 systemctl restart 重启")
    semantic_page = _page(kb, "重启流程", "重启前先摘流量再重启")

    def stub_embed(texts):
        vectors = []
        for text in texts:
            if "流量" in text:
                vectors.append([1.0, 0.0])
            elif "systemctl" in text:
                vectors.append([0.0, 1.0])
            else:
                vectors.append([0.9, 0.1])
        return vectors

    out = build_context([kb.id], "重启", top_k=2, retrieval_mode="hybrid", embed_fn=stub_embed, graph_hops=0)

    assert out["citations"][0]["id"] == semantic_page.id
    explanation = out["citations"][0]["explanation"]
    assert explanation["matched_by"] == ["keyword", "vector"]
    assert explanation["fusion"] == "rrf"
    assert explanation["semantic_rank"] == 1


@pytest.mark.django_db
def test_build_context_can_use_chunk_search_with_chunk_citations():
    from apps.opspilot.services.wiki.embedding_service import reindex_page_chunks
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    page = _page(kb, "服务操作手册", "# 重启\nsystemctl restart\n# 备份\nbackup db")
    reindex_page_chunks(page, kb.embed_provider, embed_fn=_chunk_embed_stub)

    out = build_context(
        [kb.id],
        "重启",
        top_k=2,
        retrieval_mode="chunk",
        embed_fn=_chunk_embed_stub,
        graph_hops=0,
    )

    assert out["retrieval_mode"] == "chunk"
    assert out["citations"][0]["kind"] == "page_chunk"
    assert out["citations"][0]["id"] == f"{page.id}:0"
    assert out["citations"][0]["title"] == "服务操作手册 / 重启"
    explanation = out["citations"][0]["explanation"]
    assert explanation["matched_by"] == ["chunk_vector"]
    assert explanation["chunk_index"] == 0
    assert "systemctl restart" in out["context"]


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

    def test_context_endpoint_passes_budget_and_graph_options(self, api_client):
        kb = _kb()
        seed = _page(kb, "蓝鲸平台", "蓝鲸平台提供统一运维入口")
        related = _page(kb, "作业平台", "作业平台负责批量脚本执行")
        _relate(seed, related)

        r = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/knowledge_base/context/",
            {"kb_ids": [kb.id], "query": "统一运维入口", "top_k": 3, "graph_hops": 1, "token_budget": 128},
            format="json",
        )

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["budget"]["token_budget"] == 128
        assert [item["title"] for item in data["citations"]] == ["蓝鲸平台", "作业平台"]

    def test_context_endpoint_accepts_retrieval_mode(self, api_client):
        kb = _kb()
        _page(kb, "重启服务", "systemctl restart 重启")

        r = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/knowledge_base/context/",
            {"kb_ids": [kb.id], "query": "重启", "retrieval_mode": "hybrid", "graph_hops": 0},
            format="json",
        )

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["retrieval_mode"] == "hybrid"
        assert data["citations"][0]["explanation"]["matched_by"] == ["keyword"]

    def test_context_endpoint_accepts_chunk_retrieval_mode(self, api_client, monkeypatch):
        from apps.opspilot.services.wiki import wiki_context_service

        kb = _kb()
        _page(kb, "服务操作手册", "# 重启\nsystemctl restart")

        monkeypatch.setattr(
            wiki_context_service,
            "wiki_chunk_search",
            lambda kb_arg, query, top_k, embed_fn=None: [
                {
                    "page_id": 99,
                    "title": "服务操作手册",
                    "heading_path": "重启",
                    "snippet": "systemctl restart",
                    "score": 0.9,
                    "explanation": {"matched_by": ["chunk_vector"], "chunk_index": 0, "vector_score": 0.9},
                }
            ],
        )

        r = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/knowledge_base/context/",
            {"kb_ids": [kb.id], "query": "重启", "retrieval_mode": "chunk", "graph_hops": 0},
            format="json",
        )

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["retrieval_mode"] == "chunk"
        assert data["citations"][0]["kind"] == "page_chunk"
        assert data["citations"][0]["title"] == "服务操作手册 / 重启"
