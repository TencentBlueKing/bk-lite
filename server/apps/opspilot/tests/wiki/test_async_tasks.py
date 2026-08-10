"""Wiki Celery 任务测试:用 .apply() 同步执行(无需 broker)。"""

import pytest


def _kb(schema="# s"):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1], schema_md=schema)


def _material(kb):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="facts")


@pytest.mark.django_db
def test_build_task_creates_build_record():
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.tasks import wiki_build_material_task

    kb = _kb()
    mat = _material(kb)
    # 无 llm_model -> 生成 0 页,按 2576af62a 行为标 partial(非 success),
    # build 记录仍成功落库,可追溯"模型未配"问题。
    rid = wiki_build_material_task.apply(args=[mat.id]).get()
    assert rid is not None
    rec = BuildRecord.objects.get(id=rid)
    assert rec.trigger == "material" and rec.status == "partial"


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
def test_build_success_sets_material_status_built():
    """状态机:构建成功 → 资料状态置「已构建」built。"""
    from apps.opspilot.tasks import wiki_build_material_task

    kb = _kb()
    mat = _material(kb)
    wiki_build_material_task.apply(args=[mat.id]).get()
    mat.refresh_from_db()
    assert mat.status == "built"


@pytest.mark.django_db
def test_rebuild_task_creates_record():
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.tasks import wiki_rebuild_kb_task

    kb = _kb()
    rid = wiki_rebuild_kb_task.apply(args=[kb.id]).get()
    assert BuildRecord.objects.filter(id=rid, trigger="rebuild", status="success").exists()


@pytest.mark.django_db
def test_propose_update_task_missing_returns_none():
    from apps.opspilot.tasks import wiki_propose_update_task

    assert wiki_propose_update_task.apply(args=[999999]).get() is None


@pytest.mark.django_db
def test_async_entrypoints_delegate_to_sync_services_with_same_context(monkeypatch):
    from types import SimpleNamespace

    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki import build_service, rebuild_service, update_service
    from apps.opspilot.tasks import wiki_build_material_task, wiki_propose_update_task, wiki_rebuild_kb_task

    kb = _kb()
    material = _material(kb)
    rebuild_record = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="rebuild",
        status="running",
        stage="queued",
    )
    calls = {}

    def fake_build(item, llm_model_id=None, operator=""):
        calls["build"] = (item.id, llm_model_id, operator)
        return SimpleNamespace(id=101)

    def fake_update(item, llm_model_id=None, operator=""):
        calls["update"] = (item.id, llm_model_id, operator)
        return SimpleNamespace(id=102)

    def fake_rebuild(knowledge_base, llm_model_id=None, operator="", build=None):
        calls["rebuild"] = (
            knowledge_base.id,
            llm_model_id,
            operator,
            build.id if build else None,
        )
        return SimpleNamespace(id=103)

    monkeypatch.setattr(build_service, "build_from_material", fake_build)
    monkeypatch.setattr(update_service, "propose_update", fake_update)
    monkeypatch.setattr(rebuild_service, "rebuild_knowledge_base", fake_rebuild)

    assert (
        wiki_build_material_task.run(
            material.id,
            llm_model_id=7,
            operator="alice",
        )
        == 101
    )
    assert (
        wiki_propose_update_task.run(
            material.id,
            llm_model_id=8,
            operator="bob",
        )
        == 102
    )
    assert (
        wiki_rebuild_kb_task.run(
            kb.id,
            llm_model_id=9,
            operator="carol",
            build_record_id=rebuild_record.id,
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
