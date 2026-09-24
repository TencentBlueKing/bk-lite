"""opspilot_atoms 单元测试：用 mock 覆盖校验/组织边界/限额，不依赖 INSTALLED_APPS。"""

import sys
import types
from types import SimpleNamespace

import pytest

from apps.workflow_orchestration.services import opspilot_atoms as atoms


def _context(**overrides):
    base = {
        "execution_id": "execution-1",
        "workflow_id": "workflow-1",
        "workflow_version": 1,
        "organization_id": 7,
        "actor": {"username": "alice", "domain": "example.com"},
        "trigger_type": "FORM",
    }
    base.update(overrides)
    return base


def _install_agent_node(monkeypatch, execute):
    mod = types.ModuleType("apps.opspilot.utils.chat_flow_utils.nodes.agent.agent")

    class AgentNode:
        def __init__(self, manager):
            self.manager = manager

        def execute(self, *args, **kwargs):
            return execute(*args, **kwargs)

    mod.AgentNode = AgentNode
    monkeypatch.setitem(sys.modules, "apps.opspilot.utils.chat_flow_utils.nodes.agent.agent", mod)


def _install_intent_node(monkeypatch, execute):
    mod = types.ModuleType("apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier")

    class IntentClassifierNode:
        def __init__(self, manager):
            self.manager = manager

        def execute(self, *args, **kwargs):
            return execute(*args, **kwargs)

    mod.IntentClassifierNode = IntentClassifierNode
    monkeypatch.setitem(
        sys.modules,
        "apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier",
        mod,
    )


def _install_variable_manager(monkeypatch):
    mod = types.ModuleType("apps.opspilot.utils.chat_flow_utils.engine.core.variable_manager")

    class VariableManager:
        def __init__(self):
            self.values = {}

        def set_variable(self, key, value):
            self.values[key] = value

    mod.VariableManager = VariableManager
    monkeypatch.setitem(
        sys.modules,
        "apps.opspilot.utils.chat_flow_utils.engine.core.variable_manager",
        mod,
    )
    return VariableManager


@pytest.mark.parametrize(
    ("context", "message"),
    [
        (None, "缺少可信的流程执行上下文"),
        ({"organization_id": "x", "actor": {"username": "a", "domain": "d"}}, "流程执行组织非法"),
        ({"organization_id": 0, "actor": {"username": "a", "domain": "d"}}, "流程执行身份非法"),
        ({"organization_id": 7, "actor": "not-dict"}, "流程执行身份非法"),
        ({"organization_id": 7, "actor": {"username": "", "domain": "d"}}, "流程执行身份非法"),
        ({"organization_id": 7, "actor": {"username": "a" * 151, "domain": "d"}}, "流程执行身份非法"),
    ],
)
def test_trusted_context_rejects_invalid_execution_identity(context, message):
    with pytest.raises(ValueError, match=message):
        atoms._trusted_context({"__bklite_context": context} if context is not None else {})


def test_clean_text_enforces_type_and_size_limits():
    assert atoms._clean_text("  ok  ", label="message", maximum=10) == "ok"
    with pytest.raises(ValueError, match="必须是字符串"):
        atoms._clean_text(1, label="message", maximum=10)
    with pytest.raises(ValueError, match="超出限额"):
        atoms._clean_text("", label="message", maximum=10)
    with pytest.raises(ValueError, match="超出限额"):
        atoms._clean_text("x" * 11, label="message", maximum=10)
    assert atoms._clean_text("", label="prompt", maximum=10, required=False) == ""


def test_execute_agent_happy_path_and_failure_modes(mocker, monkeypatch):
    skill = SimpleNamespace(id=11, team=[7])
    mocker.patch.object(atoms, "_scoped_skill", return_value=skill)
    mocker.patch.object(atoms, "resolve_uploaded_agent_knowledge", return_value=[])
    _install_variable_manager(monkeypatch)
    _install_agent_node(monkeypatch, lambda *a, **k: {"message": "inspection complete"})

    result = atoms.execute_agent(
        {
            "agent_id": 11,
            "message": "inspect host",
            "prompt": "summarize",
            "memory_context": "known " + ("c" * atoms.MAX_MEMORY_CONTEXT_CHARS),
            "__bklite_context": _context(),
        }
    )
    assert result == {"message": "inspection complete"}

    _install_agent_node(monkeypatch, lambda *a, **k: {"success": False, "error_type": "Timeout"})
    with pytest.raises(ValueError, match="智能体执行失败: Timeout"):
        atoms.execute_agent({"agent_id": 11, "message": "x", "__bklite_context": _context()})

    _install_agent_node(monkeypatch, lambda *a, **k: {"message": 123})
    with pytest.raises(ValueError, match="返回结果非法"):
        atoms.execute_agent({"agent_id": 11, "message": "x", "__bklite_context": _context()})

    _install_agent_node(monkeypatch, lambda *a, **k: None)
    with pytest.raises(ValueError, match="智能体执行失败"):
        atoms.execute_agent({"agent_id": 11, "message": "x", "__bklite_context": _context()})


