from types import SimpleNamespace

import pytest


def _kb(name="kb"):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name=name, team=[1])


def _page(kb, title, body):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title=title, body=body, created_by="u")


def _chunk_embed_stub(texts):
    vectors = []
    for text in texts:
        if "restart" in text:
            vectors.append([1.0, 0.0])
        elif "backup" in text:
            vectors.append([0.0, 1.0])
        else:
            vectors.append([0.9, 0.1])
    return vectors


@pytest.mark.django_db
def test_augment_prompt_injects_context_and_citations():
    from apps.opspilot.services.wiki.wiki_context_service import augment_prompt

    kb = _kb()
    _page(kb, "重启服务", "执行 systemctl restart 重启服务")

    prompt, citations = augment_prompt("你是运维助手", [kb.id], "重启服务")
    assert "你是运维助手" in prompt
    assert "知识库检索结果" in prompt
    assert "systemctl restart" in prompt
    assert citations and citations[0]["title"] == "重启服务"


@pytest.mark.django_db
def test_augment_prompt_passes_context_options():
    from apps.opspilot.services.wiki.embedding_service import reindex_page_chunks
    from apps.opspilot.services.wiki.wiki_context_service import augment_prompt

    kb = _kb()
    page = _page(kb, "服务操作手册", "# 重启\nsystemctl restart\n# 备份\nbackup db")
    reindex_page_chunks(page, kb.embed_provider, embed_fn=_chunk_embed_stub)

    prompt, citations = augment_prompt(
        "你是运维助手",
        [kb.id],
        "重启",
        top_k=2,
        retrieval_mode="chunk",
        graph_hops=0,
        token_budget=48,
        embed_fn=_chunk_embed_stub,
    )

    assert "systemctl restart" in prompt
    assert citations[0]["kind"] == "page_chunk"
    assert citations[0]["title"] == "服务操作手册 / 重启"
    assert citations[0]["explanation"]["matched_by"] == ["chunk_vector"]


@pytest.mark.django_db
def test_augment_prompt_noop_without_kb_or_match():
    from apps.opspilot.services.wiki.wiki_context_service import augment_prompt

    kb = _kb()
    _page(kb, "网络", "静态路由")

    # 未选知识库 -> 原样返回
    p1, c1 = augment_prompt("base", [], "任何问题")
    assert p1 == "base" and c1 == []
    # 无命中 -> 仍追加规则段（默认非强制），citations 为空
    p2, c2 = augment_prompt("base", [kb.id], "数据库备份")
    assert "知识库参考规则｜非强制" in p2
    assert "（暂无检索结果）" in p2
    assert c2 == []


def test_should_skip_wiki_retrieval_for_greetings():
    from apps.opspilot.services.wiki.wiki_context_service import should_skip_wiki_retrieval

    assert should_skip_wiki_retrieval("你好") is True
    assert should_skip_wiki_retrieval("Hello!") is True
    assert should_skip_wiki_retrieval("谢谢") is True
    assert should_skip_wiki_retrieval("在吗") is True
    assert should_skip_wiki_retrieval("如何重启 tomcat 服务") is False
    assert should_skip_wiki_retrieval("告警 Unhealthy startup probe 怎么排查") is False


def test_should_skip_wiki_retrieval_for_time_tool_queries():
    from apps.opspilot.services.wiki.wiki_context_service import should_skip_wiki_retrieval

    assert should_skip_wiki_retrieval("现在几点了") is True
    assert should_skip_wiki_retrieval("现在几点了？") is True
    assert should_skip_wiki_retrieval("现在几点") is True
    assert should_skip_wiki_retrieval("几点了") is True
    assert should_skip_wiki_retrieval("what time is it") is True
    assert should_skip_wiki_retrieval("现在几点开会") is False
    assert should_skip_wiki_retrieval("怎么巡检数据库？") is False
    assert should_skip_wiki_retrieval("帮我写一首关于月亮的诗") is False


@pytest.mark.django_db
def test_augment_prompt_skips_retrieval_for_chitchat():
    from apps.opspilot.services.wiki.wiki_context_service import augment_prompt, augment_prompt_with_trace

    kb = _kb()

    prompt, citations = augment_prompt("你是运维助手", [kb.id], "你好")
    assert prompt == "你是运维助手"
    assert citations == []

    _, _, trace = augment_prompt_with_trace("你是运维助手", [kb.id], "hello")
    assert trace.get("overview_status") == "skipped_chitchat"
    assert (trace.get("llm_budget") or {}).get("used_calls") == 0


