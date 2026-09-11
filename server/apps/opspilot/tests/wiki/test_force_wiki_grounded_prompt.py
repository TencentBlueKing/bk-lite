"""force_wiki_grounded prompt selection unit tests (no page fixture required)."""

from types import SimpleNamespace

from apps.opspilot.services.wiki import wiki_context_service as svc


def test_wiki_rules_block_non_force_contains_soft_rules():
    block = svc._wiki_rules_block("[1] demo", force_wiki_grounded=False)
    assert "知识库参考规则｜非强制" in block
    assert "知识库强制回答规则" not in block
    assert "[1] demo" in block
    assert "可以按你的人设做常规回答" in block


def test_wiki_rules_block_force_contains_strict_rules_and_refuse_phrase():
    block = svc._wiki_rules_block("[1] demo", force_wiki_grounded=True)
    assert "知识库强制回答规则｜优先级高于常识发挥" in block
    assert "知识库参考规则｜非强制" not in block
    assert "知识库中暂无相关资料,无法回答该问题。" in block
    assert "[1] demo" in block
    assert block.index("纯工具型问题") < block.index("知识库中暂无相关资料,无法回答该问题。")
    assert "必须调用工具作答" in block


def test_wiki_rules_block_empty_context_placeholder():
    soft = svc._wiki_rules_block("", force_wiki_grounded=False)
    hard = svc._wiki_rules_block("", force_wiki_grounded=True)
    assert "（暂无检索结果）" in soft
    assert "（暂无检索结果）" in hard
    assert "知识库参考规则｜非强制" in soft
    assert "知识库强制回答规则｜优先级高于常识发挥" in hard


def test_augment_prompt_with_trace_selects_force_false(monkeypatch):
    monkeypatch.setattr(
        svc,
        "build_context",
        lambda *a, **k: {"context": "[1] 《VPN》\n需审批", "citations": [{"n": 1}], "budget": {}},
    )
    prompt, citations, _ = svc.augment_prompt_with_trace(
        "人设",
        [8],
        "VPN制度",
        force_wiki_grounded=False,
    )
    assert prompt.startswith("人设")
    assert "知识库参考规则｜非强制" in prompt
    assert "知识库强制回答规则" not in prompt
    assert "[1] 《VPN》" in prompt
    assert citations == [{"n": 1}]


def test_augment_prompt_with_trace_selects_force_true(monkeypatch):
    monkeypatch.setattr(
        svc,
        "build_context",
        lambda *a, **k: {"context": "[1] 《VPN》\n需审批", "citations": [{"n": 1}], "budget": {}},
    )
    prompt, citations, _ = svc.augment_prompt_with_trace(
        "人设",
        [8],
        "VPN制度",
        force_wiki_grounded=True,
    )
    assert "知识库强制回答规则｜优先级高于常识发挥" in prompt
    assert "知识库参考规则｜非强制" not in prompt
    assert "知识库中暂无相关资料,无法回答该问题。" in prompt
    assert citations


def test_augment_prompt_with_trace_empty_context_still_appends_rules(monkeypatch):
    monkeypatch.setattr(
        svc,
        "build_context",
        lambda *a, **k: {"context": "", "citations": [], "budget": {"overview_status": "not_needed"}},
    )
    prompt_soft, c1, _ = svc.augment_prompt_with_trace("base", [8], "写诗", force_wiki_grounded=False)
    prompt_hard, c2, _ = svc.augment_prompt_with_trace("base", [8], "写诗", force_wiki_grounded=True)
    assert "知识库参考规则｜非强制" in prompt_soft
    assert "（暂无检索结果）" in prompt_soft
    assert c1 == []
    assert "知识库强制回答规则｜优先级高于常识发挥" in prompt_hard
    assert "（暂无检索结果）" in prompt_hard
    assert "知识库中暂无相关资料,无法回答该问题。" in prompt_hard
    assert c2 == []


def test_augment_prompt_with_trace_skips_force_rules_for_current_time(monkeypatch):
    def fail_build(*_a, **_k):
        raise AssertionError("纯时间问句不应调用 build_context")

    monkeypatch.setattr(svc, "build_context", fail_build)
    prompt, citations, trace = svc.augment_prompt_with_trace(
        "人设",
        [8],
        "现在几点了？",
        force_wiki_grounded=True,
    )
    assert prompt == "人设"
    assert citations == []
    assert trace.get("overview_status") == "skipped_chitchat"
    assert "知识库强制回答规则" not in prompt


def test_chat_service_passes_force_flag(monkeypatch):
    from apps.opspilot.models import SkillTypeChoices
    from apps.opspilot.services import chat_service

    captured = {}

    def fake_augment(system_prompt, kb_ids, query, **options):
        captured["options"] = options
        return "aug", [], {}

    monkeypatch.setattr(chat_service, "augment_prompt_with_trace", fake_augment)
    monkeypatch.setattr(
        chat_service,
        "load_wiki_budget_config",
        lambda: SimpleNamespace(qa_max_llm_calls=3, qa_max_output_tokens=1024),
    )
    chat_service.ChatService.format_chat_server_kwargs(
        {
            "show_think": True,
            "user_message": "q",
            "chat_history": [],
            "conversation_window_size": 10,
            "skill_prompt": "s",
            "skill_params": [],
            "wiki_kb_ids": [1],
            "force_wiki_grounded": True,
            "user_id": "u1",
            "skill_type": SkillTypeChoices.BASIC_TOOL,
        },
        SimpleNamespace(
            openai_api_base="http://llm",
            openai_api_key="key",
            model_name="model",
            protocol_type="openai",
            vendor_id=None,
            pk=1,
        ),
    )
    assert captured["options"]["force_wiki_grounded"] is True
