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


def _conflict_routing_context(wiki_factory, *, max_calls, max_total_tokens=200000):
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
        max_calls=max_calls,
        max_total_tokens=max_total_tokens,
        scope="wiki_material:test",
    )
    for index in range(5):
        reservation = budget.ensure_call(
            f"completed_{index}",
            "x" * 24000,
            output_reserve=0,
        )
        budget.record_call(reservation, "y" * 6000)
    return knowledge_base, page, budget


def test_conflict_routing_retries_empty_llm_then_keeps_comparison(wiki_factory):
    from apps.opspilot.services.wiki.build_service import BuildOutputInvalid
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts

    knowledge_base, page, budget = _conflict_routing_context(wiki_factory, max_calls=8)
    stages = []

    def invoke_llm(_model_id, prompt, *, budget, stage, output_reserve):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        stages.append(stage)
        if stage == "material_conflict_batch":
            budget.record_call(reservation, "")
            raise BuildOutputInvalid(
                "build_output_empty_llm: stage=material_conflict_batch finish_reason=length " "prompt_tokens=10 completion_tokens=4000"
            )
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

    assert stages == ["material_conflict_batch", "material_conflict_batch_retry_2"]
    assert result.llm_called is True
    assert result.comparisons[0]["relation"] == "supplement"
    assert result.comparisons[0]["reason"] == "新增了兼容步骤"


def test_conflict_routing_marks_unresolved_when_llm_stays_empty(wiki_factory, caplog):
    from apps.opspilot.services.wiki.build_service import BuildOutputInvalid
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts

    knowledge_base, page, budget = _conflict_routing_context(wiki_factory, max_calls=8)
    stages = []

    def invoke_llm(_model_id, prompt, *, budget, stage, output_reserve):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        stages.append(stage)
        budget.record_call(reservation, "")
        raise BuildOutputInvalid(f"build_output_empty_llm: stage={stage} finish_reason=length " "prompt_tokens=10 completion_tokens=4000")

    with caplog.at_level("WARNING"):
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

    assert stages == ["material_conflict_batch", "material_conflict_batch_retry_2"]
    assert result.llm_called is True
    assert result.comparisons[0]["relation"] == "unresolved"
    assert result.comparisons[0]["reason"] == "conflict_comparison_llm_empty"
    assert "wiki conflict comparison LLM 失败" in caplog.text
    assert f"candidate_generation_id={knowledge_base.active_generation_id}" in caplog.text
    assert "error_type=BuildOutputInvalid" in caplog.text


def test_conflict_routing_degrades_when_retry_exceeds_token_budget(wiki_factory, caplog):
    from apps.opspilot.services.wiki.build_service import BuildOutputInvalid
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts

    knowledge_base, page, budget = _conflict_routing_context(
        wiki_factory,
        max_calls=8,
        max_total_tokens=60000,
    )
    stages = []

    def invoke_llm(_model_id, prompt, *, budget, stage, output_reserve):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        stages.append(stage)
        budget.record_call(reservation, "")
        raise BuildOutputInvalid(f"build_output_empty_llm: stage={stage} finish_reason=length " "prompt_tokens=10 completion_tokens=4000")

    with caplog.at_level("WARNING"):
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

    assert stages == ["material_conflict_batch"]
    assert result.llm_called is True
    assert result.comparisons[0]["relation"] == "unresolved"
    assert result.comparisons[0]["reason"] == "conflict_comparison_llm_empty"
    assert "error_type=WikiBudgetExceeded" in caplog.text