def test_execute_intent_classification_validates_intents_and_result(mocker, monkeypatch):
    model = SimpleNamespace(id=3)
    mocker.patch.object(atoms, "_scoped_model", return_value=model)
    _install_variable_manager(monkeypatch)
    _install_intent_node(
        monkeypatch,
        lambda *a, **k: {"intent_result": "alarm", "success": True},
    )

    result = atoms.execute_intent_classification(
        {
            "model_id": 3,
            "text": "cpu high",
            "intents": ["alarm", "question"],
            "classification_rules": "prefer alarm",
            "__bklite_context": _context(),
        }
    )
    assert result == {"intent": "alarm", "text": "cpu high"}

    with pytest.raises(ValueError, match="1 到 20 个意图"):
        atoms.execute_intent_classification({"model_id": 3, "text": "x", "intents": [], "__bklite_context": _context()})
    with pytest.raises(ValueError, match="不能重复"):
        atoms.execute_intent_classification(
            {
                "model_id": 3,
                "text": "x",
                "intents": ["alarm", "alarm"],
                "__bklite_context": _context(),
            }
        )

    _install_intent_node(monkeypatch, lambda *a, **k: {"success": False, "error_type": "Boom"})
    with pytest.raises(ValueError, match="意图分类失败: Boom"):
        atoms.execute_intent_classification({"model_id": 3, "text": "x", "intents": ["alarm"], "__bklite_context": _context()})

    _install_intent_node(monkeypatch, lambda *a, **k: {"intent_result": "other"})
    with pytest.raises(ValueError, match="未声明的意图"):
        atoms.execute_intent_classification({"model_id": 3, "text": "x", "intents": ["alarm"], "__bklite_context": _context()})


def test_memory_atoms_validate_limits_and_bind_entity_scope(mocker, monkeypatch):
    personal = SimpleNamespace(id=1, scope="personal", SCOPE_PERSONAL="personal")
    team = SimpleNamespace(id=2, scope="team", SCOPE_PERSONAL="personal")
    engine = mocker.Mock()
    engine.read.return_value = SimpleNamespace(
        context="remembered",
        raw_memories=[{"id": "m1"}, {"id": "m2"}],
        source="local",
    )
    engine.write.return_value = SimpleNamespace(success=True, memory_id="m9", event_id="e9")

    memory_entity_mod = types.ModuleType("apps.opspilot.memory.engines.base")
    memory_entity_mod.MemoryEntity = lambda **kwargs: SimpleNamespace(**kwargs)
    monkeypatch.setitem(sys.modules, "apps.opspilot.memory.engines.base", memory_entity_mod)

    registry_mod = types.ModuleType("apps.opspilot.memory.engines.registry")

    class MemoryEngineRegistry:
        @staticmethod
        def get_engine(space_id):
            return engine

    registry_mod.MemoryEngineRegistry = MemoryEngineRegistry
    monkeypatch.setitem(sys.modules, "apps.opspilot.memory.engines.registry", registry_mod)

    mocker.patch.object(
        atoms,
        "_scoped_memory_space",
        side_effect=lambda space_id, organization_id: personal if space_id == 1 else team,
    )
    mocker.patch.object(atoms, "_scoped_model", return_value=SimpleNamespace(id=5))

    read = atoms.execute_memory_read({"memory_space_id": 1, "query": "cpu", "top_k": 1, "__bklite_context": _context()})
    assert read == {"query": "cpu", "memory_context": "remembered", "count": 1, "source": "local"}
    assert engine.read.call_args.kwargs["entity"].user_id == "alice@example.com"

    written = atoms.execute_memory_write(
        {
            "memory_space_id": 2,
            "content": "host recovered",
            "title": "recovery",
            "model_id": 5,
            "write_batch_size": 10,
            "__bklite_context": _context(),
        }
    )
    assert written == {
        "content": "host recovered",
        "written": True,
        "memory_id": "m9",
        "event_id": "e9",
    }
    assert engine.write.call_args.kwargs["entity"].organization_id == 7
    assert engine.write.call_args.kwargs["model_id"] == 5

    with pytest.raises(ValueError, match="top_k"):
        atoms.execute_memory_read({"memory_space_id": 2, "query": "x", "top_k": 0, "__bklite_context": _context()})
    with pytest.raises(ValueError, match="write_batch_size"):
        atoms.execute_memory_write(
            {
                "memory_space_id": 2,
                "content": "x",
                "write_batch_size": True,
                "__bklite_context": _context(),
            }
        )

    engine.write.return_value = SimpleNamespace(success=False, memory_id=None, event_id=None)
    with pytest.raises(ValueError, match="记忆写入失败"):
        atoms.execute_memory_write({"memory_space_id": 2, "content": "x", "__bklite_context": _context()})


def test_opspilot_models_imports_when_installed(monkeypatch, mocker):
    mocker.patch.object(atoms.django_apps, "is_installed", return_value=True)
    models_mod = types.ModuleType("apps.opspilot.models")
    models_mod.LLMModel = object()
    models_mod.LLMSkill = object()
    models_mod.MemorySpace = object()
    monkeypatch.setitem(sys.modules, "apps.opspilot.models", models_mod)

    assert atoms._opspilot_models() == (models_mod.LLMModel, models_mod.LLMSkill, models_mod.MemorySpace)


