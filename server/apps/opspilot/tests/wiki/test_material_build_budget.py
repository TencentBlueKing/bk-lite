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


@pytest.mark.django_db
def test_budgeted_generation_fits_legacy_32k_source_in_one_200k_call(monkeypatch):
    from apps.opspilot.models import LLMModel
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.text_utils import split_text_for_llm
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    tail_marker = "TAIL_FACT_MUST_SURVIVE"
    source = ("文" * (32466 - len(tail_marker))) + tail_marker
    assert len(split_text_for_llm(source)) == 5
    model = LLMModel.objects.create(name="build-200k", model="m")

    calls = []

    def fake_invoke(_model_id, prompt, *, budget, stage, output_reserve, **_kwargs):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        result = '{"pages":[]}'
        budget.record_call(reservation, result)
        calls.append((stage, prompt))
        return result

    monkeypatch.setattr(build_service, "_invoke_llm", fake_invoke)
    result = build_service.generate_material_pages_with_budget(
        SimpleNamespace(purpose_md="", schema_md=""),
        source,
        model.pk,
        budget=LLMCallBudget(max_calls=6, max_total_tokens=60000, scope="wiki_material:test"),
        structure_revision=SimpleNamespace(
            pk=1,
            revision_no=1,
            fingerprint="structure-v1",
            structure_snapshot={"directories": []},
        ),
    )

    assert result.pages == []
    assert result.skipped == []
    assert [item[0] for item in calls] == ["material_generate"]
    assert tail_marker in calls[0][1]


@pytest.mark.django_db
def test_budgeted_generation_maps_when_source_exceeds_8k_input_working(monkeypatch):
    from apps.opspilot.models import LLMModel
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    tail_marker = "TAIL_FACT_MUST_SURVIVE"
    source = ("文" * (12000 - len(tail_marker))) + tail_marker
    model = LLMModel.objects.create(name="build-8k", model="m", context_window_tokens=8_000)
    calls = []

    def fake_invoke(_model_id, prompt, *, budget, stage, output_reserve, **_kwargs):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        result = '{"pages":[]}' if stage == "material_reduce_generate" else '{"facts":[]}'
        budget.record_call(reservation, result)
        calls.append((stage, prompt))
        return result

    monkeypatch.setattr(build_service, "_invoke_llm", fake_invoke)
    result = build_service.generate_material_pages_with_budget(
        SimpleNamespace(purpose_md="", schema_md=""),
        source,
        model.pk,
        budget=LLMCallBudget(max_calls=32, max_total_tokens=None, scope="wiki_material:test"),
        structure_revision=SimpleNamespace(
            pk=1,
            revision_no=1,
            fingerprint="structure-v1",
            structure_snapshot={"directories": []},
        ),
    )

    map_calls = [item for item in calls if item[0].startswith("material_map_")]
    assert result.pages == []
    assert result.skipped == []
    assert len(map_calls) > 1
    assert calls[-1][0] == "material_reduce_generate"
    assert tail_marker in map_calls[-1][1]


def test_new_material_call_budget_uses_derived_per_call_cap_not_16k():
    from apps.opspilot.services.wiki.wiki_budget_service import new_material_call_budget

    budget = new_material_call_budget(1, window_tokens=200_000, scene_output_default=6000)
    assert budget.max_context_tokens_per_call == 190_000


@pytest.mark.django_db
def test_invoke_llm_attaches_derived_window_and_rejects_oversized_prompt(monkeypatch):
    from apps.opspilot.models import LLMModel
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded

    captured = {}

    def fake_invoke(request, _messages):
        captured["extra"] = dict(request.extra_config or {})
        captured["max_output"] = request.max_output_tokens
        return '{"ok":true}'

    monkeypatch.setattr(build_service.LLMClientFactory, "invoke_isolated", fake_invoke)
    large = LLMModel.objects.create(name="invoke-200k", model="m")
    build_service._invoke_llm(large.pk, "hello", output_reserve=6000)
    assert captured["extra"]["input_working_tokens"] == 184_000
    assert captured["extra"]["context_window_tokens"] == 200_000
    assert captured["max_output"] == 6_000

    small = LLMModel.objects.create(name="invoke-8k", model="m", context_window_tokens=8_000)
    with pytest.raises(WikiBudgetExceeded) as exc:
        build_service._invoke_llm(small.pk, "文" * 12_000, output_reserve=4000)
    assert exc.value.code == "wiki_llm_context_window_exceeded"
    assert "max_output" not in captured or captured["max_output"] == 6_000


def _large_map_source():
    from apps.opspilot.services.wiki.text_utils import split_text_for_llm

    tail_marker = "TAIL_FACT_MUST_SURVIVE"
    source = ("文" * (32466 - len(tail_marker))) + tail_marker
    assert len(split_text_for_llm(source)) == 5
    return source, tail_marker


