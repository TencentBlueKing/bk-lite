import pytest
from django.apps import apps as django_apps

from apps.workflow_orchestration.services.atom_registry import available_atom_catalog
from apps.workflow_orchestration.services.opspilot_atoms import (
    execute_agent,
    execute_intent_classification,
    execute_memory_read,
    execute_memory_write,
)

pytestmark = pytest.mark.skipif(
    not django_apps.is_installed("apps.opspilot"),
    reason="OpsPilot 未安装时不加载跨应用原子适配测试",
)

if django_apps.is_installed("apps.opspilot"):
    from apps.opspilot.memory.engines.base import MemoryReadResult, MemoryWriteResult
    from apps.opspilot.models import LLMModel, LLMSkill, MemorySpace


def _context(*, organization_id=7):
    return {
        "execution_id": "execution-1",
        "workflow_id": "workflow-1",
        "workflow_version": 1,
        "organization_id": organization_id,
        "actor": {"username": "alice", "domain": "example.com"},
        "trigger_type": "FORM",
    }


@pytest.mark.django_db
def test_agent_and_intent_atoms_reuse_opspilot_nodes_with_clean_contract(mocker):
    model = LLMModel.objects.create(name="classification-model", enabled=True, team=[7])
    skill = LLMSkill.objects.create(name="inspection-agent", llm_model=model, team=[7], usage_team=[7])
    agent_execute = mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.nodes.agent.agent.AgentNode.execute",
        return_value={"message": "inspection complete"},
    )
    intent_execute = mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier.IntentClassifierNode.execute",
        return_value={"intent": "alarm", "intent_result": "alarm", "previous_output": "cpu high"},
    )
    resolve_knowledge = mocker.patch(
        "apps.workflow_orchestration.services.opspilot_atoms.resolve_uploaded_agent_knowledge",
        return_value=[{"name": "runbook.md", "content": "check disk"}],
    )

    agent_result = execute_agent(
        {
            "agent_id": skill.id,
            "message": "inspect host",
            "prompt": "return a summary",
            "knowledge_files": [{"kind": "workflow_agent_knowledge", "token": "signed"}],
            "memory_context": "known context",
            "__bklite_context": _context(),
        }
    )
    intent_result = execute_intent_classification(
        {
            "model_id": model.id,
            "text": "cpu high",
            "intents": ["alarm", "question"],
            "classification_rules": "prefer alarm",
            "__bklite_context": _context(),
        }
    )

    assert agent_result == {"message": "inspection complete"}
    assert agent_execute.call_args.args[1]["data"]["config"]["agent"] == skill.id
    assert agent_execute.call_args.args[1]["data"]["config"]["uploadedFiles"] == [{"name": "runbook.md", "content": "check disk"}]
    resolve_knowledge.assert_called_once_with(
        [{"kind": "workflow_agent_knowledge", "token": "signed"}],
        workflow_id="workflow-1",
        team=7,
    )
    assert intent_result == {"intent": "alarm", "text": "cpu high"}
    assert intent_execute.call_args.args[1]["data"]["config"]["intents"] == [
        {"name": "alarm"},
        {"name": "question"},
    ]


@pytest.mark.django_db
def test_opspilot_atoms_reject_cross_organization_resources(mocker):
    model = LLMModel.objects.create(name="other-model", enabled=True, team=[8])
    skill = LLMSkill.objects.create(name="other-agent", llm_model=model, team=[8], usage_team=[8])
    space = MemorySpace.objects.create(name="other-memory", team=[8], scope=MemorySpace.SCOPE_TEAM)

    with pytest.raises(ValueError, match="当前组织不可用"):
        execute_agent({"agent_id": skill.id, "message": "x", "__bklite_context": _context()})
    with pytest.raises(ValueError, match="当前组织不可用"):
        execute_intent_classification({"model_id": model.id, "text": "x", "intents": ["a"], "__bklite_context": _context()})
    with pytest.raises(ValueError, match="当前组织不可用"):
        execute_memory_read({"memory_space_id": space.id, "query": "x", "__bklite_context": _context()})


@pytest.mark.django_db
def test_memory_atoms_bind_actor_or_organization_and_return_bounded_results(mocker):
    personal = MemorySpace.objects.create(name="personal-memory", team=[7], scope=MemorySpace.SCOPE_PERSONAL)
    team = MemorySpace.objects.create(name="team-memory", team=[7], scope=MemorySpace.SCOPE_TEAM)
    engine = mocker.Mock()
    engine.read.return_value = MemoryReadResult(context="remembered", raw_memories=[{"id": "m1"}], source="local")
    engine.write.return_value = MemoryWriteResult(success=True, memory_id="m2", message="ok")
    mocker.patch(
        "apps.opspilot.memory.engines.registry.MemoryEngineRegistry.get_engine",
        return_value=engine,
    )

    read = execute_memory_read({"memory_space_id": personal.id, "query": "cpu", "top_k": 3, "__bklite_context": _context()})
    written = execute_memory_write({"memory_space_id": team.id, "content": "host recovered", "title": "recovery", "__bklite_context": _context()})

    assert read == {"query": "cpu", "memory_context": "remembered", "count": 1, "source": "local"}
    assert engine.read.call_args.kwargs["entity"].user_id == "alice@example.com"
    assert written == {"content": "host recovered", "written": True, "memory_id": "m2", "event_id": None}
    assert engine.write.call_args.kwargs["entity"].organization_id == 7


@pytest.mark.django_db
def test_designer_catalog_materializes_current_organization_opspilot_options():
    own_model = LLMModel.objects.create(name="own-model", enabled=True, team=[7])
    LLMModel.objects.create(name="disabled-model", enabled=False, team=[7])
    other_model = LLMModel.objects.create(name="other-model", enabled=True, team=[8])
    own_skill = LLMSkill.objects.create(name="own-agent", llm_model=own_model, team=[7], usage_team=[7])
    LLMSkill.objects.create(name="other-agent", llm_model=other_model, team=[8], usage_team=[8])
    own_space = MemorySpace.objects.create(name="own-memory", team=[7], default_model=str(own_model.id))
    MemorySpace.objects.create(name="other-memory", team=[8])
    from apps.system_mgmt.models import User

    member = User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        password="x",
        group_list=[{"id": 7, "name": "Current"}],
    )
    User.objects.create(
        username="bob",
        display_name="Bob",
        email="bob@example.com",
        password="x",
        group_list=[{"id": 8, "name": "Other"}],
    )

    catalog = available_atom_catalog(7)

    agent_field = catalog["bklite_agent"]["input_schema"]["properties"]["agent_id"]
    model_field = catalog["bklite_intent_classification"]["input_schema"]["properties"]["model_id"]
    memory_field = catalog["bklite_memory_read"]["input_schema"]["properties"]["memory_space_id"]
    recipients = catalog["bklite_notification"]["input_schema"]["properties"]["recipients"]["items"]
    assert agent_field["enum"] == [own_skill.id]
    assert agent_field["x-enum-labels"] == {str(own_skill.id): "own-agent"}
    assert model_field["enum"] == [own_model.id]
    assert memory_field["enum"] == [own_space.id]
    assert memory_field["x-enum-metadata"][str(own_space.id)] == {
        "scope": MemorySpace.SCOPE_TEAM,
        "default_model": str(own_model.id),
    }
    assert recipients["enum"] == [str(member.id)]
    assert recipients["x-enum-labels"][str(member.id)] == "Alice (alice)"
    assert recipients["x-enum-usernames"][str(member.id)] == "alice"
