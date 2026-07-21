import json
from unittest.mock import patch

import pytest

_FAKE_PAGES = [
    {"page_type": "concept", "title": "重启服务", "tags": ["ops"], "body": "用 systemctl restart 重启。"},
    {"page_type": "qa", "title": "如何重启", "tags": [], "body": "问:如何重启?答:systemctl restart。"},
]


@pytest.mark.django_db
def test_build_from_material_creates_pages_versions_evidence():
    from apps.opspilot.models import KnowledgePage, Material, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="t", ai_summary="重启服务摘要")

    with (
        patch.object(build_service, "_llm_extract_facts", return_value="facts"),
        patch.object(build_service, "_llm_generate_pages", return_value=_FAKE_PAGES),
    ):
        record = build_service.build_from_material(material, llm_model_id=1)

    assert record.status == "success"
    assert record.counts["new"] == 2
    assert KnowledgePage.objects.filter(knowledge_base=kb).count() == 2
    page = KnowledgePage.objects.get(title="重启服务")
    assert page.current_version is not None
    assert PageVersion.objects.filter(page=page, is_current=True).count() == 1
    assert PageEvidence.objects.filter(page=page, material=material).count() == 1


@pytest.mark.django_db
def test_build_from_material_records_source_chunk_locator_for_new_page(monkeypatch):
    from apps.opspilot.models import Material, PageEvidence, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="raw")
    tail_marker = "TAIL_COMPONENT_NEEDS_PAGE"
    parsed_markdown = ("head content\n" * 1200) + f"\n{tail_marker} 是尾部组件的关键事实。"

    monkeypatch.setattr(build_service, "load_parsed_markdown", lambda m: parsed_markdown)
    monkeypatch.setattr(build_service, "_llm_extract_facts", lambda text, llm_model_id: "")
    monkeypatch.setattr(
        build_service,
        "_llm_generate_pages",
        lambda kb, source_text, llm_model_id: [{"page_type": "entity", "title": "尾部组件", "tags": [], "body": f"{tail_marker} 负责尾部能力。"}],
    )

    build_service.build_from_material(material, llm_model_id=1)

    evidence = PageEvidence.objects.get(material=material)
    locator = json.loads(evidence.locator)
    assert locator["kind"] == "material_chunk"
    assert locator["chunk_index"] > 0
    assert locator["chunk_count"] > 1
    assert locator["start"] < locator["end"]
    assert tail_marker in locator["snippet"]


@pytest.mark.django_db
def test_build_from_material_updates_existing_evidence_locator_when_source_chunk_changes(monkeypatch):
    from apps.opspilot.models import Material, PageEvidence, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="raw")
    first_text = "HEAD_MARKER 是头部事实。"
    second_text = ("head filler\n" * 1200) + "\nTAIL_MARKER 是尾部事实。"
    generated_pages = [
        {"page_type": "entity", "title": "平台组件", "tags": [], "body": "HEAD_MARKER 是头部事实。"},
        {"page_type": "entity", "title": "平台组件", "tags": [], "body": "TAIL_MARKER 是尾部事实。"},
    ]

    monkeypatch.setattr(build_service, "_llm_extract_facts", lambda text, llm_model_id: "")
    monkeypatch.setattr(build_service, "_llm_generate_pages", lambda kb, source_text, llm_model_id: [generated_pages.pop(0)])
    monkeypatch.setattr(build_service, "load_parsed_markdown", lambda m: first_text)
    build_service.build_from_material(material, llm_model_id=1)

    evidence = PageEvidence.objects.get(material=material)
    first_locator = json.loads(evidence.locator)
    assert "HEAD_MARKER" in first_locator["snippet"]

    monkeypatch.setattr(build_service, "load_parsed_markdown", lambda m: second_text)
    build_service.build_from_material(material, llm_model_id=1)

    evidence.refresh_from_db()
    second_locator = json.loads(evidence.locator)
    assert second_locator["chunk_index"] > 0
    assert "TAIL_MARKER" in second_locator["snippet"]


