import json

import pytest


def _kb(schema="# schema"):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1], schema_md=schema)


def _material(kb, name="m"):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name=name, material_type="text", text_content="facts")


def _page(kb, title, contribution):
    from apps.opspilot.models import KnowledgePage, PageVersion

    page = KnowledgePage.objects.create(knowledge_base=kb, page_type="concept", title=title, contribution=contribution)
    v = PageVersion.objects.create(page=page, no=1, body="old", change_type="ai_create", is_current=True)
    page.current_version = v
    page.save(update_fields=["current_version"])
    return page


@pytest.mark.django_db
def test_rebuild_archives_ai_keeps_human_and_regenerates():
    from apps.opspilot.models import CheckItem, KnowledgePage
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    mat = _material(kb)
    ai_page = _page(kb, "OldAI", "ai")
    human_page = _page(kb, "Human", "mixed")

    build = rebuild_knowledge_base(kb, generator=lambda m: [{"page_type": "concept", "title": f"New-{m.name}", "tags": [], "body": "fresh"}])

    ai_page.refresh_from_db()
    human_page.refresh_from_db()
    assert ai_page.status == "archived"  # 旧 AI 页归档
    assert human_page.status == "active"  # 人工页保留
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="schema_changed").exists()  # 人工页待核对

    new_pages = KnowledgePage.objects.filter(knowledge_base=kb, update_method="rebuild", status="active")
    assert new_pages.count() == 1 and new_pages.first().title == f"New-{mat.name}"
    assert build.counts == {"new": 1, "archived": 1, "unchanged": 0, "pending_review": 1}


@pytest.mark.django_db
def test_rebuild_with_no_generated_pages():
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    _material(kb)
    _page(kb, "AI", "ai")

    build = rebuild_knowledge_base(kb, generator=lambda m: [])
    assert build.counts["new"] == 0 and build.counts["archived"] == 1
    assert build.status == "success"


@pytest.mark.django_db
def test_rebuild_default_generator_extracts_facts_before_generating_pages(monkeypatch):
    from apps.opspilot.services.wiki import rebuild_service

    kb = _kb()
    _material(kb)
    seen = {}

    def fake_extract(text, llm_model_id):
        seen["extract_text"] = text
        seen["extract_model"] = llm_model_id
        return "EXTRACTED_FACTS"

    def fake_generate(kb_arg, source_text, llm_model_id):
        seen["generate_text"] = source_text
        seen["generate_model"] = llm_model_id
        return [{"page_type": "concept", "title": "FromFacts", "tags": [], "body": "body"}]

    monkeypatch.setattr(rebuild_service, "load_parsed_markdown", lambda material: "FULL_MARKDOWN")
    monkeypatch.setattr(rebuild_service, "_llm_extract_facts", fake_extract, raising=False)
    monkeypatch.setattr(rebuild_service, "_llm_generate_pages", fake_generate)

    build = rebuild_service.rebuild_knowledge_base(kb, llm_model_id=123)

    assert build.counts["new"] == 1
    assert seen == {
        "extract_text": "FULL_MARKDOWN",
        "extract_model": 123,
        "generate_text": "EXTRACTED_FACTS",
        "generate_model": 123,
    }


@pytest.mark.django_db
def test_rebuild_merges_same_title_generated_from_multiple_materials():
    from apps.opspilot.models import KnowledgePage, PageEvidence
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    first = _material(kb, "first")
    second = _material(kb, "second")

    build = rebuild_knowledge_base(
        kb,
        generator=lambda material: [
            {
                "page_type": "entity",
                "title": "蓝鲸平台",
                "tags": [material.name],
                "body": f"{material.name} body",
            }
        ],
    )

    page = KnowledgePage.objects.get(knowledge_base=kb, title="蓝鲸平台", status="active")
    assert build.counts["new"] == 1
    assert KnowledgePage.objects.filter(knowledge_base=kb, title="蓝鲸平台", status="active").count() == 1
    assert "first body" in page.current_version.body
    assert "second body" in page.current_version.body
    assert PageEvidence.objects.filter(page=page, material__in=[first, second]).count() == 2


