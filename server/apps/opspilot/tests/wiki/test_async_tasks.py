"""Wiki Celery 任务测试:用 .apply() 同步执行(无需 broker)。"""

import pytest

from apps.opspilot.services.wiki.build_service import MaterialPageGeneration
from apps.opspilot.services.wiki.conflict_candidate_routing_service import ConflictRoutingResult


def _kb(schema="# s"):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1], schema_md=schema, introduction="测试知识库简介")


def _stub_successful_material_generation(monkeypatch):
    def fake_route(*args, **kwargs):
        return ConflictRoutingResult(
            comparisons={},
            compact_candidate_count=0,
            evidence_page_ids=(),
            old_evidence_tokens=0,
            overflow_count=0,
            llm_called=False,
            unresolved_incoming_indexes=(),
        )

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_material_build_service.generate_material_pages_with_budget",
        lambda *args, **kwargs: MaterialPageGeneration(
            pages=[
                {
                    "page_type": "concept",
                    "title": "Generated",
                    "tags": [],
                    "body": "generated body",
                }
            ],
            skipped=[],
        ),
    )
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_material_build_service.route_material_conflicts",
        fake_route,
    )
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_material_build_service.enrich_generation_colloquial_aliases_safely",
        lambda *args, **kwargs: {"status": "skipped", "updated": 0, "llm_called": False},
    )
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_navigation_service.enhance_generation_overviews",
        lambda *args, **kwargs: {"status": "skipped", "updated": 0, "llm_called": False},
    )


def _material(kb, **overrides):
    from apps.opspilot.tests.wiki.factories import WikiFactory

    return WikiFactory().ready_material(knowledge_base=kb, **overrides)


@pytest.mark.django_db
def test_build_task_creates_build_record():
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.tasks import wiki_build_material_task

    kb = _kb()
    mat = _material(kb)
    # 无 llm_model → 0 页，构建失败落库，资料标 build_failed。
    rid = wiki_build_material_task.apply(args=[mat.id], kwargs={"ensure_parsed": True}).get()
    assert rid is not None
    rec = BuildRecord.objects.get(id=rid)
    mat.refresh_from_db()
    assert rec.trigger == "material" and rec.status == "failed"
    assert rec.stage == "failed"
    assert mat.status == "build_failed"


@pytest.mark.django_db
def test_build_task_missing_material_returns_none():
    from apps.opspilot.tasks import wiki_build_material_task

    assert wiki_build_material_task.apply(args=[999999]).get() is None


@pytest.mark.django_db
def test_ingest_task_parses_and_sets_status_done(monkeypatch):
    """异步解析任务:抽取 + 摘要后,资料状态机置「已解析」done。"""
    from apps.opspilot.models import Material  # noqa: F401
    from apps.opspilot.services.wiki import material_service
    from apps.opspilot.tasks import wiki_ingest_material_task

    class Parser:
        def parse_text(self, text, *, filename="raw.txt"):
            return text

    monkeypatch.setattr(material_service, "get_parser", lambda: Parser())
    monkeypatch.setattr(material_service, "save_parsed_markdown", lambda material, md, digest: "wiki/parsed/task.md")

    kb = _kb()
    mat = _material(kb)  # text 资料,正文 "facts"
    mid = wiki_ingest_material_task.apply(args=[mat.id]).get()
    assert mid == mat.id
    mat.refresh_from_db()
    assert mat.status == "done" and mat.ai_summary  # 无模型回退为截断正文


@pytest.mark.django_db
def test_ingest_task_missing_material_returns_none():
    from apps.opspilot.tasks import wiki_ingest_material_task

    assert wiki_ingest_material_task.apply(args=[999999]).get() is None


@pytest.mark.django_db
def test_build_success_sets_material_status_built(monkeypatch):
    """状态机:构建成功 → 资料状态置「已构建」built。"""
    from apps.opspilot.tasks import wiki_build_material_task

    _stub_successful_material_generation(monkeypatch)
    kb = _kb()
    mat = _material(kb)
    wiki_build_material_task.apply(args=[mat.id], kwargs={"ensure_parsed": True}).get()
    mat.refresh_from_db()
    assert mat.status == "built"