@pytest.mark.django_db
def test_build_record_inputs_include_source_trace(monkeypatch):
    from apps.opspilot.models import Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(knowledge_base=kb, name="平台资料", material_type="text", text_content="raw")
    marker = "TRACE_MARKER_COMPONENT"
    parsed_markdown = ("head content\n" * 1200) + f"\n{marker} 属于尾部片段。"

    monkeypatch.setattr(build_service, "load_parsed_markdown", lambda m: parsed_markdown)
    monkeypatch.setattr(build_service, "_llm_extract_facts", lambda text, llm_model_id: "")
    monkeypatch.setattr(
        build_service,
        "_llm_generate_pages",
        lambda kb, source_text, llm_model_id: [{"page_type": "entity", "title": "尾部组件", "tags": [], "body": f"{marker} 正文"}],
    )

    record = build_service.build_from_material(material, llm_model_id=1)

    source_trace = record.inputs["source_trace"]
    assert record.inputs["material_name"] == "平台资料"
    assert len(source_trace["chunks"]) > 1
    assert source_trace["chunks"][-1]["index"] > 0
    assert marker in source_trace["chunks"][-1]["preview"]
    page_action = source_trace["page_actions"][0]
    assert page_action["title"] == "尾部组件"
    assert page_action["action"] == "new"
    assert page_action["source_locator"]["chunk_index"] == source_trace["chunks"][-1]["index"]


@pytest.mark.django_db
def test_rebuilding_material_after_partial_page_delete_does_not_duplicate_existing_pages():
    from apps.opspilot.models import KnowledgePage, Material, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="t")

    with (
        patch.object(build_service, "_llm_extract_facts", return_value="facts"),
        patch.object(build_service, "_llm_generate_pages", return_value=_FAKE_PAGES),
    ):
        first_record = build_service.build_from_material(material, llm_model_id=1)

    deleted_page = KnowledgePage.objects.get(knowledge_base=kb, title="重启服务")
    kept_page = KnowledgePage.objects.get(knowledge_base=kb, title="如何重启")
    kept_page_id = kept_page.id
    deleted_page.delete()

    with (
        patch.object(build_service, "_llm_extract_facts", return_value="facts"),
        patch.object(build_service, "_llm_generate_pages", return_value=_FAKE_PAGES),
    ):
        second_record = build_service.build_from_material(material, llm_model_id=1)

    assert first_record.counts["new"] == 2
    assert second_record.counts == {"new": 1, "updated": 0, "unchanged": 1, "pending_review": 0}
    assert KnowledgePage.objects.filter(knowledge_base=kb, title="重启服务").count() == 1
    assert KnowledgePage.objects.filter(knowledge_base=kb, title="如何重启").count() == 1
    assert KnowledgePage.objects.get(knowledge_base=kb, title="如何重启").id == kept_page_id
    assert PageVersion.objects.filter(page_id=kept_page_id).count() == 1
    assert PageEvidence.objects.filter(page_id=kept_page_id, material=material).count() == 1


@pytest.mark.django_db
def test_same_title_from_different_materials_preserves_existing_body_and_sources(monkeypatch):
    from apps.opspilot.models import KnowledgePage, Material, PageEvidence, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    first_material = Material.objects.create(knowledge_base=kb, name="first", material_type="text", text_content="first")
    second_material = Material.objects.create(knowledge_base=kb, name="second", material_type="text", text_content="second")

    with (
        patch.object(build_service, "_llm_extract_facts", return_value="facts"),
        patch.object(
            build_service,
            "_llm_generate_pages",
            return_value=[{"page_type": "entity", "title": "蓝鲸平台", "tags": ["first"], "body": "第一份资料正文"}],
        ),
    ):
        first_record = build_service.build_from_material(first_material, llm_model_id=1)

    monkeypatch.setattr(
        build_service,
        "_classify_page_change",
        lambda page, page_data, llm_model_id: {
            "same_subject": True,
            "relation": "supplement",
            "reason": "新资料补充了非矛盾信息",
        },
    )
    with (
        patch.object(build_service, "_llm_extract_facts", return_value="facts"),
        patch.object(
            build_service,
            "_llm_generate_pages",
            return_value=[{"page_type": "entity", "title": "蓝鲸平台", "tags": ["second"], "body": "第二份资料正文"}],
        ),
    ):
        second_record = build_service.build_from_material(second_material, llm_model_id=1)

    page = KnowledgePage.objects.get(knowledge_base=kb, title="蓝鲸平台")
    body = page.current_version.body
    assert first_record.counts["new"] == 1
    assert second_record.counts == {"new": 0, "updated": 1, "unchanged": 0, "pending_review": 0}
    assert "第一份资料正文" in body
    assert "第二份资料正文" in body
    assert PageEvidence.objects.filter(page=page).count() == 2


