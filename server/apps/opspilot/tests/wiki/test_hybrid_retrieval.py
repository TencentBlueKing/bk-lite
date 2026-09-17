import pytest


def _kb():
    from apps.opspilot.tests.wiki.factories import WikiFactory

    return WikiFactory().bootstrapped_knowledge_base()


def _page(kb, title, body):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title=title, body=body, created_by="u")


def _store_embedding(page, vector):
    version = page.current_version
    version.embedding = list(vector)
    version.save(update_fields=["embedding"])
    return page


def test_cosine():
    from apps.opspilot.services.wiki.embedding_service import cosine

    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([0, 0], [1, 1]) == 0.0
    assert cosine([1, 2], []) == 0.0


def test_rrf_fuse_rewards_consensus():
    from apps.opspilot.services.wiki.embedding_service import rrf_fuse

    fused = rrf_fuse([["A", "B", "C"], ["B", "C", "A"]])
    assert fused[0] == "B"
    assert len(rrf_fuse([["A", "B", "C"]], top_k=2)) == 2


@pytest.mark.django_db
def test_hybrid_search_semantic_rerank():
    from apps.opspilot.services.wiki.retrieval_service import hybrid_search

    kb = _kb()
    _store_embedding(_page(kb, "重启服务", "使用 systemctl restart 重启"), [0.0, 1.0])
    p2 = _store_embedding(_page(kb, "重启流程", "重启前先摘流量再重启"), [1.0, 0.0])

    results = hybrid_search(kb, "重启", embed_fn=lambda texts: [[0.9, 0.1] for _ in texts])
    assert results and results[0]["id"] == p2.id
    explanation = results[0]["explanation"]
    assert "vector" in explanation["matched_by"]
    assert "generation_index" in explanation["matched_by"] or "keyword" in explanation["matched_by"]
    assert explanation["semantic_rank"] == 1
    assert explanation["vector_score"] > 0


@pytest.mark.django_db
def test_hybrid_search_falls_back_to_keyword_without_embeddings():
    from apps.opspilot.services.wiki.retrieval_service import hybrid_search

    kb = _kb()
    _page(kb, "重启服务", "systemctl restart 重启")

    results = hybrid_search(kb, "重启", embed_fn=lambda texts: pytest.fail("no stored vectors should skip embedding"))
    assert len(results) == 1 and results[0]["kind"] == "page"
    assert "vector" not in results[0]["explanation"]["matched_by"]


@pytest.mark.django_db
def test_hybrid_search_empty_without_keyword_candidates():
    from apps.opspilot.services.wiki.retrieval_service import hybrid_search

    kb = _kb()

    assert hybrid_search(kb, "不存在的内容", embed_fn=lambda texts: pytest.fail("no candidates should skip embedding")) == []


@pytest.mark.django_db
def test_hybrid_search_recalls_page_missing_from_keyword_pool():
    from apps.opspilot.services.wiki.retrieval_service import hybrid_search, search

    kb = _kb()
    _page(kb, "打印机驱动安装", "安装打印机驱动需要管理员权限。")
    expected = _store_embedding(
        _page(kb, "会议室预定失败或按钮灰色处理", "日期超出可选范围时预定提交控件会变成不可用。"),
        [1.0, 0.0],
    )

    query = "想约个房间开会那个键点不动"
    assert all(item["id"] != expected.id for item in search(kb, query, top_k=20))

    results = hybrid_search(kb, query, embed_fn=lambda texts: [[1.0, 0.0] for _ in texts])
    assert results
    assert results[0]["id"] == expected.id
    assert results[0]["explanation"]["matched_by"] == ["vector"]
    assert results[0]["explanation"]["semantic_rank"] == 1


@pytest.mark.django_db
def test_hybrid_search_vector_respects_directory_scope():
    from apps.opspilot.services.wiki.retrieval_service import hybrid_search

    kb = _kb()
    page = _store_embedding(_page(kb, "会议室预定失败或按钮灰色处理", "确定按钮变灰"), [1.0, 0.0])
    results = hybrid_search(
        kb,
        "想约个房间开会确定键点不动",
        embed_fn=lambda texts: [[1.0, 0.0] for _ in texts],
        directory_id=page.directory_id,
    )
    assert results and results[0]["id"] == page.id
