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
    assert "相关知识库信息" in prompt
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
    # 无命中 -> 原样返回
    p2, c2 = augment_prompt("base", [kb.id], "数据库备份")
    assert p2 == "base" and c2 == []


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

    def fake_augment_prompt(system_prompt, kb_ids, query, **options):
        captured.update(
            {
                "system_prompt": system_prompt,
                "kb_ids": kb_ids,
                "query": query,
                "options": options,
            }
        )
        return "augmented prompt", [{"title": "服务操作手册"}]

    monkeypatch.setattr(chat_service, "augment_prompt", fake_augment_prompt, raising=False)

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
        ),
    )

    assert captured["kb_ids"] == [1]
    assert captured["query"] == "请重启服务"
    assert captured["options"] == {"retrieval_mode": "chunk", "graph_hops": 0, "token_budget": 64}
    assert chat_kwargs["system_message_prompt"] == "augmented prompt"
    assert chat_kwargs["extra_config"]["wiki_citations"] == [{"title": "服务操作手册"}]
