import pytest


def test_apply_wikilink_suggestions_only_wraps_first_unlinked_occurrence():
    from apps.opspilot.services.wiki.wikilink_enrichment_service import apply_wikilink_suggestions

    body = "蓝鲸平台依赖配置平台。配置平台提供配置能力。已有 [[作业平台]]。"
    links = [
        {"term": "配置平台", "target": "配置平台"},
        {"term": "作业平台", "target": "作业平台"},
        {"term": "不存在", "target": "未知页面"},
    ]

    enriched, count = apply_wikilink_suggestions(
        body,
        links,
        allowed_titles={"配置平台": "配置平台", "作业平台": "作业平台"},
    )

    assert count == 1
    assert enriched == "蓝鲸平台依赖[[配置平台]]。配置平台提供配置能力。已有 [[作业平台]]。"


@pytest.mark.django_db
def test_enrichment_links_existing_title_without_llm():
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.wikilink_enrichment_service import enrich_pages_wikilinks

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    target = KnowledgePage.objects.create(
        knowledge_base=kb,
        page_type="entity",
        title="配置平台",
        contribution="human",
    )
    target_version = PageVersion.objects.create(
        page=target,
        no=1,
        body="配置平台说明",
        change_type="human_edit",
        is_current=True,
    )
    target.current_version = target_version
    target.save(update_fields=["current_version"])
    source = KnowledgePage.objects.create(
        knowledge_base=kb,
        page_type="entity",
        title="蓝鲸平台",
        contribution="ai",
    )
    source_version = PageVersion.objects.create(
        page=source,
        no=1,
        body="蓝鲸平台依赖配置平台提供配置能力。",
        change_type="ai_create",
        is_current=True,
    )
    source.current_version = source_version
    source.save(update_fields=["current_version"])

    def fail_if_called(llm_model_id, prompt):
        pytest.fail("已有页面标题命中时不应调用 LLM 补链")

    enriched_ids = enrich_pages_wikilinks(kb, [source.id], 1, fail_if_called)

    source.refresh_from_db()
    assert enriched_ids == [source.id]
    assert source.current_version.body == "蓝鲸平台依赖[[配置平台]]提供配置能力。"


@pytest.mark.django_db
def test_build_enriches_generated_page_wikilinks_and_rebuilds_reference_relation(monkeypatch):
    from apps.opspilot.models import KnowledgePage, Material, PageRelation, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    target = KnowledgePage.objects.create(
        knowledge_base=kb,
        page_type="entity",
        title="配置平台",
        contribution="human",
    )
    target_version = PageVersion.objects.create(
        page=target,
        no=1,
        body="配置平台说明",
        change_type="human_edit",
        is_current=True,
    )
    target.current_version = target_version
    target.save(update_fields=["current_version"])
    material = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="raw")
    prompts = []

    monkeypatch.setattr(build_service, "_llm_extract_facts", lambda text, llm_model_id: "facts")
    monkeypatch.setattr(
        build_service,
        "_llm_generate_pages",
        lambda kb, source_text, llm_model_id: [
            {
                "page_type": "entity",
                "title": "蓝鲸平台",
                "tags": [],
                "body": "蓝鲸平台依赖配置平台提供配置能力。",
            }
        ],
    )

    def fake_invoke(llm_model_id, prompt):
        prompts.append(prompt)
        return '{"links":[{"term":"配置平台","target":"配置平台"}]}'

    monkeypatch.setattr(build_service, "_invoke_llm", fake_invoke)

    build_service.build_from_material(material, llm_model_id=1)

    source = KnowledgePage.objects.get(knowledge_base=kb, title="蓝鲸平台")
    assert source.current_version.body == "蓝鲸平台依赖[[配置平台]]提供配置能力。"
    assert PageVersion.objects.filter(page=source).count() == 2
    assert PageRelation.objects.filter(from_page=source, to_page=target, relation_type="reference").exists()
    assert prompts == []


@pytest.mark.django_db
def test_rebuild_enriches_generated_page_wikilinks(monkeypatch):
    from apps.opspilot.models import KnowledgePage, Material, PageRelation, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import rebuild_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    target = KnowledgePage.objects.create(
        knowledge_base=kb,
        page_type="entity",
        title="配置平台",
        contribution="human",
    )
    target_version = PageVersion.objects.create(
        page=target,
        no=1,
        body="配置平台说明",
        change_type="human_edit",
        is_current=True,
    )
    target.current_version = target_version
    target.save(update_fields=["current_version"])
    Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="raw")

    monkeypatch.setattr(
        rebuild_service,
        "_invoke_llm",
        lambda llm_model_id, prompt: '{"links":[{"term":"配置平台","target":"配置平台"}]}',
    )

    rebuild_service.rebuild_knowledge_base(
        kb,
        llm_model_id=1,
        generator=lambda m: [
            {
                "page_type": "entity",
                "title": "蓝鲸平台",
                "tags": [],
                "body": "蓝鲸平台依赖配置平台。",
            }
        ],
    )

    source = KnowledgePage.objects.get(knowledge_base=kb, title="蓝鲸平台")
    assert source.current_version.body == "蓝鲸平台依赖[[配置平台]]。"
    assert PageRelation.objects.filter(from_page=source, to_page=target, relation_type="reference").exists()
