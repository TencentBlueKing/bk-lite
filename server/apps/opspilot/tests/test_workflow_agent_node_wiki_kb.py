"""workflow AgentNode wiki_kb_ids 透传行为锁定测试(Issue #3919)。

回归保护:workflow canvas 中"智能体"节点执行时,必须把 LLMSkill.wiki_knowledge_bases
上的 id 列表透传到 chat_kwargs["wiki_kb_ids"],触发 chat_service.augment_prompt 路径,
自动检索并把相关页面片段注入系统提示词。

revert 解耦修复(还原为不传 wiki_kb_ids)后,所有三个测试均失败。
"""

import pytest

from apps.opspilot.models import WikiKnowledgeBase
from apps.opspilot.utils.chat_flow_utils.engine.core.variable_manager import VariableManager
from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode


@pytest.fixture
def variable_manager():
    return VariableManager()


@pytest.fixture
def agent_node(variable_manager):
    node = AgentNode.__new__(AgentNode)
    node.variable_manager = variable_manager
    return node


def _make_skill_with_kb(team, kb_ids):
    """构造带 wiki_knowledge_bases 关联的 skill 替身对象。

    LLMSkill wiki_knowledge_bases 是 M2M 字段,这里用 SimpleNamespace 模拟
    `values_list('id', flat=True)` 接口。
    """
    from types import SimpleNamespace

    class _M2M:
        def __init__(self, ids):
            self._ids = list(ids)

        def values_list(self, *_args, **_kwargs):
            return iter(self._ids)

    return SimpleNamespace(
        skill_prompt="你是助手",
        skill_params=[],
        llm_model_id=1,
        temperature=0.5,
        tools=[],
        skill_type="basic",
        team=[team],
        enable_suggest=False,
        enable_query_rewrite=False,
        conversation_window_size=10,
        show_think=False,
        skill_packages=[],
        wiki_knowledge_bases=_M2M(kb_ids),
    )


def test_agent_node_passes_wiki_kb_ids_from_skill(agent_node, db):
    """skill 上勾选了 2 个 wiki KB,必须把 [kb_id1, kb_id2] 透传出去。"""
    kb1 = WikiKnowledgeBase.objects.create(name="kb-a", team=[1])
    kb2 = WikiKnowledgeBase.objects.create(name="kb-b", team=[1])
    skill = _make_skill_with_kb(team=1, kb_ids=[kb1.id, kb2.id])

    params = agent_node._build_llm_params(skill, final_message="hi", flow_input={"user_id": "u1"})

    assert "wiki_kb_ids" in params, "AgentNode._build_llm_params 必须透传 wiki_kb_ids"
    assert list(params["wiki_kb_ids"]) == [kb1.id, kb2.id]


def test_agent_node_wiki_kb_ids_empty_when_skill_has_no_kb(agent_node, db):
    """skill 没勾选任何 wiki KB 时,wiki_kb_ids 必须是空列表(而不是 None / 缺失)。"""
    skill = _make_skill_with_kb(team=1, kb_ids=[])

    params = agent_node._build_llm_params(skill, final_message="hi", flow_input={"user_id": "u1"})

    # 即便为空,字段必须存在;chat_service 中 if wiki_kb_ids 走空集合短路分支。
    assert "wiki_kb_ids" in params
    assert list(params["wiki_kb_ids"]) == []


def test_agent_node_wiki_kb_ids_preserves_int_type(agent_node, db):
    """kb ids 必须是 int(给 WikiKnowledgeBase.objects.filter(id=...) 用),不能被强转 str。"""
    kb = WikiKnowledgeBase.objects.create(name="kb-int", team=[1])
    skill = _make_skill_with_kb(team=1, kb_ids=[kb.id])

    params = agent_node._build_llm_params(skill, final_message="hi", flow_input={"user_id": "u1"})

    out_ids = list(params["wiki_kb_ids"])
    assert len(out_ids) == 1
    # wiki_context_service.augment_prompt 内部 WikiKnowledgeBase.objects.filter(id=kb_ids[0]),
    # 若被强转 str 会导致查询空结果或类型错误。
    assert isinstance(out_ids[0], int)
