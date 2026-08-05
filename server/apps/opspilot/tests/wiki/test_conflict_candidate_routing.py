import json

import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def test_conflict_routing_fits_real_evidence_to_remaining_material_budget(
    wiki_factory,
):
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    page = wiki_factory.page(
        knowledge_base=knowledge_base,
        title="主机监控快速入门",
        body="旧知识证据" * 1200,
    )
    knowledge_base.refresh_from_db()
    assert knowledge_base.active_generation.index_entries.filter(page=page).exists()

    budget = LLMCallBudget(
        max_calls=6,
        max_total_tokens=60000,
        scope="wiki_material:test",
    )
    for index in range(5):
        reservation = budget.ensure_call(
            f"completed_{index}",
            "x" * 24000,
            output_reserve=0,
        )
        budget.record_call(reservation, "y" * 6000)
    assert budget.used_tokens == 50000

    prompts = []

    def invoke_llm(_model_id, prompt, *, budget, stage, output_reserve):
        reservation = budget.ensure_call(
            stage,
            prompt,
            output_reserve=output_reserve,
        )
        prompts.append(prompt)
        output = json.dumps(
            {
                "comparisons": [
                    {
                        "incoming_index": 0,
                        "old_page_id": page.pk,
                        "same_subject": True,
                        "relation": "supplement",
                        "reason": "新增了兼容步骤",
                    }
                ]
            },
            ensure_ascii=False,
        )
        budget.record_call(reservation, output)
        return output

    result = route_material_conflicts(
        knowledge_base.active_generation_id,
        [
            {
                "title": page.title,
                "body": "新知识证据" * 1200,
                "summary": "主机监控接入步骤",
                "page_type": "concept",
            }
        ],
        llm_model_id=1,
        budget=budget,
        invoke_llm=invoke_llm,
        base_generation_id=knowledge_base.active_generation_id,
    )

    assert result.llm_called is True
    assert result.comparisons[0]["relation"] == "supplement"
    assert len(prompts) == 1
    assert budget.used_calls == 6
    assert budget.used_tokens <= budget.max_total_tokens


def test_conflict_routing_defers_to_review_when_remaining_budget_cannot_fit_evidence(
    wiki_factory,
):
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    page = wiki_factory.page(
        knowledge_base=knowledge_base,
        title="主机监控快速入门",
        body="旧知识证据" * 1200,
    )
    knowledge_base.refresh_from_db()

    budget = LLMCallBudget(
        max_calls=6,
        max_total_tokens=60000,
        scope="wiki_material:test",
    )
    for index in range(5):
        reservation = budget.ensure_call(
            f"completed_{index}",
            "x" * 29100,
            output_reserve=0,
        )
        budget.record_call(reservation, "y" * 6000)
    assert budget.remaining_calls == 1
    assert budget.remaining_tokens < 2000

    invoked = False

    def invoke_llm(*_args, **_kwargs):
        nonlocal invoked
        invoked = True
        raise AssertionError("insufficient evidence budget must not call the LLM")

    result = route_material_conflicts(
        knowledge_base.active_generation_id,
        [
            {
                "title": page.title,
                "body": "新知识证据" * 1200,
                "summary": "主机监控接入步骤",
                "page_type": "concept",
            }
        ],
        llm_model_id=1,
        budget=budget,
        invoke_llm=invoke_llm,
        base_generation_id=knowledge_base.active_generation_id,
    )

    assert invoked is False
    assert result.llm_called is False
    assert result.comparisons[0]["relation"] == "unresolved"
    assert result.comparisons[0]["reason"] == "conflict_comparison_budget_unavailable"
    assert result.overflow_count == 1