@pytest.mark.django_db
def test_llm_generate_pages_exposes_existing_page_catalog_and_preserves_match_id(monkeypatch):
    from apps.opspilot.models import KnowledgePage, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb-catalog", team=[1], purpose_md="# P", schema_md="# S")
    existing = KnowledgePage.objects.create(
        knowledge_base=kb,
        page_type="concept",
        title="出差报销流程",
        contribution="ai",
    )

    def fake_invoke(llm_model_id, prompt):
        assert "existing_page_id" in prompt
        assert str(existing.id) in prompt
        assert existing.title in prompt
        return json.dumps(
            {
                "pages": [
                    {
                        "page_type": "concept",
                        "title": "差旅报销",
                        "tags": ["报销"],
                        "body": "超过 5000 元由 Leader B 终审。",
                        "existing_page_id": existing.id,
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(build_service, "_invoke_llm", fake_invoke)

    pages = build_service._llm_generate_pages(kb, "报销规则", llm_model_id=1)

    assert pages[0]["existing_page_id"] == existing.id


@pytest.mark.django_db
def test_build_ai_conflict_for_drifted_title_creates_review_candidate(monkeypatch):
    from apps.opspilot.models import CheckItem, KnowledgePage, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb-ai-conflict", team=[1], purpose_md="# P", schema_md="# S")
    material_a, version_a = _decision_material(kb, "A", "hash-a")
    material_b, _version_b = _decision_material(kb, "B", "hash-b")
    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        page_type="concept",
        title="出差报销流程",
        contribution="ai",
    )
    current = PageVersion.objects.create(
        page=page,
        no=1,
        body="超过 5000 元由 Leader A 终审。",
        change_type="ai_create",
        is_current=True,
    )
    page.current_version = current
    page.save(update_fields=["current_version", "updated_at"])
    PageEvidence.objects.create(page=page, material=material_a, material_version=version_a)

    monkeypatch.setattr(build_service, "_llm_extract_facts", lambda text, llm_model_id: text)
    monkeypatch.setattr(
        build_service,
        "_llm_generate_pages",
        lambda kb, source_text, llm_model_id: [
            {
                "page_type": "concept",
                "title": "差旅报销",
                "tags": ["报销"],
                "body": "超过 5000 元由 Leader B 终审。",
                "existing_page_id": page.id,
            }
        ],
    )
    monkeypatch.setattr(
        build_service,
        "_classify_page_change",
        lambda page, page_data, llm_model_id: {
            "same_subject": True,
            "relation": "conflict",
            "reason": "同一金额区间的最终审批人不一致",
        },
        raising=False,
    )

    record = build_service.build_from_material(material_b, llm_model_id=1, operator="admin")

    assert record.counts == {"new": 0, "updated": 0, "unchanged": 0, "pending_review": 1}
    assert KnowledgePage.objects.filter(knowledge_base=kb).count() == 1
    check = CheckItem.objects.get(knowledge_base=kb, status="open")
    assert check.related == {"pages": [page.id], "materials": [material_b.id]}
    page.refresh_from_db()
    assert page.current_version.body == "超过 5000 元由 Leader A 终审。"


@pytest.mark.django_db
def test_build_from_material_creates_review_candidate_for_human_page(monkeypatch):
    from apps.opspilot.models import CheckItem, KnowledgePage, Material, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="蓝鲸平台资料")
    page = KnowledgePage.objects.create(knowledge_base=kb, page_type="entity", title="蓝鲸平台", contribution="human")
    version = PageVersion.objects.create(page=page, no=1, body="人工正文", change_type="human_edit", is_current=True)
    page.current_version = version
    page.save(update_fields=["current_version"])

    monkeypatch.setattr(build_service, "_llm_extract_facts", lambda text, llm_model_id: "facts")
    monkeypatch.setattr(
        build_service,
        "_llm_generate_pages",
        lambda kb, source_text, llm_model_id: [{"page_type": "entity", "title": "蓝鲸平台", "tags": [], "body": "AI 正文"}],
    )

    record = build_service.build_from_material(material, llm_model_id=1, operator="admin")

    assert record.counts == {"new": 0, "updated": 0, "unchanged": 0, "pending_review": 1}
    assert record.affected_pages == [page.id]
    check = CheckItem.objects.get(knowledge_base=kb, check_type="cannot_merge")
    assert check.related == {"pages": [page.id], "materials": [material.id]}
    page.refresh_from_db()
    assert page.current_version.body == "人工正文"


@pytest.mark.django_db
def test_merge_ai_page_updates_metadata_status_and_evidence_version():
    from apps.opspilot.models import BuildRecord, KnowledgePage, Material, MaterialVersion, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="平台资料")
    material_version = MaterialVersion.objects.create(material=material, content_locator="old.md", content_hash="old")
    material.current_version = material_version
    material.save(update_fields=["current_version"])
    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        page_type="concept",
        title="旧标题",
        tags=["old"],
        contribution="ai",
        status="source_invalid",
    )
    page_version = PageVersion.objects.create(page=page, no=1, body="", change_type="ai_create", is_current=True)
    page.current_version = page_version
    page.save(update_fields=["current_version"])
    build = BuildRecord.objects.create(knowledge_base=kb, trigger="material", status="running")

    action = build_service._merge_ai_page(
        page,
        material,
        build,
        {"page_type": "entity", "title": "新标题", "tags": ["new"], "body": "新正文"},
        locator="chunk-1",
    )

    page.refresh_from_db()
    assert action == "updated"
    assert page.page_type == "entity"
    assert page.title == "新标题"
    assert page.status == "active"
    assert page.tags == ["old", "new"]
    assert page.current_version.body == "新正文"
    evidence = page.evidences.get(material=material)
    assert evidence.material_version == material_version
    assert evidence.locator == "chunk-1"


