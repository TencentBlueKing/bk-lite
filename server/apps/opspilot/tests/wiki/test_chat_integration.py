import pytest


def _kb(name="kb"):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name=name, team=[1])


def _page(kb, title, body):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title=title, body=body, created_by="u")


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
