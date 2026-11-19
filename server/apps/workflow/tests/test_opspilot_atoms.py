import pytest
from django.apps import apps as django_apps

from apps.workflow.services.atom_registry import available_atom_catalog
from apps.workflow.services.opspilot_atoms import (
    _scoped_skill,
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
    from apps.opspilot.models.model_provider_mgmt import ModelVendor


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
@pytest.mark.parametrize(
    "trigger_type,message,expected,approval_trigger",
    [
        ("SCHEDULE", "检查告警", True, "unattended"),
        ("NATS", "检查告警", True, "unattended"),
        ("WEBHOOK", "检查告警", True, "unattended"),
        ("FORM", "检查告警", False, "interactive"),
        ("FORM", "/auto 检查告警", True, "interactive"),
    ],
)
def test_workflow_agent_runs_with_trigger_appropriate_auto_mode(mocker, trigger_type, message, expected, approval_trigger):
    from apps.opspilot.services.chat_service import ChatService

    vendor = ModelVendor.objects.create(name="on", vendor_type="openai", team=[7], enabled=True)
    model = LLMModel.objects.create(name="auto-model", enabled=True, team=[7], vendor=vendor)
    skill = LLMSkill.objects.create(name="auto-agent", llm_model=model, team=[7], usage_team=[7])
    mocker.patch("apps.workflow.services.opspilot_atoms.resolve_uploaded_agent_knowledge", return_value=[])
    mocker.patch("apps.opspilot.services.chat_service.consume_pending_question", return_value=None)
    seen = {}

    def invoke(params):
        formatted, _, _ = ChatService.format_chat_server_kwargs(params, model)
        seen.update(formatted.get("extra_config") or {})
        return {"success": True, "message": "处理完成"}, None, None

    mocker.patch.object(ChatService, "invoke_chat", side_effect=invoke)
    context = {**_context(), "trigger_type": trigger_type, "task_reference": "agent-a"}
    result = execute_agent({"agent_id": skill.id, "message": message, "prompt": "附加提示", "__bklite_context": context})
    assert result == {"message": "处理完成"}
    assert seen.get("unattended", False) is expected
    assert seen["trigger_type"] == approval_trigger


@pytest.mark.django_db
@pytest.mark.skipif(not django_apps.is_installed("apps.alerts"), reason="需要告警中心查询处理器")
@pytest.mark.parametrize("action", ["run", "debug", "node_debug"])
def test_workflow_agent_queries_active_alerts_as_execution_caller(mocker, action):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.alerts.constants.constants import AlertStatus, SessionStatus
    from apps.alerts.models.models import Alert
    from apps.alerts.nats.nats import list_alerts
    from apps.opspilot.metis.llm.tools.alerts import alerts_list_alerts
    from apps.opspilot.services.chat_service import ChatService
    from apps.system_mgmt.models.role import Role
    from apps.system_mgmt.models.user import User
    from apps.workflow.management.commands.run_workflow_worker import _build_runtime_inputs
    from apps.workflow.models import Workflow, WorkflowExecution, WorkflowVersion
    from apps.workflow.views import WorkflowViewSet

    vendor = ModelVendor.objects.create(name="on", vendor_type="openai", team=[7], enabled=True)
    model = LLMModel.objects.create(name="alert-model", enabled=True, team=[7], vendor=vendor)
    skill = LLMSkill.objects.create(name="shared-agent", llm_model=model, team=[99], usage_team=[7])
    mocker.patch("apps.opspilot.services.chat_service.consume_pending_question", return_value=None)
    rpc = mocker.patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc").return_value.list_alerts
    rpc.side_effect = list_alerts
    role, _ = Role.objects.get_or_create(name="admin", app="system-manager")
    User.objects.create(username="alice", domain="example.com", role_list=[role.pk])
    for team_id in (7, 99):
        Alert.objects.create(
            alert_id=f"ALERT-{team_id}",
            team=[team_id],
            title="CPU 告警",
            status=AlertStatus.UNASSIGNED,
            session_status=SessionStatus.CONFIRMED,
            fingerprint=f"fp-{team_id}",
            level="warning",
        )
    tool_results = []

    def invoke(params):
        formatted, _, _ = ChatService.format_chat_server_kwargs(params, model)
        tool_results.append(alerts_list_alerts.invoke({"status": "active"}, config={"configurable": formatted["extra_config"]}))
        return {"success": True, "message": "完成"}, None, None

    mocker.patch.object(ChatService, "invoke_chat", side_effect=invoke)
    inputs = {"agent_id": skill.id, "message": "查询活动告警"}
    definition = {"tasks": [{"name": "bklite_agent", "taskReferenceName": "agent", "type": "SIMPLE", "inputParameters": inputs}]}
    workflow = Workflow.objects.create(
        name="告警查询", team=[7], definition=definition, current_version=1, status=Workflow.Status.PUBLISHED, enabled=True
    )
    WorkflowVersion.objects.create(workflow=workflow, version=1, definition=definition)
    operator = get_user_model().objects.create(username="alice", domain="example.com", group_list=[{"id": 7}], is_superuser=True)
    conductor = mocker.patch("apps.workflow.views.ConductorClient").return_value
    conductor.start_workflow.return_value = "engine-run"

    def request_action(method, name, data=None):
        path = f"/workflows/{workflow.pk}/{name}/"
        request = getattr(APIRequestFactory(), method)(path, data or {}, format="json")
        request.COOKIES.update(current_team="7", include_children="1")
        force_authenticate(request, user=operator)
        return WorkflowViewSet.as_view({method: name})(request, pk=workflow.pk)

    if action == "run":
        plan = request_action("get", "launch_plan")
        response = request_action("post", "run", {"launch_token": plan.data["launch_token"]})
    else:
        debug_inputs = {"task_reference": "agent", "confirmed": True} if action == "node_debug" else {}
        response = request_action("post", "debug", debug_inputs)
    assert response.status_code == 201, response.data
    execution = WorkflowExecution.objects.get(pk=response.data["id"])
    inputs = {**inputs, "__bklite_context": {"caller_identity": {"username": "untrusted", "team_id": 99}}}
    execute_agent(_build_runtime_inputs(inputs=inputs, atom_execution=None, task_type="bklite_agent", execution=execution))
    assert tool_results[0]["success"], tool_results[0].get("error")
    assert [row["alert_id"] for row in tool_results[0]["data"]["items"]] == ["ALERT-7"]
    assert rpc.call_args.kwargs["user_info"] == {"user": "alice", "domain": "example.com", "team": 7, "include_children": False}


@pytest.mark.django_db
def test_workflow_agent_forwards_supplied_caller_identity_and_does_not_invent_one(mocker):
    from apps.opspilot.services.chat_service import ChatService

    vendor = ModelVendor.objects.create(name="on", vendor_type="openai", team=[7], enabled=True)
    model = LLMModel.objects.create(name="identity-model", enabled=True, team=[7], vendor=vendor)
    skill = LLMSkill.objects.create(name="identity-agent", llm_model=model, team=[7], usage_team=[7])
    mocker.patch("apps.workflow.services.opspilot_atoms.resolve_uploaded_agent_knowledge", return_value=[])
    mocker.patch("apps.opspilot.services.chat_service.consume_pending_question", return_value=None)
    captured = {}

    def invoke(params):
        captured.clear()
        captured.update(params)
        return {"success": True, "message": "处理完成"}, None, None

    mocker.patch.object(ChatService, "invoke_chat", side_effect=invoke)
    snapshot = {
        "username": "dave",
        "domain": "hook.example",
        "team_id": 7,
        "include_children": False,
    }
    execute_agent(
        {
            "agent_id": skill.id,
            "message": "统计告警",
            "__bklite_context": {
                **_context(),
                "trigger_type": "WEBHOOK",
                "caller_identity": snapshot,
                "locale": "zh-Hans",
            },
        }
    )
    assert captured["caller_identity"] == snapshot
    assert captured["locale"] == "zh-Hans"

    execute_agent(
        {
            "agent_id": skill.id,
            "message": "统计告警",
            "__bklite_context": {**_context(), "trigger_type": "WEBHOOK"},
        }
    )
    assert "caller_identity" not in captured
    assert captured["locale"] == "en"


@pytest.mark.django_db
def test_workflow_agent_history_separates_distinct_nodes(mocker):
    from apps.opspilot.models import SkillConversation
    from apps.opspilot.services.chat_service import ChatService
    from apps.opspilot.services.skill_channel_chat_service import list_skill_conversations_for_admin

    vendor = ModelVendor.objects.create(name="on", vendor_type="openai", team=[7], enabled=True)
    model = LLMModel.objects.create(name="history-model", enabled=True, team=[7], vendor=vendor)
    skill = LLMSkill.objects.create(name="history-agent", llm_model=model, team=[7], usage_team=[7])
    mocker.patch("apps.workflow.services.opspilot_atoms.resolve_uploaded_agent_knowledge", return_value=[])
    mocker.patch.object(ChatService, "invoke_chat", return_value=({"success": True, "message": "完成"}, None, None))
    for node in ("agent-a", "agent-b"):
        context = {**_context(), "task_reference": node}
        execute_agent({"agent_id": skill.id, "message": f"查询 {node}", "__bklite_context": context})
    data = list_skill_conversations_for_admin(skill_id=skill.id)
    assert data["count"] == 2
    assert all(row["channel_type"] == "workflow" for row in data["items"])
    assert SkillConversation.objects.filter(skill=skill).count() == 2
    assert sorted(row["title"] for row in data["items"]) == ["查询 agent-a", "查询 agent-b"]


@pytest.mark.django_db
def test_agent_and_intent_atoms_reuse_opspilot_nodes_with_clean_contract(mocker):
    vendor = ModelVendor.objects.create(name="on", vendor_type="openai", team=[7], enabled=True)
    model = LLMModel.objects.create(name="classification-model", enabled=True, team=[7], vendor=vendor)
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
        "apps.workflow.services.opspilot_atoms.resolve_uploaded_agent_knowledge",
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
    assert agent_execute.call_args.args[0] == "workflow_agent"
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
    vendor = ModelVendor.objects.create(name="on", vendor_type="openai", team=[8], enabled=True)
    model = LLMModel.objects.create(name="other-model", enabled=True, team=[8], vendor=vendor)
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
    vendor = ModelVendor.objects.create(name="on", vendor_type="openai", team=[7], enabled=True)
    disabled_vendor = ModelVendor.objects.create(name="off", vendor_type="openai", team=[7], enabled=False)
    own_model = LLMModel.objects.create(name="own-model", enabled=True, team=[7], vendor=vendor)
    LLMModel.objects.create(name="disabled-model", enabled=False, team=[7], vendor=vendor)
    vendor_off_model = LLMModel.objects.create(name="vendor-off", enabled=True, team=[7], vendor=disabled_vendor)
    other_model = LLMModel.objects.create(name="other-model", enabled=True, team=[8], vendor=vendor)
    own_skill = LLMSkill.objects.create(name="own-agent", llm_model=own_model, team=[7], usage_team=[7])
    LLMSkill.objects.create(name="vendor-off-agent", llm_model=vendor_off_model, team=[7], usage_team=[7])
    LLMSkill.objects.create(name="other-agent", llm_model=other_model, team=[8], usage_team=[8])
    own_space = MemorySpace.objects.create(name="own-memory", team=[7], default_model=str(own_model.id))
    MemorySpace.objects.create(name="other-memory", team=[8])
    from apps.system_mgmt.models import User

    member = User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        password="x",
        group_list=[7],
    )
    User.objects.create(
        username="bob",
        display_name="Bob",
        email="bob@example.com",
        password="x",
        group_list=[8],
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
    assert "vendor-off-agent" not in agent_field["x-enum-labels"].values()


@pytest.mark.django_db
def test_agent_bound_to_disabled_vendor_is_rejected_before_execution(mocker):
    enabled_vendor = ModelVendor.objects.create(name="on", vendor_type="openai", team=[7], enabled=True)
    disabled_vendor = ModelVendor.objects.create(name="off", vendor_type="openai", team=[7], enabled=False)
    enabled_model = LLMModel.objects.create(name="keep-model", enabled=True, team=[7], vendor=enabled_vendor)
    disabled_vendor_model = LLMModel.objects.create(name="vendor-off", enabled=True, team=[7], vendor=disabled_vendor)
    available_skill = LLMSkill.objects.create(name="own-agent", llm_model=enabled_model, team=[7], usage_team=[7])
    blocked_skill = LLMSkill.objects.create(name="vendor-off-agent", llm_model=disabled_vendor_model, team=[7], usage_team=[7])
    agent_execute = mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.nodes.agent.agent.AgentNode.execute",
        return_value={"message": "should not run"},
    )

    with pytest.raises(ValueError, match="指定智能体在当前组织不可用"):
        _scoped_skill(blocked_skill.id, 7)
    with pytest.raises(ValueError, match="指定智能体在当前组织不可用"):
        execute_agent({"agent_id": blocked_skill.id, "message": "inspect", "__bklite_context": _context()})
    agent_execute.assert_not_called()

    assert _scoped_skill(available_skill.id, 7).id == available_skill.id
    catalog = available_atom_catalog(7)
    agent_ids = catalog["bklite_agent"]["input_schema"]["properties"]["agent_id"]["enum"]
    assert agent_ids == [available_skill.id]
