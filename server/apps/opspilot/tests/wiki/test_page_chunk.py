import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _page(kb, title, body):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title=title, body=body, created_by="u")


def _stub(texts):
    out = []
    for t in texts:
        if "restart" in t:
            out.append([1.0, 0.0])
        elif "backup" in t:
            out.append([0.0, 1.0])
        else:
            out.append([0.9, 0.1])  # 中文 query → 偏向 restart
    return out


def test_chunk_markdown_splits_by_heading():
    from apps.opspilot.services.wiki.embedding_service import chunk_markdown

    chunks = chunk_markdown("# 标题A\n内容1\n## 标题B\n内容2")
    assert len(chunks) == 2
    assert chunks[0]["heading_path"] == "标题A" and "内容1" in chunks[0]["text"]
    assert chunks[1]["heading_path"] == "标题B" and "内容2" in chunks[1]["text"]
    assert [c["idx"] for c in chunks] == [0, 1]


def test_chunk_markdown_secondary_split_for_long_section():
    from apps.opspilot.services.wiki.embedding_service import chunk_markdown

    chunks = chunk_markdown("x" * 2000, max_chars=800)
    assert len(chunks) == 3  # 800 + 800 + 400


@pytest.mark.django_db
def test_reindex_page_chunks_and_search():
    from apps.opspilot.models import PageChunk
    from apps.opspilot.services.wiki.embedding_service import chunk_semantic_search, reindex_page_chunks

    kb = _kb()
    page = _page(kb, "P", "# 重启\nsystemctl restart\n# 备份\nbackup db")

    n = reindex_page_chunks(page, kb.embed_provider, embed_fn=_stub)
    assert n == 2
    assert PageChunk.objects.filter(page=page).count() == 2

    results = chunk_semantic_search(kb, "重启", embed_fn=_stub, top_k=5)
    assert results and "restart" in results[0]["snippet"]
    assert results[0]["heading_path"] == "重启"


@pytest.mark.django_db
def test_reindex_chunks_is_idempotent():
    from apps.opspilot.models import PageChunk
    from apps.opspilot.services.wiki.embedding_service import reindex_page_chunks

    kb = _kb()
    page = _page(kb, "P", "# A\nalpha\n# B\nbeta")
    reindex_page_chunks(page, kb.embed_provider, embed_fn=_stub)
    reindex_page_chunks(page, kb.embed_provider, embed_fn=_stub)
    assert PageChunk.objects.filter(page=page).count() == 2  # 重建不累积