def _patch_legacy_map_window(monkeypatch):
    from apps.opspilot.services.llm_context_budget import LLMWorkingBudget
    from apps.opspilot.services.wiki import build_service

    primary = LLMWorkingBudget(
        window_tokens=200_000,
        safety_tokens=256,
        output_reserve_tokens=6000,
        input_working_tokens=8_000,
        compaction_threshold_tokens=6_000,
        knowledge_inject_tokens=1_200,
        build_chunk_tokens=8_000,
        single_message_tokens=1_600,
    )
    monkeypatch.setattr(build_service, "_material_window_limits", lambda _id: (primary, 2500, 2500))


def test_map_retries_empty_llm_then_continues(monkeypatch):
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    source, tail_marker = _large_map_source()
    calls = []
    _patch_legacy_map_window(monkeypatch)

    def fake_invoke(_model_id, prompt, *, budget, stage, output_reserve, force_json=False):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        calls.append((stage, prompt))
        if stage == "material_map_1":
            budget.record_call(reservation, "")
            raise build_service.BuildOutputInvalid(
                "build_output_empty_llm: stage=material_map_1 finish_reason=length " "prompt_tokens=10 completion_tokens=2500"
            )
        result = '{"pages":[]}' if stage == "material_reduce_generate" else '{"facts":["ok"]}'
        budget.record_call(reservation, result)
        return result

    monkeypatch.setattr(build_service, "_invoke_llm", fake_invoke)
    budget = LLMCallBudget(max_calls=8, max_total_tokens=60000, scope="wiki_material:map-retry")
    knowledge_base = SimpleNamespace(purpose_md="", schema_md="")
    structure_revision = SimpleNamespace(
        pk=1,
        revision_no=1,
        fingerprint="structure-v1",
        structure_snapshot={"directories": []},
    )

    result = build_service.generate_material_pages_with_budget(
        knowledge_base,
        source,
        1,
        budget=budget,
        structure_revision=structure_revision,
    )

    stages = [item[0] for item in calls]
    map_calls = [item for item in calls if item[0].startswith("material_map_")]
    assert result.pages == []
    assert result.skipped == []
    assert stages[:2] == ["material_map_1", "material_map_1_retry_2"]
    assert stages[-1] == "material_reduce_generate"
    assert "material_map_2" in stages
    assert tail_marker in map_calls[-1][1]
    assert budget.used_tokens <= budget.max_total_tokens


def test_map_skips_chunk_after_retry_still_empty(monkeypatch, caplog):
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    source, _tail_marker = _large_map_source()
    calls = []
    _patch_legacy_map_window(monkeypatch)

    def fake_invoke(_model_id, prompt, *, budget, stage, output_reserve, force_json=False):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        calls.append((stage, prompt))
        if str(stage).startswith("material_map_1"):
            budget.record_call(reservation, "")
            raise build_service.BuildOutputInvalid(
                f"build_output_empty_llm: stage={stage} finish_reason=length " "prompt_tokens=10 completion_tokens=2500"
            )
        result = '{"pages":[]}' if stage == "material_reduce_generate" else '{"facts":["ok"]}'
        budget.record_call(reservation, result)
        return result

    monkeypatch.setattr(build_service, "_invoke_llm", fake_invoke)
    budget = LLMCallBudget(max_calls=8, max_total_tokens=60000, scope="wiki_material:map-skip")
    knowledge_base = SimpleNamespace(purpose_md="", schema_md="")
    structure_revision = SimpleNamespace(
        pk=1,
        revision_no=1,
        fingerprint="structure-v1",
        structure_snapshot={"directories": []},
    )

    with caplog.at_level("INFO"):
        result = build_service.generate_material_pages_with_budget(
            knowledge_base,
            source,
            1,
            budget=budget,
            structure_revision=structure_revision,
        )

    assert result.pages == []
    assert result.skipped == [
        {
            "code": "wiki_build_llm_skip",
            "message": "map chunk skipped after empty LLM retry",
            "stage": "material_map_1",
            "error_type": "BuildOutputInvalid",
        }
    ]
    stages = [item[0] for item in calls]
    assert stages[:2] == ["material_map_1", "material_map_1_retry_2"]
    assert stages[-1] == "material_reduce_generate"
    assert "material_map_2" in stages
    assert "wiki_build_llm_skip" in caplog.text
    assert "stage=material_map_1" in caplog.text
    assert "error_type=BuildOutputInvalid" in caplog.text
    assert any(rec.msg == "wiki_build_llm_skipped kb=%s skipped=%s stages=%s" and rec.args == (None, 1, "material_map_1") for rec in caplog.records)


def test_map_still_fails_on_provider_llm_error(monkeypatch):
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    source, _tail_marker = _large_map_source()
    _patch_legacy_map_window(monkeypatch)

    def fake_invoke(_model_id, prompt, *, budget, stage, output_reserve, force_json=False):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        budget.record_call(reservation, "")
        raise build_service.BuildOutputInvalid("build_output_llm_error: stage=material_map_1 RuntimeError: provider down")

    monkeypatch.setattr(build_service, "_invoke_llm", fake_invoke)
    budget = LLMCallBudget(max_calls=8, max_total_tokens=60000, scope="wiki_material:map-error")
    knowledge_base = SimpleNamespace(purpose_md="", schema_md="")
    structure_revision = SimpleNamespace(
        pk=1,
        revision_no=1,
        fingerprint="structure-v1",
        structure_snapshot={"directories": []},
    )

    with pytest.raises(build_service.BuildOutputInvalid) as exc:
        build_service.generate_material_pages_with_budget(
            knowledge_base,
            source,
            1,
            budget=budget,
            structure_revision=structure_revision,
        )

    assert "build_output_llm_error" in str(exc.value)


