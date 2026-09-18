import json

import pytest

from apps.opspilot.services.wiki.colloquial_alias_service import (
    COLLOQUIAL_ALIAS_CONTRACT,
    GenerationAliasEnrichmentError,
    build_alias_enrich_prompt,
    enrich_generation_colloquial_aliases,
    enrich_generation_colloquial_aliases_safely,
    ground_aliases,
    parse_alias_payload,
    seed_aliases_from_tags,
)


def test_seed_aliases_from_tags_skips_okf_system_tags():
    assert seed_aliases_from_tags(["远程控制", "okf:Metric", "okf:human_reviewed", " 向日葵 "]) == [
        "远程控制",
        "向日葵",
    ]


def test_ground_aliases_keeps_grounded_and_explicit_tags():
    aliases = ground_aliases(
        ["向日葵", "编造的产品X", "远程控制"],
        title="远程协助",
        tags=["远程控制", "okf:Metric"],
        body="员工常用向日葵连过去。",
        always_keep=seed_aliases_from_tags(["远程控制", "okf:Metric"]),
    )
    assert aliases == ["远程控制", "向日葵"]


def test_parse_alias_payload_accepts_pages_and_flat_shapes():
    assert parse_alias_payload('{"pages":[{"page_id":"12","aliases":["向日葵"," "]}]}') == {12: ["向日葵"]}
    assert parse_alias_payload('前言{"aliases":["提单"]}后缀') == {None: ["提单"]}
    assert parse_alias_payload("not json") == {}


def test_build_alias_enrich_prompt_includes_contract():
    prompt = build_alias_enrich_prompt([{"page_id": 1, "title": "远程协助", "tags": ["远程"], "excerpt": "向日葵"}])
    assert COLLOQUIAL_ALIAS_CONTRACT in prompt
    assert "报错原句" in prompt
    assert "员工会怎么描述" in prompt
    assert '"page_id": 1' in prompt


@pytest.mark.django_db
def test_enrich_safely_swallows_missing_generation():
    result = enrich_generation_colloquial_aliases_safely(0, [1])
    assert result["status"] == "skipped"
    assert result["llm_called"] is False


@pytest.mark.django_db(transaction=True)
def test_enrich_generation_colloquial_aliases_writes_grounded_llm_output(wiki_factory, monkeypatch):
    from apps.opspilot.models import BuildRecord, WikiDirectory, WikiGenerationPage
    from apps.opspilot.services.wiki.build_generation_service import begin_build_generation, stage_ai_page
    from apps.opspilot.services.wiki.structure_service import UNCLASSIFIED_DIRECTORY_KEY

    knowledge_base = wiki_factory.bootstrapped_knowledge_base()
    build = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="markdown_import",
        stage="generating",
        status="running",
    )
    context = begin_build_generation(
        knowledge_base,
        build,
        source_fingerprints=[{"archive_sha256": "alias-test"}],
        operator="admin",
    )
    directory = WikiDirectory.objects.get(
        knowledge_base=knowledge_base,
        key=UNCLASSIFIED_DIRECTORY_KEY,
        status="active",
    )
    staged = stage_ai_page(
        context,
        title="远程协助",
        page_type="concept",
        tags=["远程控制", "okf:Metric"],
        body="员工常用向日葵连过去，提单找谁批。",
        directory_id=directory.pk,
        assignment_mode="auto",
        build_record=build,
        operator="admin",
        update_method="markdown_import",
        change_type="markdown_import",
        body_strategy="replace",
    )
    calls = []

    def fake_invoke(_model_id, prompt, **_kwargs):
        calls.append(prompt)
        return json.dumps(
            {
                "pages": [
                    {
                        "page_id": staged.page_id,
                        "aliases": ["向日葵", "提单", "不存在的系统"],
                    }
                ]
            }
        )

    logs = []

    def fake_info(message, *args):
        logs.append((message, args))

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.colloquial_alias_service.logger.info",
        fake_info,
    )
    result = enrich_generation_colloquial_aliases(
        context.candidate_generation_id,
        [staged.page_id],
        llm_model_id=1,
        invoke_llm=fake_invoke,
        llm_when="always",
    )
    assert result["status"] == "ok"
    assert result["llm_called"] is True
    assert calls and COLLOQUIAL_ALIAS_CONTRACT in calls[0]
    assert logs
    template, args = logs[-1]
    assert template == ("wiki colloquial alias enrich completed generation_id=%s updated=%s llm_pages=%s skipped=%s llm_called=%s used_tokens=%s")
    assert args == (context.candidate_generation_id, 1, 1, 0, True, 0)
    assert "generation_id=%s" in template
    formatted = template % args
    assert f"generation_id={context.candidate_generation_id}" in formatted
    assert "updated=1" in formatted
    assert "llm_called=True" in formatted

    member = WikiGenerationPage.objects.select_related("page_version").get(
        generation_id=context.candidate_generation_id,
        page_id=staged.page_id,
    )
    aliases = member.page_display_snapshot.get("aliases") or []
    assert "向日葵" in aliases
    assert "提单" in aliases
    assert "远程控制" in aliases
    assert "不存在的系统" not in aliases
    assert "okf:Metric" not in aliases
    assert member.page_version.meta_snapshot.get("aliases") == aliases


@pytest.mark.django_db(transaction=True)
def test_enrich_if_empty_skips_llm_when_tags_already_seeded(wiki_factory):
    from apps.opspilot.models import BuildRecord, WikiDirectory
    from apps.opspilot.services.wiki.build_generation_service import begin_build_generation, stage_ai_page
    from apps.opspilot.services.wiki.structure_service import UNCLASSIFIED_DIRECTORY_KEY

    knowledge_base = wiki_factory.bootstrapped_knowledge_base()
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
    directory = WikiDirectory.objects.get(
        knowledge_base=knowledge_base,
        key=UNCLASSIFIED_DIRECTORY_KEY,
        status="active",
    )
    staged = stage_ai_page(
        context,
        title="远程协助",
        page_type="concept",
        tags=["远程控制"],
        body="正文",
        directory_id=directory.pk,
        assignment_mode="auto",
        build_record=build,
        operator="admin",
        body_strategy="replace",
    )

    def fail_invoke(*_args, **_kwargs):
        raise AssertionError("llm_when=if_empty must not call LLM after tag seed")

    result = enrich_generation_colloquial_aliases(
        context.candidate_generation_id,
        [staged.page_id],
        llm_model_id=1,
        invoke_llm=fail_invoke,
        llm_when="if_empty",
    )
    assert result["llm_called"] is False
    assert result["updated"] == 1


@pytest.mark.django_db
def test_enrich_missing_generation_raises():
    with pytest.raises(GenerationAliasEnrichmentError) as exc:
        enrich_generation_colloquial_aliases(0, [1])
    assert exc.value.code == "generation_not_found"