def test_parse_pages_returns_empty_for_malformed_json():
    from apps.opspilot.services.wiki import build_service

    assert build_service._parse_pages('{"pages": [bad json]}') == []


def test_parse_pages_handles_code_fence_and_missing_json_object():
    from apps.opspilot.services.wiki import build_service

    fenced = '```json\n{"pages":[{"page_type":"concept","title":"蓝鲸平台","body":"body"}]}\n```'

    assert build_service._parse_pages(fenced)[0]["title"] == "蓝鲸平台"
    assert build_service._parse_pages("no json here") == []


def test_wiki_llm_invocation_uses_wiki_timeout(monkeypatch):
    from apps.opspilot.services.wiki import build_service

    class FakeModel:
        openai_api_base = "https://api.openai.com"
        openai_api_key = "sk-key"
        model_name = "wiki-model"

    captured = {}

    monkeypatch.setenv("WIKI_LLM_INVOKE_TIMEOUT", "240")
    monkeypatch.setattr(build_service.LLMModel.objects, "get", lambda id: FakeModel())

    def fake_invoke(request, messages):
        captured["request"] = request
        return "ok"

    monkeypatch.setattr(build_service.LLMClientFactory, "invoke_isolated", fake_invoke)

    assert build_service._invoke_llm(1, "prompt") == "ok"
    assert captured["request"].extra_config["timeout"] == 240.0


def test_wiki_llm_invocation_falls_back_on_invalid_timeout_and_errors(monkeypatch):
    from apps.opspilot.services.wiki import build_service

    monkeypatch.setenv("WIKI_LLM_INVOKE_TIMEOUT", "invalid")

    assert build_service._wiki_llm_timeout() == build_service._WIKI_LLM_TIMEOUT_SECONDS
    assert build_service._invoke_llm(None, "prompt") == ""

    def raise_model_error(id):
        raise RuntimeError("boom")

    monkeypatch.setattr(build_service.LLMModel.objects, "get", raise_model_error)

    assert build_service._invoke_llm(1, "prompt") == ""


