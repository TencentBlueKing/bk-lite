"""LLM 上下文窗口工作预算派生：只断言 spec 锁定的字面量。"""

import pytest

from apps.opspilot.services.llm_context_budget import derive_llm_working_budget, parse_context_window_tokens


def test_derive_working_budget_for_200k_window_and_4k_output():
    budget = derive_llm_working_budget(200_000, scene_output_default=4000)

    assert budget.window_tokens == 200_000
    assert budget.safety_tokens == 10_000
    assert budget.output_reserve_tokens == 4_000
    assert budget.input_working_tokens == 186_000
    assert budget.compaction_threshold_tokens == 139_500
    assert budget.knowledge_inject_tokens == 27_900
    assert budget.build_chunk_tokens == 27_900
    assert budget.single_message_tokens == 37_200


def test_derive_working_budget_for_8k_window_caps_output_at_10_percent():
    budget = derive_llm_working_budget(8_000, scene_output_default=4000)

    assert budget.window_tokens == 8_000
    assert budget.safety_tokens == 400
    assert budget.output_reserve_tokens == 800
    assert budget.input_working_tokens == 6_800
    assert budget.compaction_threshold_tokens == 5_100
    assert budget.knowledge_inject_tokens == 1_020
    assert budget.build_chunk_tokens == 1_020
    assert budget.single_message_tokens == 1_360


def test_parse_context_window_tokens_defaults_and_accepts_bounds():
    assert parse_context_window_tokens(None) == 200_000
    assert parse_context_window_tokens(8_000) == 8_000
    assert parse_context_window_tokens(2_000_000) == 2_000_000


def test_parse_context_window_tokens_rejects_out_of_range():
    with pytest.raises(ValueError, match="8000"):
        parse_context_window_tokens(7_999)
    with pytest.raises(ValueError, match="8000"):
        parse_context_window_tokens(2_000_001)