@pytest.mark.django_db
def test_rebuild_merges_abbreviation_and_full_name_generated_from_multiple_materials():
    from apps.opspilot.models import KnowledgePage, PageEvidence
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    first = _material(kb, "first")
    second = _material(kb, "second")

    def generator(material):
        title = "CMDB" if material == first else "配置平台"
        return [
            {
                "page_type": "entity",
                "title": title,
                "tags": [material.name],
                "body": f"{title} {material.name} body",
            }
        ]

    build = rebuild_knowledge_base(kb, generator=generator)

    page = KnowledgePage.objects.get(knowledge_base=kb, title="配置平台", status="active")
    assert build.counts["new"] == 1
    assert KnowledgePage.objects.filter(knowledge_base=kb, status="active").count() == 1
    assert not KnowledgePage.objects.filter(knowledge_base=kb, title="CMDB", status="active").exists()
    assert "CMDB first body" in page.current_version.body
    assert "配置平台 second body" in page.current_version.body
    assert PageEvidence.objects.filter(page=page, material__in=[first, second]).count() == 2


@pytest.mark.django_db
def test_rebuild_records_source_chunk_locator_for_generated_page():
    from apps.opspilot.models import PageEvidence
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    marker = "REBUILD_TAIL_COMPONENT"
    material = _material(kb)
    material.text_content = ("head content\n" * 1200) + f"\n{marker} 是全量重建尾部事实。"
    material.save(update_fields=["text_content"])

    rebuild_knowledge_base(
        kb,
        generator=lambda m: [
            {
                "page_type": "entity",
                "title": "尾部组件",
                "tags": [],
                "body": f"{marker} 需要保留片段级来源。",
            }
        ],
    )

    evidence = PageEvidence.objects.get(material=material)
    locator = json.loads(evidence.locator)
    assert locator["kind"] == "material_chunk"
    assert locator["chunk_index"] > 0
    assert locator["chunk_count"] > 1
    assert marker in locator["snippet"]


@pytest.mark.django_db
def test_rebuild_traces_pending_review_and_skips_titleless_page_data():
    from apps.opspilot.models import CheckItem, KnowledgePage
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    _page(kb, "人工页面", "mixed")
    _material(kb, "first")
    _material(kb, "second")

    build = rebuild_knowledge_base(
        kb,
        generator=lambda m: [
            {"page_type": "concept", "title": "", "tags": [], "body": "missing title"},
            {"page_type": "concept", "title": "人工页面", "tags": [], "body": f"{m.name} candidate"},
        ],
    )

    actions = [action["action"] for material_trace in build.inputs["source_trace"]["materials"] for action in material_trace["page_actions"]]
    assert actions == ["pending_review", "unchanged"]
    assert KnowledgePage.objects.filter(knowledge_base=kb, title="", status="active").count() == 0
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="cannot_merge", status="open").count() == 1


@pytest.mark.django_db
class TestRebuildView:
    def test_rebuild_endpoint_enqueues_task_and_returns_running_record(self, api_client, monkeypatch):
        from apps.opspilot import tasks
        from apps.opspilot.models import BuildRecord

        kb = _kb()
        calls = []

        class Task:
            @staticmethod
            def delay(kb_id, llm_model_id, operator, build_record_id):
                calls.append((kb_id, llm_model_id, operator, build_record_id))

        monkeypatch.setattr(tasks, "wiki_rebuild_kb_task", Task)

        r = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/rebuild/", {}, format="json")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["trigger"] == "rebuild"
        assert data["status"] == "running"
        assert data["stage"] == "queued"
        assert BuildRecord.objects.filter(id=data["id"], knowledge_base=kb, status="running").exists()
        assert calls == [(kb.id, kb.llm_model_id, data["operator"], data["id"])]

    def test_rebuild_endpoint_rejects_when_build_running(self, api_client, monkeypatch):
        from apps.opspilot import tasks
        from apps.opspilot.models import BuildRecord

        kb = _kb()
        BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")

        class Task:
            @staticmethod
            def delay(*args, **kwargs):
                pytest.fail("running rebuild should not enqueue another task")

        monkeypatch.setattr(tasks, "wiki_rebuild_kb_task", Task)

        r = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/rebuild/", {}, format="json")
        assert r.status_code == 400
        assert "运行中" in r.json()["message"]
        assert BuildRecord.objects.filter(knowledge_base=kb, status="running").count() == 1

    def test_delete_endpoint_rejects_when_build_running(self, api_client):
        from apps.opspilot.models import BuildRecord, WikiKnowledgeBase

        kb = _kb()
        BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")

        r = api_client.delete(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/")
        assert r.status_code == 400
        assert "运行中" in r.json()["message"]
        assert WikiKnowledgeBase.objects.filter(id=kb.id).exists()

    def test_build_record_list_can_filter_running_status(self, api_client):
        from apps.opspilot.models import BuildRecord

        kb = _kb()
        BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")
        BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="success", stage="done")

        r = api_client.get(f"/api/v1/opspilot/wiki_mgmt/build_record/?knowledge_base={kb.id}&status=running&page_size=1")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["count"] == 1
        assert data["items"][0]["status"] == "running"