@pytest.mark.django_db
def test_rebuild_task_creates_record():
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki.build_generation_service import freeze_generation_identity
    from apps.opspilot.tasks import wiki_rebuild_kb_task

    kb = _kb()
    identity = freeze_generation_identity(kb, [])
    rid = wiki_rebuild_kb_task.apply(args=[kb.id], kwargs={"task_identity": identity}).get()
    rec = BuildRecord.objects.get(id=rid)
    assert rec.trigger == "rebuild" and rec.status == "success"


@pytest.mark.django_db
def test_propose_update_task_missing_returns_none():
    from apps.opspilot.tasks import wiki_propose_update_task

    assert wiki_propose_update_task.apply(args=[999999]).get() is None


@pytest.mark.django_db
def test_async_entrypoints_delegate_to_sync_services_with_same_context(monkeypatch):
    from types import SimpleNamespace

    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki import rebuild_service, update_service
    from apps.opspilot.services.wiki.build_generation_service import freeze_generation_identity
    from apps.opspilot.tasks import wiki_build_material_task, wiki_propose_update_task, wiki_rebuild_kb_task

    kb = _kb()
    material = _material(kb)
    identity = freeze_generation_identity(kb, [material])
    rebuild_record = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="rebuild",
        status="running",
        stage="queued",
    )
    calls = {}

    def fake_build(item, build, llm_model_id=None, operator="", **_kwargs):
        calls["build"] = (item.id, llm_model_id, operator)
        return SimpleNamespace(id=101)

    def fake_update(item, llm_model_id=None, operator="", **_kwargs):
        calls["update"] = (item.id, llm_model_id, operator)
        return SimpleNamespace(id=102)

    def fake_rebuild(knowledge_base, llm_model_id=None, operator="", build=None, **_kwargs):
        calls["rebuild"] = (
            knowledge_base.id,
            llm_model_id,
            operator,
            build.id if build else None,
        )
        return SimpleNamespace(id=103)

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_material_build_service.build_material_with_generation",
        fake_build,
    )
    monkeypatch.setattr(update_service, "propose_update", fake_update)
    monkeypatch.setattr(rebuild_service, "rebuild_knowledge_base_with_generation", fake_rebuild)

    assert (
        wiki_build_material_task.run(
            material.id,
            llm_model_id=7,
            operator="alice",
            task_identity=identity,
        )
        == 101
    )
    assert (
        wiki_propose_update_task.run(
            material.id,
            llm_model_id=8,
            operator="bob",
            task_identity=identity,
        )
        == 102
    )
    assert (
        wiki_rebuild_kb_task.run(
            kb.id,
            llm_model_id=9,
            operator="carol",
            build_record_id=rebuild_record.id,
            task_identity=identity,
        )
        == 103
    )
    assert calls == {
        "build": (material.id, 7, "alice"),
        "update": (material.id, 8, "bob"),
        "rebuild": (kb.id, 9, "carol", rebuild_record.id),
    }


@pytest.mark.django_db
def test_refresh_web_materials_task(monkeypatch):
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki import material_service
    from apps.opspilot.tasks import wiki_refresh_web_materials_task

    kb = _kb()
    Material.objects.create(
        knowledge_base=kb,
        name="site",
        material_type="web",
        url="http://example.com",
        sync_policy={"enabled": True},
    )

    class Parser:
        def parse_url(self, url, *, vision_client=None):
            return "fresh content"

    monkeypatch.setattr(material_service, "get_parser", lambda: Parser())
    monkeypatch.setattr(
        material_service,
        "save_parsed_markdown",
        lambda material, md, digest: "wiki/parsed/web-refresh.md",
    )

    result = wiki_refresh_web_materials_task.apply().get()
    assert result["checked"] == 1 and result["updated"] == 1
