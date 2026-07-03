import pytest


def test_llm_summarize_uses_entire_long_markdown(monkeypatch):
    from types import SimpleNamespace

    from apps.opspilot.services.wiki import material_service

    tail_marker = "TAIL_SUMMARY_FACT"
    long_markdown = ("head content\n" * 900) + f"\n{tail_marker} 是长文件尾部的重要事实。"
    prompts = []

    monkeypatch.setattr(
        material_service.LLMModel.objects,
        "get",
        lambda id: SimpleNamespace(openai_api_base="", openai_api_key="", model_name="fake"),
    )

    def fake_invoke(request, messages):
        prompt = messages[0]["content"]
        prompts.append(prompt)
        if "资料片段" in prompt:
            return "尾部摘要事实" if tail_marker in prompt else "头部摘要事实"
        if "分片摘要" in prompt:
            return "最终摘要包含尾部摘要事实"
        return "旧摘要没有尾部"

    monkeypatch.setattr(material_service.LLMClientFactory, "invoke_isolated", fake_invoke)

    summary = material_service._llm_summarize(long_markdown, llm_model_id=1)

    assert "尾部摘要事实" in summary
    assert any(tail_marker in prompt for prompt in prompts)


def test_invoke_summary_llm_passes_isolated_request(monkeypatch):
    from types import SimpleNamespace

    from apps.opspilot.services.wiki import material_service

    seen = {}

    def fake_invoke(request, messages):
        seen["request"] = request
        seen["messages"] = messages
        return "summary"

    monkeypatch.setattr(material_service.LLMClientFactory, "invoke_isolated", fake_invoke)
    llm = SimpleNamespace(openai_api_base="http://llm", openai_api_key="secret", model_name="model-a")

    assert material_service._invoke_summary_llm(llm, "prompt body") == "summary"
    assert seen["request"].openai_api_base == "http://llm"
    assert seen["request"].openai_api_key == "secret"
    assert seen["request"].model == "model-a"
    assert seen["request"].temperature == 0.3
    assert seen["request"].user_message == "prompt body"
    assert seen["messages"] == [{"role": "user", "content": "prompt body"}]


def test_llm_summarize_handles_empty_single_chunk_and_llm_failure(monkeypatch):
    from types import SimpleNamespace

    from apps.opspilot.services.wiki import material_service

    assert material_service._llm_summarize("  ", llm_model_id=1) == ""

    monkeypatch.setattr(
        material_service.LLMModel.objects,
        "get",
        lambda id: SimpleNamespace(openai_api_base="", openai_api_key="", model_name="fake"),
    )
    monkeypatch.setattr(material_service, "split_text_for_llm", lambda text: ["single chunk"])
    monkeypatch.setattr(material_service, "_invoke_summary_llm", lambda llm, prompt: "single summary")

    assert material_service._llm_summarize("single chunk", llm_model_id=1) == "single summary"

    def raise_invoke(llm, prompt):
        raise RuntimeError("llm down")

    monkeypatch.setattr(material_service, "_invoke_summary_llm", raise_invoke)

    assert material_service._llm_summarize("fallback text", llm_model_id=1) == "fallback text"


@pytest.mark.django_db
def test_ingest_text_material_uses_parser_and_persists_markdown(monkeypatch):
    from apps.opspilot.models import Material, MaterialVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.material_service import ingest_material

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    m = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="运维知识:重启服务用 systemctl restart。")
    saved = {}

    class Parser:
        def parse_text(self, text, *, filename="raw.txt"):
            assert text == "运维知识:重启服务用 systemctl restart。"
            return "# Parsed\n\nsystemctl restart"

    monkeypatch.setattr("apps.opspilot.services.wiki.material_service.get_parser", lambda: Parser())

    def fake_save(material, md, digest):
        saved["md"] = md
        return "wiki/parsed/m.md"

    monkeypatch.setattr("apps.opspilot.services.wiki.material_service.save_parsed_markdown", fake_save)

    ingest_material(m, llm_model_id=None)
    m.refresh_from_db()
    assert m.status == "done"
    assert m.content_hash
    assert saved["md"] == "# Parsed\n\nsystemctl restart"
    assert "systemctl" in m.ai_summary  # 无模型时回退为截断正文
    version = MaterialVersion.objects.get(material=m)
    assert m.current_version_id == version.id
    assert version.content_locator == "wiki/parsed/m.md"
    assert version.content_hash == m.content_hash


@pytest.mark.django_db
def test_ingest_web_material_uses_markitdown_parser(monkeypatch):
    from apps.opspilot.models import Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki.material_service import ingest_material

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    material = Material.objects.create(knowledge_base=kb, name="site", material_type="web", url="https://example.com/runbook")
    calls = []

    class Parser:
        def parse_url(self, url, *, vision_client=None):
            calls.append((url, vision_client))
            return "# Web Runbook"

    monkeypatch.setattr("apps.opspilot.services.wiki.material_service.get_parser", lambda: Parser())
    monkeypatch.setattr("apps.opspilot.services.wiki.material_service.save_parsed_markdown", lambda material, md, digest: "wiki/parsed/web.md")

    ingest_material(material, llm_model_id=None)

    material.refresh_from_db()
    assert calls == [("https://example.com/runbook", None)]
    assert material.status == "done"
    assert material.current_version.content_locator == "wiki/parsed/web.md"


