from types import SimpleNamespace

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
def test_index_version_embeds_full_body_without_prefix_truncation():
    from apps.opspilot.services.wiki.embedding_service import index_version

    kb = _kb()
    tail = "TAIL_FOR_EMBEDDING"
    cv = _page(kb, "Long", ("body\n" * 1800) + tail).current_version
    seen = {}

    def embed(texts):
        seen["text"] = texts[0]
        return [[0.1, 0.2]]

    assert index_version(cv, None, embed_fn=embed) is True
    assert tail in seen["text"]


@pytest.mark.django_db
def test_index_version_skips_when_embed_unavailable():
    from apps.opspilot.services.wiki.embedding_service import index_version

    kb = _kb()
    cv = _page(kb, "A", "body").current_version
    assert index_version(cv, None, embed_fn=lambda texts: []) is False


@pytest.mark.django_db
def test_index_version_skips_empty_body_and_clear_empty_page_list():
    from apps.opspilot.services.wiki.embedding_service import clear_page_vectors, index_version

    kb = _kb()
    cv = _page(kb, "A", "   ").current_version

    assert index_version(cv, None, embed_fn=lambda texts: pytest.fail("empty body should not embed")) is False
    assert clear_page_vectors([]) == 0


@pytest.mark.django_db
def test_clear_page_vectors_removes_version_embedding_and_chunks():
    from apps.opspilot.models import PageChunk
    from apps.opspilot.services.wiki.embedding_service import clear_page_vectors

    kb = _kb()
    page = _page(kb, "A", "# H\nbody")
    version = page.current_version
    version.embedding = [0.1, 0.2]
    version.save(update_fields=["embedding"])
    PageChunk.objects.create(page=page, version=version, idx=0, text="body", embedding=[0.3])

    assert clear_page_vectors([page.id]) == 1

    version.refresh_from_db()
    assert version.embedding == []
    assert list(PageChunk.objects.filter(page=page).values_list("embedding", flat=True)) == [[]]


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
    assert results[0]["explanation"]["matched_by"] == ["vector"]
    assert results[0]["explanation"]["vector_score"] == results[0]["score"]


@pytest.mark.django_db
def test_semantic_search_empty_without_index():
    from apps.opspilot.services.wiki.embedding_service import semantic_search

    kb = _kb()
    _page(kb, "A", "body")  # 未建索引
    assert semantic_search(kb, "x", embed_fn=lambda texts: [[1.0]]) == []


@pytest.mark.django_db
def test_semantic_search_empty_when_query_embedding_unavailable():
    from apps.opspilot.services.wiki.embedding_service import semantic_search

    kb = _kb()
    _page(kb, "A", "body")

    assert semantic_search(kb, "x", embed_fn=lambda texts: []) == []


@pytest.mark.django_db
def test_page_list_exposes_object_level_index_status(api_client):
    from apps.opspilot.models import BuildRecord, EmbedProvider, PageChunk

    provider = EmbedProvider.objects.create(name="embed", model="embed-model")
    kb = _kb()
    kb.embed_provider = provider
    kb.save(update_fields=["embed_provider"])
    _page(kb, "未索引页面", "# H\nmissing")
    indexed = _page(kb, "已索引页面", "# H\nindexed")
    failed = _page(kb, "失败页面", "# H\nfailed")
    indexed.current_version.embedding = [0.1, 0.2]
    indexed.current_version.save(update_fields=["embedding"])
    PageChunk.objects.create(page=indexed, version=indexed.current_version, idx=0, text="# H\nindexed", heading_path="H", embedding=[0.3])
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="partial",
        stage="done",
        affected_pages=[failed.id],
        maintenance={
            "status": "partial",
            "affected_page_ids": [failed.id],
            "stages": {
                "page_embedding": {"status": "failed", "error": "page index down"},
                "chunk_embedding": {"status": "failed", "error": "chunk index down"},
            },
        },
    )

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/?knowledge_base={kb.id}&page_size=20")

    assert response.status_code == 200, response.content
    items = {item["title"]: item for item in response.json()["data"]["items"]}
    assert items["未索引页面"]["index_status"] == "not_indexed"
    assert items["未索引页面"]["chunk_index_status"] == "not_indexed"
    assert items["已索引页面"]["index_status"] == "indexed"
    assert items["已索引页面"]["chunk_index_status"] == "indexed"
    assert items["已索引页面"]["index_detail"]["chunk_embedding"]["indexed_chunks"] == 1
    assert items["失败页面"]["index_status"] == "failed"
    assert items["失败页面"]["chunk_index_status"] == "failed"
    assert items["失败页面"]["index_detail"]["page_embedding"]["error"] == "page index down"
    assert items["失败页面"]["index_detail"]["chunk_embedding"]["error"] == "chunk index down"