def test_conflict_routing_treats_same_title_different_subject_as_unrelated(wiki_factory):
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    page = wiki_factory.page(
        knowledge_base=knowledge_base,
        title="应用与菜单管理",
        body="# 应用与菜单管理\n\n用于配置系统应用入口、菜单层级和权限绑定。",
    )
    knowledge_base.refresh_from_db()
    invoked = False

    def invoke_llm(*_args, **_kwargs):
        nonlocal invoked
        invoked = True
        raise AssertionError("distinct subjects must not need LLM comparison")

    result = route_material_conflicts(
        knowledge_base.active_generation_id,
        [
            {
                "title": "应用与菜单管理",
                "page_type": "concept",
                "body": "# 云区域管理\n\n云区域是节点管理模块的分区单元，用于纳管节点。",
            }
        ],
        llm_model_id=1,
        budget=LLMCallBudget(max_calls=4, max_total_tokens=20000, scope="wiki_material:test"),
        invoke_llm=invoke_llm,
        base_generation_id=knowledge_base.active_generation_id,
    )

    assert invoked is False
    assert result.comparisons[0]["relation"] == "unrelated"
    assert result.comparisons[0]["same_subject"] is False
    assert result.comparisons[0]["old_page_id"] == page.pk


def test_conflict_routing_compares_generic_title_against_existing_page(wiki_factory):
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    page = wiki_factory.page(
        knowledge_base=knowledge_base,
        title="机房温湿度巡检标准",
        body="广州一号机房夏季温度应保持在 28℃ 到 32℃。湿度不需要控制。",
        contribution="human",
    )
    knowledge_base.refresh_from_db()
    prompts = []

    def invoke_llm(_model_id, prompt, *, budget, stage, output_reserve):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        prompts.append(prompt)
        output = json.dumps(
            {
                "comparisons": [
                    {
                        "incoming_index": 0,
                        "old_page_id": page.pk,
                        "same_subject": True,
                        "relation": "conflict",
                        "reason": "同一巡检标准的温度结论相反",
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
                "title": "定义",
                "page_type": "concept",
                "keywords": ["机房", "温度", "湿度"],
                "body": ("## 定义\n\n" "机房温湿度控制标准规定温度保持在 18℃ 到 27℃，相对湿度保持在 40% 到 70%。" "旧结论「夏季温度保持在 28℃ 到 32℃，湿度不需要控制」有误。"),
            }
        ],
        llm_model_id=1,
        budget=LLMCallBudget(max_calls=4, max_total_tokens=20000, scope="wiki_material:test"),
        invoke_llm=invoke_llm,
        base_generation_id=knowledge_base.active_generation_id,
        chat_sourced=True,
    )

    assert prompts
    assert str(page.pk) in prompts[0]
    assert result.llm_called is True
    assert result.comparisons[0]["relation"] == "conflict"
    assert result.comparisons[0]["same_subject"] is True
    assert result.comparisons[0]["old_page_id"] == page.pk


def test_conflict_routing_prefers_human_page_when_titles_share_subject_stem(wiki_factory):
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    human_page = wiki_factory.page(
        knowledge_base=knowledge_base,
        title="机房温湿度巡检标准",
        body="广州一号机房夏季温度应保持在 28℃ 到 32℃。湿度不需要控制。",
        contribution="human",
    )
    ai_page = wiki_factory.page(
        knowledge_base=knowledge_base,
        title="定义",
        body="## 定义\n\n机房温度保持在 18℃ 到 27℃，相对湿度保持在 40% 到 70%。",
        contribution="ai",
    )
    knowledge_base.refresh_from_db()

    def invoke_llm(_model_id, prompt, *, budget, stage, output_reserve):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        output = json.dumps(
            {
                "comparisons": [
                    {
                        "incoming_index": 0,
                        "old_page_id": ai_page.pk,
                        "same_subject": True,
                        "relation": "conflict",
                        "reason": "区间不同",
                    },
                    {
                        "incoming_index": 0,
                        "old_page_id": human_page.pk,
                        "same_subject": True,
                        "relation": "conflict",
                        "reason": "旧结论被明确否定",
                    },
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
                "title": "机房温湿度控制标准",
                "page_type": "concept",
                "keywords": ["机房", "温度", "湿度"],
                "body": ("## 定义\n\n" "温度保持在 24℃ 到 27℃，相对湿度保持在 50% 到 80%。" "旧结论「夏季温度保持在 28℃ 到 32℃，湿度不需要控制」有误。"),
            }
        ],
        llm_model_id=1,
        budget=LLMCallBudget(max_calls=4, max_total_tokens=20000, scope="wiki_material:test"),
        invoke_llm=invoke_llm,
        base_generation_id=knowledge_base.active_generation_id,
        chat_sourced=True,
    )

    assert result.llm_called is True
    assert human_page.pk in result.evidence_page_ids
    assert result.comparisons[0]["old_page_id"] == human_page.pk
    assert result.comparisons[0]["relation"] == "conflict"


def test_conflict_routing_treats_different_module_titles_as_unrelated(wiki_factory):
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    page = wiki_factory.page(
        knowledge_base=knowledge_base,
        title="WeOpsX 作业管理模块",
        body="# WeOpsX 作业管理模块\n\n作业管理是 WeOpsX 平台统一的脚本执行中心。",
    )
    knowledge_base.refresh_from_db()
    invoked = False

    def invoke_llm(*_args, **_kwargs):
        nonlocal invoked
        invoked = True
        raise AssertionError("distinct WeOpsX modules must not need LLM comparison")

    result = route_material_conflicts(
        knowledge_base.active_generation_id,
        [
            {
                "title": "WeOpsX 节点管理模块",
                "page_type": "concept",
                "summary": "WeOpsX 采集与执行底座",
                "keywords": ["WeOpsX", "节点", "云区域"],
                "body": "# 节点管理\n\n节点管理是 WeOpsX 平台的采集与执行底座模块，统一管理云区域。",
            }
        ],
        llm_model_id=1,
        budget=LLMCallBudget(max_calls=4, max_total_tokens=20000, scope="wiki_material:test"),
        invoke_llm=invoke_llm,
        base_generation_id=knowledge_base.active_generation_id,
    )

    assert invoked is False
    assert result.comparisons[0]["relation"] == "unrelated"
    assert result.comparisons[0]["same_subject"] is False
    assert result.comparisons[0]["old_page_id"] == page.pk


def _route_alarm_rule_pair(wiki_factory, *, chat_sourced):
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    page = wiki_factory.page(
        knowledge_base=knowledge_base,
        title="告警规则说明",
        body="# 告警规则说明\n\n说明里写了阈值和通知对象。",
    )
    knowledge_base.refresh_from_db()
    invoked = False

    def invoke_llm(_model_id, prompt, *, budget, stage, output_reserve):
        nonlocal invoked
        invoked = True
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        output = json.dumps(
            {
                "comparisons": [
                    {
                        "incoming_index": 0,
                        "old_page_id": page.pk,
                        "same_subject": False,
                        "relation": "unrelated",
                        "reason": "配置和说明不是同一条规则",
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
                "title": "告警规则配置",
                "page_type": "concept",
                "keywords": ["阈值", "通知对象"],
                "body": "# 告警规则配置\n\n配置项包括阈值和通知对象。",
            }
        ],
        llm_model_id=1,
        budget=LLMCallBudget(max_calls=4, max_total_tokens=20000, scope="wiki_material:test"),
        invoke_llm=invoke_llm,
        base_generation_id=knowledge_base.active_generation_id,
        chat_sourced=chat_sourced,
    )
    return page, result, invoked


def test_uploaded_material_does_not_treat_short_suffix_titles_as_same_subject(wiki_factory):
    page, result, invoked = _route_alarm_rule_pair(wiki_factory, chat_sourced=False)

    assert invoked is False
    assert result.comparisons[0]["relation"] == "unrelated"
    assert result.comparisons[0]["same_subject"] is False
    assert result.comparisons[0]["old_page_id"] == page.pk


def test_chat_material_still_compares_short_suffix_titles(wiki_factory):
    page, result, invoked = _route_alarm_rule_pair(wiki_factory, chat_sourced=True)

    assert invoked is True
    assert result.llm_called is True
    assert result.comparisons[0]["old_page_id"] == page.pk


def test_uploaded_material_keeps_generic_title_as_a_distinct_subject(wiki_factory):
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    page = wiki_factory.page(
        knowledge_base=knowledge_base,
        title="机房巡检手册",
        body="机房巡检手册规定夏季温度上限。",
    )
    knowledge_base.refresh_from_db()
    invoked = False

    def invoke_llm(*_args, **_kwargs):
        nonlocal invoked
        invoked = True
        raise AssertionError("generic titles stay concrete for uploaded materials")

    result = route_material_conflicts(
        knowledge_base.active_generation_id,
        [
            {
                "title": "定义",
                "page_type": "concept",
                "keywords": ["机房", "温度"],
                "body": "## 定义\n\n这是另一份文档的开篇，不是机房巡检手册。",
            }
        ],
        llm_model_id=1,
        budget=LLMCallBudget(max_calls=4, max_total_tokens=20000, scope="wiki_material:test"),
        invoke_llm=invoke_llm,
        base_generation_id=knowledge_base.active_generation_id,
        chat_sourced=False,
    )

    assert invoked is False
    assert result.comparisons[0]["relation"] == "unrelated"
    assert result.comparisons[0]["old_page_id"] == page.pk


def test_uploaded_material_does_not_prefer_human_page_on_equal_conflict(wiki_factory):
    from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.services.wiki.wiki_budget_service import LLMCallBudget

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    human_page = wiki_factory.page(
        knowledge_base=knowledge_base,
        title="告警规则说明",
        body="人工记录的告警阈值是 80%。",
        contribution="human",
    )
    ai_page = wiki_factory.page(
        knowledge_base=knowledge_base,
        title="告警规则",
        body="AI 记录的告警阈值是 90%。",
        contribution="ai",
    )
    knowledge_base.refresh_from_db()
    ai_page.refresh_from_db()
    human_page.refresh_from_db()

    def invoke_llm(_model_id, prompt, *, budget, stage, output_reserve):
        reservation = budget.ensure_call(stage, prompt, output_reserve=output_reserve)
        output = json.dumps(
            {
                "comparisons": [
                    {
                        "incoming_index": 0,
                        "old_page_id": ai_page.pk,
                        "same_subject": True,
                        "relation": "conflict",
                        "reason": "阈值不同",
                    },
                    {
                        "incoming_index": 0,
                        "old_page_id": human_page.pk,
                        "same_subject": True,
                        "relation": "conflict",
                        "reason": "阈值不同",
                    },
                ]
            },
            ensure_ascii=False,
        )
        budget.record_call(reservation, output)
        return output

    pages = [
        {
            "title": "告警规则",
            "page_type": "concept",
            "keywords": ["告警", "阈值"],
            "body": "新的告警阈值是 70%。",
        }
    ]
    uploaded = route_material_conflicts(
        knowledge_base.active_generation_id,
        pages,
        llm_model_id=1,
        budget=LLMCallBudget(max_calls=4, max_total_tokens=20000, scope="wiki_material:test"),
        invoke_llm=invoke_llm,
        base_generation_id=knowledge_base.active_generation_id,
        chat_sourced=False,
    )
    chat = route_material_conflicts(
        knowledge_base.active_generation_id,
        pages,
        llm_model_id=1,
        budget=LLMCallBudget(max_calls=4, max_total_tokens=20000, scope="wiki_material:test"),
        invoke_llm=invoke_llm,
        base_generation_id=knowledge_base.active_generation_id,
        chat_sourced=True,
    )

    assert ai_page.contribution == "ai"
    assert human_page.contribution == "human"
    assert uploaded.comparisons[0]["old_page_id"] == ai_page.pk
    assert chat.comparisons[0]["old_page_id"] == human_page.pk