@pytest.mark.django_db
def test_skill_can_reference_wiki_knowledge_bases():
    from apps.opspilot.models import LLMSkill

    kb = _kb()
    skill = LLMSkill.objects.create(name="s", team=[1])
    skill.wiki_knowledge_bases.add(kb)

    assert list(skill.wiki_knowledge_bases.values_list("id", flat=True)) == [kb.id]
    # 反向关系
    assert kb.skills.filter(id=skill.id).exists()


def test_chat_service_passes_wiki_context_options(monkeypatch):
    from apps.opspilot.models import SkillTypeChoices
    from apps.opspilot.services import chat_service

    captured = {}

    def fake_augment_prompt_with_trace(system_prompt, kb_ids, query, **options):
        captured.update(
            {
                "system_prompt": system_prompt,
                "kb_ids": kb_ids,
                "query": query,
                "options": options,
            }
        )
        return "augmented prompt", [{"title": "服务操作手册"}], {"overview_status": "routed", "llm_budget": {"used_calls": 0}}

    monkeypatch.setattr(chat_service, "augment_prompt_with_trace", fake_augment_prompt_with_trace)
    monkeypatch.setattr(
        chat_service,
        "load_wiki_budget_config",
        lambda: SimpleNamespace(qa_max_llm_calls=3, qa_max_output_tokens=1024),
    )

    chat_kwargs, _, _ = chat_service.ChatService.format_chat_server_kwargs(
        {
            "show_think": True,
            "user_message": "请重启服务",
            "chat_history": [],
            "conversation_window_size": 10,
            "skill_prompt": "你是运维助手",
            "skill_params": [],
            "wiki_kb_ids": [1],
            "wiki_retrieval_mode": "chunk",
            "wiki_graph_hops": 0,
            "wiki_token_budget": 64,
            "temperature": 0.2,
            "user_id": "u1",
            "skill_type": SkillTypeChoices.KNOWLEDGE_TOOL,
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

    assert captured["kb_ids"] == [1]
    assert captured["query"] == "请重启服务"
    assert captured["options"]["retrieval_mode"] == "chunk"
    assert captured["options"]["graph_hops"] == 0
    assert captured["options"]["token_budget"] == 64
    assert chat_kwargs["system_message_prompt"] == "augmented prompt"
    assert chat_kwargs["extra_config"]["wiki_citations"] == [{"title": "服务操作手册"}]
    assert chat_kwargs["max_model_calls"] == 1


def test_chat_service_skips_wiki_path_for_greeting(monkeypatch):
    from apps.opspilot.models import SkillTypeChoices
    from apps.opspilot.services import chat_service

    called = {"augment": 0}

    def fake_augment_prompt_with_trace(*_args, **_kwargs):
        called["augment"] += 1
        raise AssertionError("寒暄不应触发 Wiki 检索")

    monkeypatch.setattr(chat_service, "augment_prompt_with_trace", fake_augment_prompt_with_trace)

    chat_kwargs, _, _ = chat_service.ChatService.format_chat_server_kwargs(
        {
            "show_think": True,
            "user_message": "你好",
            "chat_history": [],
            "conversation_window_size": 10,
            "skill_prompt": "你是运维助手",
            "skill_params": [],
            "wiki_kb_ids": [1],
            "temperature": 0.2,
            "user_id": "u1",
            "skill_type": SkillTypeChoices.KNOWLEDGE_TOOL,
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

    assert called["augment"] == 0
    assert chat_kwargs["system_message_prompt"] == "你是运维助手"
    assert "max_model_calls" not in chat_kwargs
    assert chat_kwargs["extra_config"]["wiki_budget"]["overview_status"] == "skipped_chitchat"


def test_chat_service_skips_wiki_path_for_current_time(monkeypatch):
    from apps.opspilot.models import SkillTypeChoices
    from apps.opspilot.services import chat_service

    called = {"augment": 0}

    def fake_augment_prompt_with_trace(*_args, **_kwargs):
        called["augment"] += 1
        raise AssertionError("纯时间问句不应触发 Wiki 检索")

    monkeypatch.setattr(chat_service, "augment_prompt_with_trace", fake_augment_prompt_with_trace)

    chat_kwargs, _, _ = chat_service.ChatService.format_chat_server_kwargs(
        {
            "show_think": True,
            "user_message": "现在几点了？",
            "chat_history": [],
            "conversation_window_size": 10,
            "skill_prompt": "你是运维助手",
            "skill_params": [],
            "wiki_kb_ids": [1],
            "force_wiki_grounded": True,
            "temperature": 0.2,
            "user_id": "u1",
            "skill_type": SkillTypeChoices.KNOWLEDGE_TOOL,
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

    assert called["augment"] == 0
    assert chat_kwargs["system_message_prompt"] == "你是运维助手"
    assert "wiki_citations" not in chat_kwargs["extra_config"]
    assert chat_kwargs["extra_config"]["wiki_budget"]["overview_status"] == "skipped_chitchat"


@pytest.mark.django_db
def test_augment_prompt_force_false_uses_non_force_rules():
    from apps.opspilot.services.wiki.wiki_context_service import augment_prompt_with_trace

    kb = _kb()
    _page(kb, "VPN制度", "VPN 使用需要审批")

    prompt, citations, _ = augment_prompt_with_trace(
        "你是专业机器人",
        [kb.id],
        "VPN使用有什么制度要求",
        force_wiki_grounded=False,
    )
    assert "知识库参考规则｜非强制" in prompt
    assert "知识库强制回答规则" not in prompt
    assert "知识库检索结果" in prompt
    assert citations


@pytest.mark.django_db
def test_augment_prompt_force_true_uses_force_rules():
    from apps.opspilot.services.wiki.wiki_context_service import augment_prompt_with_trace

    kb = _kb()
    _page(kb, "VPN制度", "VPN 使用需要审批")

    prompt, citations, _ = augment_prompt_with_trace(
        "你是专业机器人",
        [kb.id],
        "VPN使用有什么制度要求",
        force_wiki_grounded=True,
    )
    assert "知识库强制回答规则｜优先级高于常识发挥" in prompt
    assert "知识库参考规则｜非强制" not in prompt
    assert "知识库中暂无相关资料,无法回答该问题。" in prompt
    assert citations


@pytest.mark.django_db
def test_augment_prompt_empty_context_still_appends_rules_force_true():
    from apps.opspilot.services.wiki.wiki_context_service import augment_prompt_with_trace

    kb = _kb()
    _page(kb, "网络", "静态路由")

    prompt, citations, _ = augment_prompt_with_trace(
        "base",
        [kb.id],
        "帮我写一首关于月亮的诗",
        force_wiki_grounded=True,
    )
    assert "知识库强制回答规则｜优先级高于常识发挥" in prompt
    assert "（暂无检索结果）" in prompt or "知识库检索结果" in prompt
    assert "知识库中暂无相关资料,无法回答该问题。" in prompt
    assert citations == []


@pytest.mark.django_db
def test_augment_prompt_empty_context_non_force_allows_general():
    from apps.opspilot.services.wiki.wiki_context_service import augment_prompt_with_trace

    kb = _kb()
    _page(kb, "网络", "静态路由")

    prompt, citations, _ = augment_prompt_with_trace(
        "base",
        [kb.id],
        "怎么给电脑优化性能",
        force_wiki_grounded=False,
    )
    assert "知识库参考规则｜非强制" in prompt
    assert "可以按你的人设做常规回答" in prompt
    assert citations == []


def test_chat_service_passes_force_wiki_grounded(monkeypatch):
    from apps.opspilot.models import SkillTypeChoices
    from apps.opspilot.services import chat_service

    captured = {}

    def fake_augment_prompt_with_trace(system_prompt, kb_ids, query, **options):
        captured["options"] = options
        return "augmented", [], {}

    monkeypatch.setattr(chat_service, "augment_prompt_with_trace", fake_augment_prompt_with_trace)
    monkeypatch.setattr(
        chat_service,
        "load_wiki_budget_config",
        lambda: SimpleNamespace(qa_max_llm_calls=3, qa_max_output_tokens=1024),
    )

    chat_service.ChatService.format_chat_server_kwargs(
        {
            "show_think": True,
            "user_message": "请重启服务",
            "chat_history": [],
            "conversation_window_size": 10,
            "skill_prompt": "你是运维助手",
            "skill_params": [],
            "wiki_kb_ids": [1],
            "force_wiki_grounded": True,
            "temperature": 0.2,
            "user_id": "u1",
            "skill_type": SkillTypeChoices.KNOWLEDGE_TOOL,
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
    assert captured["options"].get("force_wiki_grounded") is True
