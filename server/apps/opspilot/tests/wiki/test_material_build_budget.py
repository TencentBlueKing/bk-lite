from types import SimpleNamespace

import pytest


def test_llm_call_budget_usage_summary_aggregates_provider_and_estimate():
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    budget = LLMCallBudget(
        max_calls=8,
        max_total_tokens=None,
        soft_total_tokens=60000,
        scope="wiki_material:16",
    )
    first = budget.ensure_call("material_generate", "prompt-a", output_reserve=100)
    budget.record_call(
        first,
        "ignored",
        provider_usage={"prompt_tokens": 120, "completion_tokens": 40},
    )
    second = budget.ensure_call("material_generate_retry_2", "prompt-b", output_reserve=50)
    budget.record_call(second, "abcd")

    summary = budget.usage_summary()
    assert summary["used_calls"] == 2
    assert summary["input_tokens"] == 120 + second.input_tokens
    assert summary["output_tokens"] == 40 + second.output_tokens
    assert summary["used_tokens"] == summary["input_tokens"] + summary["output_tokens"]
    assert summary["provider_calls"] == 1
    assert summary["estimate_calls"] == 1
    assert summary["soft_total_tokens"] == 60000
    assert "material_generate:in=120,out=40,src=provider" in summary["stages"]
    assert "src=estimate" in summary["stages"]


def test_log_material_build_token_usage_emits_searchable_line(monkeypatch):
    from apps.opspilot.services.wiki import generation_material_build_service
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    messages = []

    def fake_info(message, *args):
        messages.append(message % args if args else message)

    monkeypatch.setattr(generation_material_build_service.logger, "info", fake_info)

    budget = LLMCallBudget(
        max_calls=4,
        max_total_tokens=None,
        soft_total_tokens=60000,
        scope="wiki_material:16",
    )
    reservation = budget.ensure_call("material_generate", "hello", output_reserve=10)
    budget.record_call(
        reservation,
        "world",
        provider_usage={"prompt_tokens": 11, "completion_tokens": 7},
    )

    generation_material_build_service._log_material_build_token_usage(
        material=SimpleNamespace(pk=16, knowledge_base=SimpleNamespace(pk=3)),
        build=SimpleNamespace(pk=33, knowledge_base_id=3),
        budget=budget,
        status="success",
        llm_model_id=9,
    )

    assert len(messages) == 1
    line = messages[0]
    assert "wiki_build_token_usage" in line
    assert "material=16" in line
    assert "build=33" in line
    assert "kb=3" in line
    assert "status=success" in line
    assert "model_id=9" in line
    assert "used_calls=1" in line
    assert "used_tokens=18" in line
    assert "input_tokens=11" in line
    assert "output_tokens=7" in line


def test_budgeted_generation_rebalances_five_raw_chunks_into_four_map_calls(monkeypatch):
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.text_utils import split_text_for_llm
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    tail_marker = "TAIL_FACT_MUST_SURVIVE"
    source = ("文" * (32466 - len(tail_marker))) + tail_marker
    assert len(split_text_for_llm(source)) == 5

    calls = []

    def fake_invoke(_model_id, prompt, *, budget, stage, output_reserve):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        result = '{"pages":[]}' if stage == "material_reduce_generate" else '{"facts":[]}'
        budget.record_call(reservation, result)
        calls.append((stage, prompt))
        return result

    monkeypatch.setattr(build_service, "_invoke_llm", fake_invoke)
    budget = LLMCallBudget(
        max_calls=6,
        max_total_tokens=60000,
        scope="wiki_material:test",
    )
    knowledge_base = SimpleNamespace(purpose_md="", schema_md="")
    structure_revision = SimpleNamespace(
        pk=1,
        revision_no=1,
        fingerprint="structure-v1",
        structure_snapshot={"directories": []},
    )

    pages = build_service.generate_material_pages_with_budget(
        knowledge_base,
        source,
        1,
        budget=budget,
        structure_revision=structure_revision,
    )

    map_calls = [item for item in calls if item[0].startswith("material_map_")]
    assert pages == []
    assert len(map_calls) == 4
    assert [item[0] for item in calls] == [
        "material_map_1",
        "material_map_2",
        "material_map_3",
        "material_map_4",
        "material_reduce_generate",
    ]
    assert tail_marker in map_calls[-1][1]
    assert budget.used_calls == 5
    assert budget.used_tokens <= budget.max_total_tokens