@pytest.mark.django_db
def test_build_from_material_uses_parsed_markdown_instead_of_summary(monkeypatch):
    from apps.opspilot.models import Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(
        knowledge_base=kb,
        name="m",
        material_type="text",
        text_content="raw",
        ai_summary="LOSSY SUMMARY",
    )
    seen = {}

    monkeypatch.setattr(build_service, "load_parsed_markdown", lambda m: "# Full Markdown\n\ncritical detail")
    monkeypatch.setattr(build_service, "_llm_extract_facts", lambda text, llm_model_id: seen.setdefault("text", text) or "facts")
    monkeypatch.setattr(build_service, "_llm_generate_pages", lambda kb, source_text, llm_model_id: [])

    build_service.build_from_material(material, llm_model_id=1)

    assert seen["text"] == "# Full Markdown\n\ncritical detail"


@pytest.mark.django_db
def test_build_from_material_extracts_facts_from_entire_long_markdown(monkeypatch):
    from apps.opspilot.models import KnowledgePage, Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(
        knowledge_base=kb,
        name="m",
        material_type="text",
        text_content="raw",
    )
    tail_marker = "TAIL_COMPONENT_NEEDS_PAGE"
    long_markdown = ("head content\n" * 900) + f"\n{tail_marker} 是长文档后半段的重要组件。"
    prompts = []

    def fake_invoke(llm_model_id, prompt):
        prompts.append(prompt)
        if "知识抽取助手" in prompt:
            return "尾部组件事实" if tail_marker in prompt else "头部事实"
        if "企业知识库构建助手" in prompt and "尾部组件事实" in prompt:
            return '{"pages":[{"page_type":"entity","title":"TAIL_COMPONENT_NEEDS_PAGE","tags":["tail"],"body":"尾部组件正文"}]}'
        return '{"pages":[]}'

    monkeypatch.setattr(build_service, "load_parsed_markdown", lambda m: long_markdown)
    monkeypatch.setattr(build_service, "_invoke_llm", fake_invoke)

    record = build_service.build_from_material(material, llm_model_id=1)

    assert record.counts["new"] == 1
    assert KnowledgePage.objects.filter(knowledge_base=kb, title=tail_marker).exists()
    assert any(tail_marker in prompt for prompt in prompts if "知识抽取助手" in prompt)


@pytest.mark.django_db
def test_generate_pages_prompt_asks_for_granular_entity_pages(monkeypatch):
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    seen = {}

    def fake_invoke(llm_model_id, prompt):
        seen["prompt"] = prompt
        return '{"pages":[]}'

    monkeypatch.setattr(build_service, "_invoke_llm", fake_invoke)

    build_service._llm_generate_pages(kb, "组件表格: CMDB JOB GSE BKDATA", llm_model_id=1)

    assert "独立实体页" in seen["prompt"]
    assert "表格行" in seen["prompt"]


@pytest.mark.django_db
def test_build_no_model_yields_zero_pages():
    from apps.opspilot.models import KnowledgePage, Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", ai_summary="x")
    record = build_service.build_from_material(material, llm_model_id=None)
    assert record.status == "success"
    assert record.counts["new"] == 0
    assert KnowledgePage.objects.filter(knowledge_base=kb).count() == 0


@pytest.mark.django_db
def test_build_from_material_marks_record_failed_and_material_done_on_error(monkeypatch):
    from apps.opspilot.models import BuildRecord, Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="raw")

    monkeypatch.setattr(build_service, "_llm_extract_facts", lambda text, llm_model_id: "facts")

    def raise_generate(kb, source_text, llm_model_id):
        raise RuntimeError("generate failed")

    monkeypatch.setattr(build_service, "_llm_generate_pages", raise_generate)

    with pytest.raises(RuntimeError, match="generate failed"):
        build_service.build_from_material(material, llm_model_id=1)

    record = BuildRecord.objects.get(knowledge_base=kb)
    material.refresh_from_db()
    assert record.status == "failed"
    assert record.stage == "failed"
    assert record.errors == ["generate failed"]
    assert material.status == "done"