def test_compact_empty_after_retry_fails_instead_of_skipping(monkeypatch):
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    source, _tail_marker = _large_map_source()
    calls = []
    huge_fact = "x" * 20000
    _patch_legacy_map_window(monkeypatch)

    def fake_invoke(_model_id, prompt, *, budget, stage, output_reserve, force_json=False):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        calls.append(stage)
        if str(stage).startswith("material_reduce_compact_"):
            budget.record_call(reservation, "")
            raise build_service.BuildOutputInvalid(
                f"build_output_empty_llm: stage={stage} finish_reason=length " "prompt_tokens=10 completion_tokens=2500"
            )
        result = '{"facts":["%s"]}' % huge_fact
        budget.record_call(reservation, result)
        return result

    monkeypatch.setattr(build_service, "_invoke_llm", fake_invoke)
    budget = LLMCallBudget(max_calls=12, max_total_tokens=None, scope="wiki_material:compact-fail")
    knowledge_base = SimpleNamespace(purpose_md="", schema_md="")
    structure_revision = SimpleNamespace(
        pk=1,
        revision_no=1,
        fingerprint="structure-v1",
        structure_snapshot={"directories": []},
    )

    with pytest.raises(build_service.BuildOutputInvalid) as exc:
        build_service.generate_material_pages_with_budget(
            knowledge_base,
            source,
            1,
            budget=budget,
            structure_revision=structure_revision,
        )

    assert "build_output_empty_llm" in str(exc.value)
    compact_calls = [stage for stage in calls if str(stage).startswith("material_reduce_compact_")]
    assert compact_calls == [
        "material_reduce_compact_1_1",
        "material_reduce_compact_1_1_retry_2",
    ]
    assert "material_reduce_generate" not in calls


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


@pytest.mark.django_db(transaction=True)
def test_material_build_publishes_partial_when_map_chunk_skipped(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, MaterialVersion
    from apps.opspilot.services.wiki import generation_material_build_service
    from apps.opspilot.services.wiki.build_generation_service import freeze_generation_identity
    from apps.opspilot.services.wiki.build_service import MaterialPageGeneration
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import ConflictRoutingResult
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    material = wiki_factory.material(
        knowledge_base=knowledge_base,
        source_identity="text:partial-map.md",
        content_hash="c" * 64,
        status="done",
        text_content="source body",
    )
    version = MaterialVersion.objects.create(material=material, content_hash=material.content_hash)
    material.current_version = version
    material.save(update_fields=["current_version", "updated_at"])
    knowledge_base.refresh_from_db()
    task_identity = freeze_generation_identity(knowledge_base, [material])
    build = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="material",
        operator="admin",
        stage="generating",
        status="running",
    )

    monkeypatch.setattr(generation_material_build_service, "load_parsed_markdown", lambda _material: "source body")
    monkeypatch.setattr(
        generation_material_build_service,
        "generate_material_pages_with_budget",
        lambda *args, **kwargs: MaterialPageGeneration(
            pages=[
                {
                    "page_type": "concept",
                    "title": "部分成功主题",
                    "tags": [],
                    "body": "这是足够长的主题正文，用于验证 skip 后仍发布页面。",
                }
            ],
            skipped=[
                {
                    "code": "wiki_build_llm_skip",
                    "message": "map chunk skipped after empty LLM retry",
                    "stage": "material_map_1",
                    "error_type": "BuildOutputInvalid",
                }
            ],
        ),
    )
    monkeypatch.setattr(
        generation_material_build_service,
        "route_material_conflicts",
        lambda *args, **kwargs: ConflictRoutingResult(
            comparisons={},
            compact_candidate_count=0,
            evidence_page_ids=(),
            old_evidence_tokens=0,
            overflow_count=0,
            llm_called=False,
            unresolved_incoming_indexes=(),
        ),
    )
    monkeypatch.setattr(generation_material_build_service, "enrich_generation_pages_wikilinks", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_navigation_service.enhance_generation_overviews",
        lambda *args, **kwargs: {"status": "skipped", "updated": 0, "llm_called": False},
    )

    published = generation_material_build_service.build_material_with_generation(
        material,
        build,
        llm_model_id=1,
        operator="admin",
        frozen_identity=task_identity,
    )

    material.refresh_from_db()
    published.refresh_from_db()
    assert published.status == "partial"
    assert published.errors == [
        {
            "code": "wiki_build_llm_skip",
            "message": "map chunk skipped after empty LLM retry",
            "stage": "material_map_1",
            "error_type": "BuildOutputInvalid",
        }
    ]
    assert published.checkpoint["skipped_count"] == 1
    assert published.checkpoint["skipped_map_stages"] == ["material_map_1"]
    assert material.status == "built"