@pytest.mark.django_db
def test_ingest_hash_unchanged_skips_summary_and_new_version(monkeypatch):
    from apps.opspilot.models import Material, MaterialVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.material_service import compute_hash, ingest_material

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    markdown = "# Same"
    digest = compute_hash(markdown)
    material = Material.objects.create(
        knowledge_base=kb,
        name="m",
        material_type="text",
        text_content="same",
        content_hash=digest,
        ai_summary="old summary",
    )
    MaterialVersion.objects.create(material=material, content_hash=digest, content_locator="wiki/parsed/old.md")

    class Parser:
        def parse_text(self, text, *, filename="raw.txt"):
            return markdown

    monkeypatch.setattr("apps.opspilot.services.wiki.material_service.get_parser", lambda: Parser())
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.material_service._llm_summarize",
        lambda text, llm_model_id: pytest.fail("summary should not be regenerated"),
    )

    ingest_material(material, llm_model_id=None)

    material.refresh_from_db()
    assert material.status == "done"
    assert material.ai_summary == "old summary"
    assert MaterialVersion.objects.filter(material=material).count() == 1


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

    def test_create_text_material_auto_ingests(self, api_client, monkeypatch):
        from apps.opspilot.models import WikiKnowledgeBase

        class Parser:
            def parse_text(self, text, *, filename="raw.txt"):
                return text

        monkeypatch.setattr("apps.opspilot.services.wiki.material_service.get_parser", lambda: Parser())
        monkeypatch.setattr("apps.opspilot.services.wiki.material_service.save_parsed_markdown", lambda material, md, digest: "wiki/parsed/view.md")

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
        assert any(x["name"] == "m1" for x in self._data(lst)["items"])

    def test_list_retrieve_info_and_async_actions(self, api_client, monkeypatch):
        from apps.opspilot.models import KnowledgePage, Material, MaterialVersion, PageEvidence, PageVersion, WikiKnowledgeBase
        from apps.opspilot.viewsets import wiki_material_view

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        material = Material.objects.create(
            knowledge_base=kb,
            name="web",
            material_type="web",
            url="https://example.com/wiki",
            status="done",
            ai_summary="summary",
        )
        version = MaterialVersion.objects.create(material=material, content_hash="h1", content_locator="wiki/parsed/web.md")
        material.current_version = version
        material.save(update_fields=["current_version"])
        page = KnowledgePage.objects.create(knowledge_base=kb, page_type="concept", title="Page")
        page_version = PageVersion.objects.create(page=page, no=1, body="body", change_type="ai_create", is_current=True)
        page.current_version = page_version
        page.save(update_fields=["current_version"])
        PageEvidence.objects.create(page=page, material=material, material_version=version)

        listed = api_client.get(self.BASE + f"?knowledge_base={kb.id}&status=done&page=bad&page_size=bad")
        assert listed.status_code == 200
        assert listed.json()["data"]["count"] == 1

        retrieved = api_client.get(self.BASE + f"{material.id}/")
        assert retrieved.status_code == 200
        assert self._data(retrieved)["id"] == material.id

        info = api_client.get(self.BASE + f"{material.id}/info/")
        assert info.status_code == 200
        data = self._data(info)
        assert data["original"] == "https://example.com/wiki"
        assert data["versions"][0]["content_locator"] == "wiki/parsed/web.md"
        assert data["contributed_pages"][0]["title"] == "Page"

        def fake_enqueue(material, llm_model_id):
            material.status = "parsing"
            material.save(update_fields=["status", "updated_at"])

        monkeypatch.setattr(wiki_material_view.WikiMaterialViewSet, "_enqueue_ingest", staticmethod(fake_enqueue))

        created_file = api_client.post(
            self.BASE,
            {"knowledge_base": kb.id, "name": "file without upload", "material_type": "file"},
            format="json",
        )
        assert created_file.status_code == 201
        assert self._data(created_file)["status"] == "parsing"

        ingest = api_client.post(self.BASE + f"{material.id}/ingest/", {}, format="json")
        assert ingest.status_code == 200
        assert self._data(ingest)["status"] == "parsing"

        calls = []

        class Task:
            @staticmethod
            def delay(material_id, llm_model_id, operator):
                calls.append((material_id, llm_model_id, operator))

        monkeypatch.setattr("apps.opspilot.tasks.wiki_build_material_task", Task)
        build = api_client.post(self.BASE + f"{material.id}/build/", {"async": True}, format="json")
        assert build.status_code == 200
        assert self._data(build)["status"] == "building"
        assert calls and calls[0][0] == material.id