@pytest.mark.django_db
class TestBuildViews:
    def test_material_build_action_and_listings(self, api_client):
        from apps.opspilot.models import Material, WikiKnowledgeBase
        from apps.opspilot.services.wiki import build_service

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
        material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", ai_summary="重启服务摘要")

        with (
            patch.object(build_service, "_llm_extract_facts", return_value="facts"),
            patch.object(build_service, "_llm_generate_pages", return_value=_FAKE_PAGES),
        ):
            resp = api_client.post(f"/api/v1/opspilot/wiki_mgmt/material/{material.id}/build/", {}, format="json")
        assert resp.status_code == 200, resp.content
        assert resp.json()["data"]["status"] == "success"

        pages = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/?knowledge_base={kb.id}")
        assert pages.status_code == 200
        titles = [p["title"] for p in pages.json()["data"]["items"]]
        assert "重启服务" in titles

        records = api_client.get(f"/api/v1/opspilot/wiki_mgmt/build_record/?knowledge_base={kb.id}")
        assert records.status_code == 200
        assert records.json()["data"]["count"] == 1
        assert len(records.json()["data"]["items"]) == 1

    def test_build_record_detail_includes_ordered_affected_page_details(self, api_client):
        from apps.opspilot.models import BuildRecord, KnowledgePage, WikiKnowledgeBase

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
        first = KnowledgePage.objects.create(
            knowledge_base=kb,
            page_type="concept",
            title="蓝鲸平台概述",
            status="active",
        )
        second = KnowledgePage.objects.create(
            knowledge_base=kb,
            page_type="entity",
            title="作业平台",
            status="source_invalid",
        )
        record = BuildRecord.objects.create(
            knowledge_base=kb,
            trigger="material",
            stage="done",
            status="success",
            affected_pages=[second.id, 999999, first.id],
        )

        resp = api_client.get(f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/")

        assert resp.status_code == 200, resp.content
        data = resp.json()["data"]
        assert data["affected_pages"] == [second.id, 999999, first.id]
        assert data["affected_page_details"] == [
            {
                "id": second.id,
                "title": "作业平台",
                "page_type": "entity",
                "status": "source_invalid",
            },
            {
                "id": first.id,
                "title": "蓝鲸平台概述",
                "page_type": "concept",
                "status": "active",
            },
        ]


def _decision_material(kb, name, content_hash):
    from apps.opspilot.models import Material, MaterialVersion

    material = Material.objects.create(
        knowledge_base=kb,
        name=name,
        material_type="text",
        text_content=f"source-{name}",
        content_hash=content_hash,
    )
    version = MaterialVersion.objects.create(material=material, content_hash=content_hash)
    material.current_version = version
    material.save(update_fields=["current_version", "updated_at"])
    return material, version


def _decision_page(kb, material, material_version, body="knowledge-a"):
    from apps.opspilot.models import KnowledgePage, PageEvidence, PageVersion

    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        page_type="concept",
        title="共享知识",
        contribution="human",
    )
    version = PageVersion.objects.create(
        page=page,
        no=1,
        body=body,
        change_type="human_edit",
        is_current=True,
    )
    page.current_version = version
    page.save(update_fields=["current_version", "updated_at"])
    PageEvidence.objects.create(
        page=page,
        material=material,
        material_version=material_version,
    )
    return page


def _mock_decision_build_pages(monkeypatch, build_service, bodies):
    monkeypatch.setattr(build_service, "_llm_extract_facts", lambda text, llm_model_id: text)
    monkeypatch.setattr(
        build_service,
        "_llm_generate_pages",
        lambda kb, source_text, llm_model_id: [
            {
                "page_type": "concept",
                "title": "共享知识",
                "tags": [],
                "body": bodies[source_text],
            }
        ],
    )


