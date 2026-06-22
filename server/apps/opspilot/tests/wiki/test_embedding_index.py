import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _page(kb, title, body):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title=title, body=body, created_by="u")


@pytest.mark.django_db
def test_index_version_stores_embedding():
    from apps.opspilot.services.wiki.embedding_service import index_version

    kb = _kb()
    cv = _page(kb, "A", "body text").current_version
    assert index_version(cv, None, embed_fn=lambda texts: [[0.1, 0.2, 0.3]]) is True
    cv.refresh_from_db()
    assert cv.embedding == [0.1, 0.2, 0.3]


@pytest.mark.django_db
def test_index_version_skips_when_embed_unavailable():
    from apps.opspilot.services.wiki.embedding_service import index_version

    kb = _kb()
    cv = _page(kb, "A", "body").current_version
    assert index_version(cv, None, embed_fn=lambda texts: []) is False


@pytest.mark.django_db
def test_reindex_then_semantic_search_ranks_by_cosine():
    from apps.opspilot.services.wiki.embedding_service import reindex_knowledge_base, semantic_search

    kb = _kb()
    p1 = _page(kb, "重启", "restart service")
    _page(kb, "备份", "backup database")

    def stub(texts):
        out = []
        for t in texts:
            if "restart" in t:
                out.append([1.0, 0.0])
            elif "backup" in t:
                out.append([0.0, 1.0])
            else:
                out.append([0.9, 0.1])  # 中文 query → 语义偏向 restart
        return out

    assert reindex_knowledge_base(kb, embed_fn=stub) == 2
    results = semantic_search(kb, "重启", embed_fn=stub, top_k=5)
    assert results and results[0]["id"] == p1.id


@pytest.mark.django_db
def test_semantic_search_empty_without_index():
    from apps.opspilot.services.wiki.embedding_service import semantic_search

    kb = _kb()
    _page(kb, "A", "body")  # 未建索引
    assert semantic_search(kb, "x", embed_fn=lambda texts: [[1.0]]) == []