@pytest.mark.django_db
def test_page_list_marks_index_status_indexing_for_running_index_record(api_client):
    from apps.opspilot.models import BuildRecord, EmbedProvider

    provider = EmbedProvider.objects.create(name="embed", model="embed-model")
    kb = _kb()
    kb.embed_provider = provider
    kb.save(update_fields=["embed_provider"])
    page = _page(kb, "索引中页面", "# H\nbody")
    running = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="kb_reindex",
        status="running",
        stage="indexing",
        affected_pages=[page.id],
        maintenance={},
    )

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/?knowledge_base={kb.id}&page_size=20")

    assert response.status_code == 200, response.content
    item = response.json()["data"]["items"][0]
    assert item["index_status"] == "indexing"
    assert item["chunk_index_status"] == "indexing"
    assert item["index_detail"]["page_embedding"]["build_record_id"] == running.id
    assert item["index_detail"]["chunk_embedding"]["trigger"] == "kb_reindex"


@pytest.mark.django_db
def test_page_list_marks_index_status_skipped_without_embed_provider(api_client):
    kb = _kb()
    _page(kb, "无向量模型", "# H\nbody")

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/?knowledge_base={kb.id}&page_size=20")

    assert response.status_code == 200, response.content
    item = response.json()["data"]["items"][0]
    assert item["index_status"] == "skipped"
    assert item["chunk_index_status"] == "skipped"
    assert item["index_detail"]["page_embedding"]["reason"] == "no_embed_provider"


@pytest.mark.django_db
def test_page_index_status_handles_empty_body_and_missing_current_version(api_client):
    from apps.opspilot.models import EmbedProvider, KnowledgePage

    provider = EmbedProvider.objects.create(name="embed", model="embed-model")
    kb = _kb()
    kb.embed_provider = provider
    kb.save(update_fields=["embed_provider"])
    KnowledgePage.objects.create(knowledge_base=kb, page_type="concept", title="无当前版本")
    _page(kb, "空正文", "   ")

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/?knowledge_base={kb.id}&page_size=20")

    assert response.status_code == 200, response.content
    items = {item["title"]: item for item in response.json()["data"]["items"]}
    assert items["无当前版本"]["index_status"] == "not_indexed"
    assert items["无当前版本"]["chunk_index_status"] == "not_indexed"
    assert items["无当前版本"]["index_detail"]["page_embedding"]["reason"] == "no_current_version"
    assert items["空正文"]["index_status"] == "skipped"
    assert items["空正文"]["chunk_index_status"] == "skipped"
    assert items["空正文"]["index_detail"]["page_embedding"]["reason"] == "empty_body"