@pytest.mark.django_db
def test_build_replays_approved_full_source_set_when_incoming_role_reverses(monkeypatch):
    from apps.opspilot.models import CheckItem, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.check_service import decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb-decision-build", team=[1], schema_md="# schema")
    material_a, version_a = _decision_material(kb, "A", "hash-a")
    material_b, version_b = _decision_material(kb, "B", "hash-b")
    page = _decision_page(kb, material_a, version_a)
    _mock_decision_build_pages(
        monkeypatch,
        build_service,
        {"source-A": "knowledge-a", "source-B": "knowledge-b"},
    )

    first = build_service.build_from_material(material_b, llm_model_id=1, operator="admin")
    check = CheckItem.objects.get(knowledge_base=kb, check_type="cannot_merge", status="open")

    assert first.counts["pending_review"] == 1
    assert {(item["material_id"], item["content_hash"]) for item in check.decision_context["participants"]} == {
        (material_a.id, version_a.content_hash),
        (material_b.id, version_b.content_hash),
    }
    assert check.decision_context["incoming"] == {
        "material_id": material_b.id,
        "material_version_id": version_b.id,
        "content_hash": version_b.content_hash,
    }

    rule = decide_check(check, "use_new", operator="admin")
    version_count = PageVersion.objects.filter(page=page).count()
    second = build_service.build_from_material(material_a, llm_model_id=1, operator="admin")

    assert second.counts == {"new": 0, "updated": 0, "unchanged": 1, "pending_review": 0}
    assert not CheckItem.objects.filter(knowledge_base=kb, status="open").exists()
    assert PageVersion.objects.filter(page=page).count() == version_count
    action = second.inputs["source_trace"]["page_actions"][0]
    assert action["decision_reused"] is True
    assert action["rule_id"] == rule.id
    assert action["action"] == "use_new"


@pytest.mark.django_db
def test_build_same_candidate_body_is_unchanged_without_candidate(monkeypatch):
    from apps.opspilot.models import CheckItem, PageEvidence, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb-build-same-body", team=[1], schema_md="# schema")
    material_a, version_a = _decision_material(kb, "A", "hash-a")
    material_b, version_b = _decision_material(kb, "B", "hash-b")
    page = _decision_page(kb, material_a, version_a, body="same body")
    _mock_decision_build_pages(
        monkeypatch,
        build_service,
        {"source-A": "same body", "source-B": "same body"},
    )

    build = build_service.build_from_material(material_b, llm_model_id=1)

    assert build.counts == {"new": 0, "updated": 0, "unchanged": 1, "pending_review": 0}
    assert not CheckItem.objects.filter(knowledge_base=kb).exists()
    assert PageVersion.objects.filter(page=page).count() == 1
    evidence = PageEvidence.objects.get(page=page, material=material_b)
    assert evidence.material_version_id == version_b.id
    locator = json.loads(evidence.locator)
    assert locator["material_version_id"] == version_b.id
    assert locator["kind"] == "material_chunk"

    repeated = build_service.build_from_material(material_b, llm_model_id=1)

    evidence.refresh_from_db()
    assert repeated.counts["unchanged"] == 1
    assert PageEvidence.objects.filter(page=page, material=material_b).count() == 1
    assert evidence.material_version_id == version_b.id
    assert json.loads(evidence.locator) == locator


@pytest.mark.django_db
@pytest.mark.parametrize("signature_change", ["content_hash", "source_set", "schema"])
def test_build_changed_decision_signature_requires_new_decision(monkeypatch, signature_change):
    from apps.opspilot.models import CheckItem, PageEvidence, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.check_service import decide_check

    kb = WikiKnowledgeBase.objects.create(
        name=f"kb-build-signature-{signature_change}",
        team=[1],
        schema_md="# schema",
    )
    material_a, version_a = _decision_material(kb, "A", "hash-a")
    material_b, _version_b = _decision_material(kb, "B", "hash-b")
    page = _decision_page(kb, material_a, version_a)
    _mock_decision_build_pages(
        monkeypatch,
        build_service,
        {"source-A": "knowledge-a-changed", "source-B": "knowledge-b"},
    )

    build_service.build_from_material(material_b, llm_model_id=1)
    first_check = CheckItem.objects.get(knowledge_base=kb, status="open")
    decide_check(first_check, "use_new", operator="admin")

    if signature_change == "content_hash":
        from apps.opspilot.models import MaterialVersion

        new_version = MaterialVersion.objects.create(material=material_a, content_hash="hash-a-v2")
        material_a.current_version = new_version
        material_a.content_hash = new_version.content_hash
        material_a.save(update_fields=["current_version", "content_hash", "updated_at"])
    elif signature_change == "source_set":
        material_c, version_c = _decision_material(kb, "C", "hash-c")
        PageEvidence.objects.create(
            page=page,
            material=material_c,
            material_version=version_c,
        )
    else:
        kb.schema_md = "# changed schema"
        kb.save(update_fields=["schema_md", "updated_at"])

    build = build_service.build_from_material(material_a, llm_model_id=1)

    assert build.counts["pending_review"] == 1
    assert CheckItem.objects.filter(knowledge_base=kb, status="open").count() == 1