def test_bounded_map_planner_skips_tiny_chunk_plan_for_large_source(monkeypatch):
    from apps.opspilot.services.wiki import text_utils

    calls = []
    real_split = text_utils.split_text_for_llm

    def tracking_split(text, max_chars, overlap_chars):
        calls.append(max_chars)
        return real_split(
            text,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )

    monkeypatch.setattr(text_utils, "split_text_for_llm", tracking_split)
    chunks = text_utils.plan_bounded_map_chunks(
        "x" * (text_utils.LLM_CHUNK_CHARS * 4 + 1),
        max_chunks=4,
    )

    assert len(chunks) <= 4
    assert calls[0] > text_utils.LLM_CHUNK_CHARS


@pytest.mark.django_db(transaction=True)
def test_build_task_returns_budget_exhausted_record_instead_of_raising(
    monkeypatch,
    wiki_factory,
):
    from apps.opspilot.models import BuildRecord, Material, MaterialVersion
    from apps.opspilot.services.wiki.build_generation_service import freeze_generation_identity
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded
    from apps.opspilot.tasks import wiki_build_material_task

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    material = Material.objects.create(
        knowledge_base=knowledge_base,
        name="oversized.md",
        material_type="text",
        text_content="content",
        source_identity="text:oversized.md",
        content_hash="a" * 64,
        status="done",
    )
    version = MaterialVersion.objects.create(
        material=material,
        content_hash=material.content_hash,
    )
    material.current_version = version
    material.save(update_fields=["current_version", "updated_at"])
    knowledge_base.refresh_from_db()
    task_identity = freeze_generation_identity(knowledge_base, [material])

    def fail_with_persisted_budget_result(item, build, **_kwargs):
        build.stage = "budget_exhausted"
        build.status = "budget_exhausted"
        build.progress = 100
        build.errors = [
            {
                "code": "wiki_token_budget_exceeded",
                "message": "预算不足",
                "details": {},
            }
        ]
        build.save(
            update_fields=[
                "stage",
                "status",
                "progress",
                "errors",
                "updated_at",
            ]
        )
        item.status = "done"
        item.save(update_fields=["status", "updated_at"])
        raise WikiBudgetExceeded(
            "wiki_token_budget_exceeded",
            "预算不足",
        )

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_material_build_service.build_material_with_generation",
        fail_with_persisted_budget_result,
    )

    build_id = wiki_build_material_task.run(
        material.pk,
        operator="admin",
        task_identity=task_identity,
    )

    build = BuildRecord.objects.get(pk=build_id)
    material.refresh_from_db()
    assert build.status == "budget_exhausted"
    assert build.stage == "budget_exhausted"
    assert build.progress == 100
    assert material.status == "build_failed"


@pytest.mark.django_db(transaction=True)
def test_budget_exhaustion_persists_complete_precise_terminal_state(
    monkeypatch,
    wiki_factory,
):
    from apps.opspilot.models import BuildRecord, MaterialVersion, WikiGeneration
    from apps.opspilot.services.wiki import generation_material_build_service
    from apps.opspilot.services.wiki.build_generation_service import freeze_generation_identity
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    material = wiki_factory.material(
        knowledge_base=knowledge_base,
        source_identity="text:budget.md",
        content_hash="b" * 64,
        status="done",
    )
    version = MaterialVersion.objects.create(
        material=material,
        content_hash=material.content_hash,
    )
    material.current_version = version
    material.save(update_fields=["current_version", "updated_at"])
    knowledge_base.refresh_from_db()
    active_generation_id = knowledge_base.active_generation_id
    task_identity = freeze_generation_identity(knowledge_base, [material])
    build = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="material",
        operator="admin",
        stage="generating",
        status="running",
    )

    monkeypatch.setattr(
        generation_material_build_service,
        "load_parsed_markdown",
        lambda _material: "source",
    )

    def reject_budget(*_args, **_kwargs):
        raise WikiBudgetExceeded(
            "wiki_token_budget_exceeded",
            "Wiki token 预算不足以执行下一阶段",
            details={"next_stage": "material_map_2"},
        )

    monkeypatch.setattr(
        generation_material_build_service,
        "generate_material_pages_with_budget",
        reject_budget,
    )

    with pytest.raises(WikiBudgetExceeded):
        generation_material_build_service.build_material_with_generation(
            material,
            build,
            llm_model_id=1,
            operator="admin",
            frozen_identity=task_identity,
        )

    knowledge_base.refresh_from_db()
    material.refresh_from_db()
    build.refresh_from_db()
    candidate = WikiGeneration.objects.get(pk=build.generation_id)
    assert build.status == "budget_exhausted"
    assert build.stage == "budget_exhausted"
    assert build.progress == 100
    assert build.activation["code"] == "wiki_token_budget_exceeded"
    assert build.checkpoint["stopped_stage"] == "material_map_2"
    assert candidate.status == "failed"
    assert knowledge_base.active_generation_id == active_generation_id
    assert material.status == "build_failed"
