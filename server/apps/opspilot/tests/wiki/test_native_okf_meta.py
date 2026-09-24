import pytest
from django.db import transaction
from django.db.models.query import QuerySet


@pytest.mark.django_db(transaction=True)
def test_stage_ai_page_owns_row_lock_transaction(wiki_factory, monkeypatch):
    """Celery 资料构建在调用方事务外写页；Postgres 要求 select_for_update 必须在 atomic 内。"""

    from apps.opspilot.models import BuildRecord, WikiDirectory
    from apps.opspilot.services.wiki.build_generation_service import begin_build_generation, stage_ai_page
    from apps.opspilot.services.wiki.structure_service import UNCLASSIFIED_DIRECTORY_KEY

    original = QuerySet.select_for_update

    def require_atomic(self, *args, **kwargs):
        if not transaction.get_connection().in_atomic_block:
            raise transaction.TransactionManagementError("select_for_update cannot be used outside of a transaction.")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "select_for_update", require_atomic)

    knowledge_base = wiki_factory.bootstrapped_knowledge_base()
    directory = WikiDirectory.objects.get(
        knowledge_base=knowledge_base,
        key=UNCLASSIFIED_DIRECTORY_KEY,
        status="active",
    )
    build = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="material",
        stage="generating",
        status="running",
    )
    context = begin_build_generation(
        knowledge_base,
        build,
        source_fingerprints=[{"material_id": 1}],
        operator="admin",
    )
    staged = stage_ai_page(
        context,
        title="监控入口",
        page_type="concept",
        tags=["监控"],
        body="先打开监控入口。",
        directory_id=directory.pk,
        assignment_mode="auto",
        build_record=build,
        operator="admin",
    )
    assert staged.action == "create"
    assert staged.page_id


@pytest.mark.django_db
def test_stage_ai_page_writes_native_okf_and_keeps_concept_id(wiki_factory):
    from apps.opspilot.models import BuildRecord, PageVersion, WikiDirectory
    from apps.opspilot.services.wiki.build_generation_service import (
        begin_build_generation,
        finalize_build_generation,
        stage_ai_page,
    )
    from apps.opspilot.services.wiki.okf_export_service import build_okf_export_zip

    knowledge_base = wiki_factory.bootstrapped_knowledge_base()
    entity = WikiDirectory.objects.get(knowledge_base=knowledge_base, key="schema_entity", status="active")
    concept = WikiDirectory.objects.get(knowledge_base=knowledge_base, key="schema_concept", status="active")
    material = wiki_factory.material(knowledge_base=knowledge_base, name="值班手册.pdf")
    build = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="material",
        stage="generating",
        status="running",
    )
    context = begin_build_generation(
        knowledge_base,
        build,
        source_fingerprints=[{"material_id": material.pk}],
        operator="admin",
    )
    staged = stage_ai_page(
        context,
        title="值班入口",
        page_type="entity",
        tags=["值班"],
        body="先打开值班入口。",
        directory_id=entity.pk,
        assignment_mode="auto",
        build_record=build,
        operator="admin",
        navigation_metadata={"summary": "值班入口说明"},
        okf_sources=[{"resource": material.name, "material_id": material.pk}],
    )
    version = PageVersion.objects.get(pk=staged.page_version_id)
    okf = version.meta_snapshot["okf"]
    assert okf["type"] == "entity"
    assert okf["title"] == "值班入口"
    assert okf["description"] == "值班入口说明"
    assert okf["tags"] == ["值班"]
    assert okf["concept_id"].endswith("值班入口")
    assert "实体" in okf["concept_id"]
    assert okf["sources"] == [{"resource": "值班手册.pdf", "material_id": material.pk}]
    assert okf["generated"]["by"]
    assert okf["generated"]["at"]

    moved = stage_ai_page(
        context,
        page_id=staged.page_id,
        title="值班入口改名",
        page_type="entity",
        tags=["值班"],
        body="先打开值班入口。",
        directory_id=concept.pk,
        assignment_mode="manual",
        build_record=build,
        operator="admin",
        navigation_metadata={"summary": "值班入口说明"},
        okf_sources=[{"resource": material.name, "material_id": material.pk}],
    )
    moved_okf = PageVersion.objects.get(pk=moved.page_version_id).meta_snapshot["okf"]
    assert moved_okf["concept_id"] == okf["concept_id"]
    finalize_build_generation(
        context,
        build_record=build,
        page_actions=[
            {
                "page_id": moved.page_id,
                "action": moved.action,
                "title": moved.title,
            }
        ],
        directory_trace=[],
        run_embedding_index=False,
    )
    knowledge_base.refresh_from_db()

    content, stats = build_okf_export_zip(knowledge_base)
    assert stats["pages"] >= 1
    from apps.opspilot.tests.wiki.test_okf_export import _open_okf_zip, _parse_md

    archive, names, root = _open_okf_zip(content)
    with archive:
        page_names = [
            name
            for name in names
            if name.endswith(".md") and not name.endswith(("/index.md", "/log.md"))
        ]
        exported = archive.read(page_names[0]).decode("utf-8")
        meta, _body = _parse_md(exported)
    assert meta["generated"]["by"] == okf["generated"]["by"]
    assert meta["sources"] == okf["sources"]
    assert meta["concept_id"] == okf["concept_id"]
