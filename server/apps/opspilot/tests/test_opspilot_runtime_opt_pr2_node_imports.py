"""OpsPilot runtime optimization PR2: smoke imports for split node modules."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_import_knowledge_tools_module():
    from apps.opspilot.metis.llm.chain import knowledge_tools

    assert knowledge_tools.KnowledgeToolsMixin is not None
    assert callable(knowledge_tools._build_knowledge_retrieve_tool)
    assert callable(knowledge_tools._normalize_kb_results)


def test_import_skill_sandbox_module():
    from apps.opspilot.metis.llm.chain import skill_sandbox

    assert skill_sandbox.SkillSandboxMixin is not None
    assert callable(skill_sandbox._build_skill_backend_and_sources)
    assert callable(skill_sandbox._sandbox_env)
    assert callable(skill_sandbox._cleanup_sandbox)
    assert callable(skill_sandbox._skill_sandbox_base)


def test_import_approval_tools_module():
    from apps.opspilot.metis.llm.chain import approval_tools

    assert approval_tools.ApprovalToolsMixin is not None
    assert callable(approval_tools._build_approval_tool)
    assert callable(approval_tools._build_choice_tool)


def test_import_deepagent_assembly_module():
    from apps.opspilot.metis.llm.chain import deepagent_assembly

    assert deepagent_assembly.DeepAgentAssemblyMixin is not None
    assert callable(deepagent_assembly._build_interrupt_on)
    assert callable(deepagent_assembly._build_planned_execution_runtime_middleware)
    assert callable(deepagent_assembly._build_deep_agent_kwargs)


@pytest.mark.parametrize(
    "symbol",
    [
        "_build_knowledge_retrieve_tool",
        "_normalize_kb_results",
        "_build_skill_backend_and_sources",
        "_resolve_skill_packages",
        "_build_approval_tool",
        "_build_choice_tool",
        "_build_deep_agent_kwargs",
        "_patched_convert_message_to_dict",
    ],
)
def test_symbol_importable_from_node(symbol):
    import apps.opspilot.metis.llm.chain.node as node

    assert hasattr(node, symbol)


def test_knowledge_tools_aliases_match_node():
    from apps.opspilot.metis.llm.chain import knowledge_tools, node

    assert node._build_knowledge_retrieve_tool is knowledge_tools._build_knowledge_retrieve_tool
    assert node._normalize_kb_results is knowledge_tools._normalize_kb_results


def test_skill_sandbox_aliases_match_node():
    from apps.opspilot.metis.llm.chain import node, skill_sandbox

    assert node._resolve_skill_packages is skill_sandbox._resolve_skill_packages
    assert node._build_skill_backend_and_sources is skill_sandbox._build_skill_backend_and_sources