def test_scoped_lookups_require_opspilot_and_team_membership(mocker):
    mocker.patch.object(atoms.django_apps, "is_installed", return_value=False)
    with pytest.raises(ValueError, match="OpsPilot 应用未启用"):
        atoms._opspilot_models()

    llm_model = mocker.Mock()
    llm_skill = mocker.Mock()
    memory_space = mocker.Mock()
    empty_qs = mocker.Mock()
    empty_qs.filter.return_value.first.return_value = None
    llm_model.objects.filter.return_value = empty_qs
    llm_skill.objects.filter.return_value = empty_qs
    memory_space.objects.all.return_value = empty_qs
    mocker.patch.object(atoms, "_opspilot_models", return_value=(llm_model, llm_skill, memory_space))
    mocker.patch(
        "apps.workflow_orchestration.services.opspilot_atoms.build_json_membership_query",
        return_value=mocker.Mock(),
    )

    with pytest.raises(ValueError, match="指定模型在当前组织不可用"):
        atoms._scoped_model(1, 7)
    with pytest.raises(ValueError, match="指定智能体在当前组织不可用"):
        atoms._scoped_skill(1, 7)
    with pytest.raises(ValueError, match="指定记忆空间在当前组织不可用"):
        atoms._scoped_memory_space(1, 7)

    empty_qs.filter.return_value.first.return_value = SimpleNamespace(team=[])
    with pytest.raises(ValueError, match="指定智能体在当前组织不可用"):
        atoms._scoped_skill(1, 7)

    empty_qs.filter.return_value.first.return_value = SimpleNamespace(id=3, team=[7])
    assert atoms._scoped_model(3, 7).id == 3
    assert atoms._scoped_skill(3, 7).id == 3
    assert atoms._scoped_memory_space(3, 7).id == 3


def test_materialize_opspilot_options_fills_enum_fields(mocker):
    mocker.patch.object(atoms.django_apps, "is_installed", return_value=False)
    catalog = {"bklite_agent": {"input_schema": {"properties": {"agent_id": {}}}}}
    atoms.materialize_opspilot_options(catalog, 7)
    assert "enum" not in catalog["bklite_agent"]["input_schema"]["properties"]["agent_id"]

    mocker.patch.object(atoms.django_apps, "is_installed", return_value=True)
    llm_model = mocker.Mock()
    llm_skill = mocker.Mock()
    memory_space = mocker.Mock()
    mocker.patch.object(atoms, "_opspilot_models", return_value=(llm_model, llm_skill, memory_space))
    mocker.patch(
        "apps.workflow_orchestration.services.opspilot_atoms.build_json_membership_query",
        return_value=mocker.Mock(),
    )

    models_qs = mocker.Mock()
    models_qs.filter.return_value.order_by.return_value.values_list.return_value = [(3, "model-a")]
    llm_model.objects.filter.return_value = models_qs

    skills_qs = mocker.Mock()
    skills_qs.filter.return_value.order_by.return_value.values_list.return_value = [(11, "agent-a")]
    llm_skill.objects.filter.return_value = skills_qs

    spaces_qs = mocker.Mock()
    spaces_qs.filter.return_value.order_by.return_value.values_list.return_value = [(21, "space-a", "team", "3")]
    memory_space.objects.all.return_value = spaces_qs

    catalog = {
        "bklite_agent": {"input_schema": {"properties": {"agent_id": {}}}},
        "bklite_intent_classification": {"input_schema": {"properties": {"model_id": {}}}},
        "bklite_memory_read": {"input_schema": {"properties": {"memory_space_id": {}}}},
        "bklite_memory_write": {"input_schema": {"properties": {"memory_space_id": {}, "model_id": {}}}},
        "other": {"input_schema": {"properties": {}}},
    }
    atoms.materialize_opspilot_options(catalog, 7)

    assert catalog["bklite_agent"]["input_schema"]["properties"]["agent_id"]["enum"] == [11]
    assert catalog["bklite_intent_classification"]["input_schema"]["properties"]["model_id"]["enum"] == [3]
    memory_field = catalog["bklite_memory_read"]["input_schema"]["properties"]["memory_space_id"]
    assert memory_field["enum"] == [21]
    assert memory_field["x-enum-metadata"]["21"] == {"scope": "team", "default_model": "3"}
    assert catalog["bklite_memory_write"]["input_schema"]["properties"]["model_id"]["enum"] == [3]


def test_enum_field_noops_when_atom_or_property_missing():
    catalog = {"missing_prop": {"input_schema": {"properties": {}}}}
    atoms._enum_field(catalog, "absent", "agent_id", [(1, "a")])
    atoms._enum_field(catalog, "missing_prop", "agent_id", [(1, "a")])
    assert catalog["missing_prop"]["input_schema"]["properties"] == {}