@pytest.mark.django_db
def test_page_reindex_endpoint_retries_single_page_index_and_records_result(api_client, monkeypatch):
    from apps.opspilot.models import BuildRecord, EmbedProvider
    from apps.opspilot.viewsets import wiki_page_view

    provider = EmbedProvider.objects.create(name="embed", model="embed-model")
    kb = _kb()
    kb.embed_provider = provider
    kb.save(update_fields=["embed_provider"])
    page = _page(kb, "重建索引页面", "# H\nbody")
    calls = []

    def fake_index(version, embed_provider):
        calls.append(("page", version.id, embed_provider.id))
        return True

    def fake_chunks(page_arg, embed_provider):
        calls.append(("chunks", page_arg.id, embed_provider.id))
        return 2

    monkeypatch.setattr(wiki_page_view, "index_version", fake_index, raising=False)
    monkeypatch.setattr(wiki_page_view, "reindex_page_chunks", fake_chunks, raising=False)

    response = api_client.post(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/reindex/", {}, format="json")

    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["maintenance"]["status"] == "success"
    assert data["maintenance"]["stages"]["page_embedding"] == {"status": "success", "count": 1}
    assert data["maintenance"]["stages"]["chunk_embedding"] == {"status": "success", "count": 2}
    assert calls == [("page", page.current_version_id, provider.id), ("chunks", page.id, provider.id)]
    record = BuildRecord.objects.get(knowledge_base=kb, trigger="page_reindex")
    assert record.status == "success"
    assert record.affected_pages == [page.id]


@pytest.mark.django_db
def test_page_reindex_endpoint_records_failed_stage(api_client, monkeypatch):
    from apps.opspilot.models import BuildRecord, EmbedProvider
    from apps.opspilot.viewsets import wiki_page_view

    provider = EmbedProvider.objects.create(name="embed", model="embed-model")
    kb = _kb()
    kb.embed_provider = provider
    kb.save(update_fields=["embed_provider"])
    page = _page(kb, "索引失败页面", "# H\nbody")
    monkeypatch.setattr(wiki_page_view, "index_version", lambda version, embed_provider: False, raising=False)
    monkeypatch.setattr(wiki_page_view, "reindex_page_chunks", lambda page_arg, embed_provider: 0, raising=False)

    response = api_client.post(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/reindex/", {}, format="json")

    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["status"] == "partial"
    assert data["maintenance"]["stages"]["page_embedding"]["status"] == "failed"
    assert data["maintenance"]["stages"]["chunk_embedding"]["status"] == "failed"
    record = BuildRecord.objects.get(knowledge_base=kb, trigger="page_reindex")
    assert record.status == "partial"
    assert record.maintenance == data["maintenance"]


@pytest.mark.django_db
def test_page_reindex_endpoint_requires_embed_provider(api_client):
    from apps.opspilot.models import BuildRecord

    kb = _kb()
    page = _page(kb, "无向量模型", "# H\nbody")

    response = api_client.post(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/reindex/", {}, format="json")

    assert response.status_code == 400
    assert "向量模型" in response.json()["message"]
    assert not BuildRecord.objects.filter(knowledge_base=kb, trigger="page_reindex").exists()


@pytest.mark.django_db
def test_material_reindex_endpoint_retries_contributed_active_pages(api_client, monkeypatch):
    from apps.opspilot.models import BuildRecord, EmbedProvider, Material, PageEvidence
    from apps.opspilot.viewsets import wiki_material_view

    provider = EmbedProvider.objects.create(name="embed", model="embed-model")
    kb = _kb()
    kb.embed_provider = provider
    kb.save(update_fields=["embed_provider"])
    material = Material.objects.create(knowledge_base=kb, name="资料", material_type="text")
    first = _page(kb, "页面 A", "# A\nbody")
    second = _page(kb, "页面 B", "# B\nbody")
    archived = _page(kb, "归档页面", "# C\nbody")
    archived.status = "archived"
    archived.save(update_fields=["status"])
    for page in [first, second, archived]:
        PageEvidence.objects.create(page=page, material=material)
    calls = []

    def fake_index(version, embed_provider):
        calls.append(("page", version.id, embed_provider.id))
        return True

    def fake_chunks(page_arg, embed_provider):
        calls.append(("chunks", page_arg.id, embed_provider.id))
        return 1

    monkeypatch.setattr(wiki_material_view, "index_version", fake_index, raising=False)
    monkeypatch.setattr(wiki_material_view, "reindex_page_chunks", fake_chunks, raising=False)

    response = api_client.post(f"/api/v1/opspilot/wiki_mgmt/material/{material.id}/reindex/", {}, format="json")

    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["maintenance"]["status"] == "success"
    assert data["maintenance"]["affected_page_ids"] == [first.id, second.id]
    assert data["maintenance"]["stages"]["page_embedding"] == {"status": "success", "count": 2}
    assert data["maintenance"]["stages"]["chunk_embedding"] == {"status": "success", "count": 2}
    assert calls == [
        ("page", first.current_version_id, provider.id),
        ("chunks", first.id, provider.id),
        ("page", second.current_version_id, provider.id),
        ("chunks", second.id, provider.id),
    ]
    record = BuildRecord.objects.get(knowledge_base=kb, trigger="material_reindex")
    assert record.inputs == {"material_id": material.id, "material_name": material.name}
    assert record.affected_pages == [first.id, second.id]


@pytest.mark.django_db
def test_material_reindex_endpoint_requires_embed_provider(api_client):
    from apps.opspilot.models import BuildRecord, Material, PageEvidence

    kb = _kb()
    material = Material.objects.create(knowledge_base=kb, name="资料", material_type="text")
    page = _page(kb, "无向量模型", "# H\nbody")
    PageEvidence.objects.create(page=page, material=material)

    response = api_client.post(f"/api/v1/opspilot/wiki_mgmt/material/{material.id}/reindex/", {}, format="json")

    assert response.status_code == 400
    assert "向量模型" in response.json()["message"]
    assert not BuildRecord.objects.filter(knowledge_base=kb, trigger="material_reindex").exists()


def test_embed_texts_calls_openai_compatible_provider(monkeypatch):
    from apps.opspilot.services.wiki import embedding_service

    calls = []

    class FakeEmbeddings:
        def create(self, model, input):
            calls.append((model, input))
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2]), SimpleNamespace(embedding=[0.3, 0.4])])

    class FakeOpenAI:
        def __init__(self, base_url, api_key):
            calls.append((base_url, api_key))
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr(embedding_service, "OpenAI", FakeOpenAI)
    provider = SimpleNamespace(base_url="http://embed", api_key="secret", model_name="embed-model", id=1)

    assert embedding_service.embed_texts(["a", "b"], provider) == [[0.1, 0.2], [0.3, 0.4]]
    assert calls == [("http://embed", "secret"), ("embed-model", ["a", "b"])]


def test_embed_texts_returns_empty_when_provider_fails(monkeypatch):
    from apps.opspilot.services.wiki import embedding_service

    class FakeOpenAI:
        def __init__(self, base_url, api_key):
            raise RuntimeError("provider down")

    monkeypatch.setattr(embedding_service, "OpenAI", FakeOpenAI)
    provider = SimpleNamespace(base_url="http://embed", api_key="secret", model_name="embed-model", id=1)

    assert embedding_service.embed_texts(["a"], provider) == []
