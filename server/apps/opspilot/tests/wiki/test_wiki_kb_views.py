import pytest


@pytest.mark.django_db
class TestWikiKBViews:
    BASE = "/api/v1/opspilot/wiki_mgmt/knowledge_base/"

    def _data(self, resp):
        body = resp.json()
        return body.get("data", body)

    def test_create_and_list(self, api_client):
        resp = api_client.post(
            self.BASE,
            {"name": "kb1", "team": [1], "purpose_md": "# P", "schema_md": "# S"},
            format="json",
        )
        assert resp.status_code in (200, 201), resp.content
        lst = api_client.get(self.BASE)
        assert lst.status_code == 200
        data = self._data(lst)
        assert "count" in data and "items" in data  # 分页格式,与 EntityList 一致
        names = [x["name"] for x in data["items"]]
        assert "kb1" in names

    def test_templates_endpoint(self, api_client):
        resp = api_client.get(self.BASE + "templates/")
        assert resp.status_code == 200
        keys = {t["key"] for t in self._data(resp)}
        assert "ops_qa" in keys and "general" in keys

    def test_generate_purpose_schema_endpoint_fallback(self, api_client):
        resp = api_client.post(
            self.BASE + "generate_purpose_schema/",
            {"template_key": "ops_qa", "description": "运维问答库"},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        data = self._data(resp)
        assert "运维问答库" in data["purpose_md"]
        assert "知识类型" in data["schema_md"]

    def test_retrieve_update_patch_search_and_delete(self, api_client):
        from apps.opspilot.models import WikiKnowledgeBase

        kb = WikiKnowledgeBase.objects.create(name="blueking-kb", team=[1], purpose_md="# P", schema_md="# S")

        retrieved = api_client.get(f"{self.BASE}{kb.id}/")
        assert retrieved.status_code == 200
        assert self._data(retrieved)["name"] == "blueking-kb"

        listed = api_client.get(f"{self.BASE}?search=blueking&page=bad&page_size=bad")
        assert listed.status_code == 200
        assert any(item["id"] == kb.id for item in self._data(listed)["items"])

        updated = api_client.put(
            f"{self.BASE}{kb.id}/",
            {"name": "updated-kb", "team": [1], "purpose_md": "# P2", "schema_md": "# S2"},
            format="json",
        )
        assert updated.status_code == 200
        assert self._data(updated)["name"] == "updated-kb"

        patched = api_client.patch(f"{self.BASE}{kb.id}/", {"introduction": "intro"}, format="json")
        assert patched.status_code == 200
        assert self._data(patched)["introduction"] == "intro"

        deleted = api_client.delete(f"{self.BASE}{kb.id}/")
        assert deleted.status_code == 200
        assert not WikiKnowledgeBase.objects.filter(id=kb.id).exists()

    def test_reindex_and_semantic_actions(self, api_client, monkeypatch):
        from apps.opspilot.models import EmbedProvider, WikiKnowledgeBase
        from apps.opspilot.viewsets import wiki_kb_view

        provider = EmbedProvider.objects.create(name="embed", model="embed-model")
        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        kb.embed_provider = provider
        kb.save(update_fields=["embed_provider"])
        monkeypatch.setattr(wiki_kb_view, "wiki_hybrid_search", lambda kb, query, top_k=5: [{"kind": "page", "title": query, "score": top_k}])
        monkeypatch.setattr(wiki_kb_view, "wiki_semantic_search", lambda kb, query, top_k=5: [{"title": query, "score": top_k}])
        monkeypatch.setattr(wiki_kb_view, "wiki_reindex_chunks", lambda kb: (2, 9))
        monkeypatch.setattr(wiki_kb_view, "wiki_chunk_search", lambda kb, query, top_k=5: [{"snippet": query, "score": top_k}])

        hybrid = api_client.post(f"{self.BASE}{kb.id}/hybrid_search/", {"query": "重启", "top_k": 7}, format="json")
        assert hybrid.status_code == 200
        assert self._data(hybrid)[0]["score"] == 7

        reindex = api_client.post(f"{self.BASE}{kb.id}/reindex/", {}, format="json")
        assert reindex.status_code == 200
        assert self._data(reindex)["trigger"] == "kb_reindex"
        assert self._data(reindex)["counts"] == {"indexed_pages": 0, "indexed_chunks": 0}

        semantic = api_client.post(f"{self.BASE}{kb.id}/semantic_search/", {"query": "语义", "top_k": 4}, format="json")
        assert semantic.status_code == 200
        assert self._data(semantic)[0]["score"] == 4

        chunks = api_client.post(f"{self.BASE}{kb.id}/reindex_chunks/", {}, format="json")
        assert chunks.status_code == 200
        assert self._data(chunks) == {"pages": 2, "chunks": 9}

        chunk_search = api_client.post(f"{self.BASE}{kb.id}/chunk_search/", {"query": "片段", "top_k": 6}, format="json")
        assert chunk_search.status_code == 200
        assert self._data(chunk_search)[0]["score"] == 6

    def test_reindex_action_records_page_and_chunk_index_result(self, api_client, monkeypatch):
        from apps.opspilot.models import BuildRecord, EmbedProvider, WikiKnowledgeBase
        from apps.opspilot.services.wiki.page_service import create_manual_page
        from apps.opspilot.viewsets import wiki_kb_view

        provider = EmbedProvider.objects.create(name="embed", model="embed-model")
        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        kb.embed_provider = provider
        kb.save(update_fields=["embed_provider"])
        first = create_manual_page(kb, page_type="concept", title="页面一", body="body one", created_by="u")
        second = create_manual_page(kb, page_type="concept", title="页面二", body="body two", created_by="u")
        archived = create_manual_page(kb, page_type="concept", title="归档页", body="old", created_by="u")
        archived.status = "archived"
        archived.save(update_fields=["status"])
        calls = []

        def fake_index(version, embed_provider):
            calls.append(("page", version.page_id))
            return True

        def fake_chunks(page, embed_provider):
            calls.append(("chunks", page.id))
            return 2

        monkeypatch.setattr(wiki_kb_view, "index_version", fake_index, raising=False)
        monkeypatch.setattr(wiki_kb_view, "reindex_page_chunks", fake_chunks, raising=False)

        response = api_client.post(f"{self.BASE}{kb.id}/reindex/", {}, format="json")

        assert response.status_code == 200, response.content
        data = self._data(response)
        assert data["trigger"] == "kb_reindex"
        assert data["status"] == "success"
        assert data["counts"] == {"indexed_pages": 2, "indexed_chunks": 4}
        assert data["affected_pages"] == [first.id, second.id]
        assert ("page", archived.id) not in calls
        assert BuildRecord.objects.filter(id=data["id"], knowledge_base=kb).exists()