@pytest.mark.django_db
def test_build_alias_subject_replays_canonical_rule(monkeypatch):
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.check_service import decide_check

    canonical = "配置平台"
    kb = WikiKnowledgeBase.objects.create(name="kb-build-alias-replay", team=[1], schema_md="# schema")
    material_a, version_a = _decision_material(kb, "A", "hash-a")
    material_b, _version_b = _decision_material(kb, "B", "hash-b")
    page = _decision_page(kb, material_a, version_a)
    page.title = "CMDB"
    page.save(update_fields=["title", "updated_at"])
    monkeypatch.setattr(build_service, "_llm_extract_facts", lambda text, llm_model_id: text)
    monkeypatch.setattr(
        build_service,
        "_llm_generate_pages",
        lambda kb, source_text, llm_model_id: [
            {
                "page_type": "concept",
                "title": canonical,
                "tags": [],
                "body": "candidate body",
            }
        ],
    )

    first = build_service.build_from_material(material_b, llm_model_id=1)
    check = CheckItem.objects.get(knowledge_base=kb, status="open")

    assert first.counts["pending_review"] == 1
    assert check.decision_context["subject_key"] == f"page::concept::{canonical}"
    rule = decide_check(check, "keep_current", operator="admin")

    second = build_service.build_from_material(material_b, llm_model_id=1)

    assert second.counts["pending_review"] == 0
    assert second.counts["unchanged"] == 1
    assert not CheckItem.objects.filter(knowledge_base=kb, status="open").exists()
    trace = second.inputs["source_trace"]["page_actions"][0]
    assert trace["decision_reused"] is True
    assert trace["rule_id"] == rule.id


@pytest.mark.django_db
def test_build_stale_page_instance_does_not_replay_after_manual_edit(monkeypatch):
    from apps.opspilot.models import CheckItem, KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.check_service import decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb-build-stale-page", team=[1], schema_md="# schema")
    material_a, version_a = _decision_material(kb, "A", "hash-a")
    material_b, _version_b = _decision_material(kb, "B", "hash-b")
    page = _decision_page(kb, material_a, version_a, body="approved current")
    _mock_decision_build_pages(
        monkeypatch,
        build_service,
        {"source-A": "approved current", "source-B": "candidate body"},
    )

    build_service.build_from_material(material_b, llm_model_id=1)
    first_check = CheckItem.objects.get(knowledge_base=kb, status="open")
    rule = decide_check(first_check, "keep_current", operator="admin")
    original_resolve = build_service.resolve_knowledge_conflict
    edited = {}

    def edit_before_resolve(stale_page, *args, **kwargs):
        if not edited:
            stale_current_id = stale_page.current_version_id
            stale_page.page_versions.filter(is_current=True).update(is_current=False)
            latest = stale_page.page_versions.order_by("-no").first()
            manual_version = PageVersion.objects.create(
                page_id=stale_page.id,
                no=latest.no + 1,
                body="manual edit after approval",
                change_type="human_edit",
                is_current=True,
            )
            KnowledgePage.objects.filter(pk=stale_page.id).update(current_version=manual_version)
            edited.update(
                {
                    "manual_version_id": manual_version.id,
                    "stale_current_id": stale_current_id,
                }
            )
        return original_resolve(stale_page, *args, **kwargs)

    monkeypatch.setattr(build_service, "resolve_knowledge_conflict", edit_before_resolve)

    second = build_service.build_from_material(material_b, llm_model_id=1)

    new_check = CheckItem.objects.get(knowledge_base=kb, status="open")
    page.refresh_from_db()
    rule.refresh_from_db()
    assert edited["stale_current_id"] != edited["manual_version_id"]
    assert page.current_version_id == edited["manual_version_id"]
    assert page.current_version.body == "manual edit after approval"
    assert second.counts["pending_review"] == 1
    assert second.counts["unchanged"] == 0
    assert new_check.decision_context["locked_current_version_id"] == edited["manual_version_id"]
    assert not second.inputs["source_trace"]["page_actions"][0].get("decision_reused")
    assert rule.replay_count == 0
