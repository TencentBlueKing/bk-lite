import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _page(kb, title, body):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title=title, body=body, created_by="u")


def test_cosine():
    from apps.opspilot.services.wiki.embedding_service import cosine

    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([0, 0], [1, 1]) == 0.0
    assert cosine([1, 2], []) == 0.0


def test_rrf_fuse_rewards_consensus():
    from apps.opspilot.services.wiki.embedding_service import rrf_fuse

    # B 在两路都靠前 → 融合第一
    fused = rrf_fuse([["A", "B", "C"], ["B", "C", "A"]])
    assert fused[0] == "B"
    # top_k 截断
    assert len(rrf_fuse([["A", "B", "C"]], top_k=2)) == 2


@pytest.mark.django_db
def test_hybrid_search_semantic_rerank():
    from apps.opspilot.services.wiki.retrieval_service import hybrid_search

    kb = _kb()
    _page(kb, "重启服务", "使用 systemctl restart 重启")
    p2 = _page(kb, "重启流程", "重启前先摘流量再重启")

    def stub(texts):
        out = []
        for t in texts:
            if "流量" in t:
                out.append([1.0, 0.0])
            elif "systemctl" in t:
                out.append([0.0, 1.0])
            else:
                out.append([0.9, 0.1])  # query → 语义偏向"流量"页
        return out

    results = hybrid_search(kb, "重启", embed_fn=stub)
    assert results and results[0]["id"] == p2.id  # 语义重排把 p2 顶到前面
    explanation = results[0]["explanation"]
    assert explanation["matched_by"] == ["keyword", "vector"]
    assert explanation["semantic_rank"] == 1
    assert explanation["vector_score"] > 0


@pytest.mark.django_db
def test_hybrid_search_falls_back_to_keyword_without_embeddings():
    from apps.opspilot.services.wiki.retrieval_service import hybrid_search

    kb = _kb()
    _page(kb, "重启服务", "systemctl restart 重启")

    results = hybrid_search(kb, "重启", embed_fn=lambda texts: [])  # 嵌入不可用
    assert len(results) == 1 and results[0]["kind"] == "page"
    assert results[0]["explanation"]["matched_by"] == ["keyword"]


@pytest.mark.django_db
def test_hybrid_search_empty_without_keyword_candidates():
    from apps.opspilot.services.wiki.retrieval_service import hybrid_search

    kb = _kb()

    assert hybrid_search(kb, "不存在的内容", embed_fn=lambda texts: pytest.fail("no candidates should skip embedding")) == []
