from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import Channel, ChannelChoices, Group, Menu, Role, User
from apps.workflow.models import Workflow, WorkflowExecution
from apps.workflow.services.triggers import run_due_cron_triggers
from apps.workflow.views import WorkflowViewSet

pytestmark = pytest.mark.django_db


@pytest.fixture
def scheduled_workflow(mocker):
    for group_id in (7, 8, 9):
        Group.objects.create(id=group_id, name=f"org-{group_id}")
    menu = Menu.objects.create(app="workflow", name="workflow-Execute")
    role = Role.objects.create(app="workflow", name="runner", menu_list=[menu.pk])
    account = User.objects.create(username="publisher", domain="example.com", group_list=[7, 8], role_list=[role.pk])
    operator = get_user_model().objects.create(username=account.username, domain=account.domain, group_list=[7, 8])
    operator.permission = {"workflow": {"workflow-Publish", "workflow-Execute"}}
    rules = mocker.patch("apps.workflow.permissions.get_permission_rules", return_value={"team": [7]})
    channel = Channel.objects.create(name="通知", channel_type=ChannelChoices.EMAIL, config={}, team=[7])
    workflow = Workflow.objects.create(
        name="定时身份",
        team=[7],
        definition={
            "tasks": [
                {
                    "type": "SIMPLE",
                    "name": "bklite_notification",
                    "taskReferenceName": "notify",
                    "inputParameters": {
                        "notification_type": "EMAIL",
                        "channel_id": channel.pk,
                        "recipients": [str(account.pk)],
                        "title": "通知",
                        "body": "巡检",
                    },
                }
            ]
        },
        canvas_metadata={
            "trigger_nodes": [
                {
                    "id": "clock",
                    "name": "定时",
                    "trigger_type": "SCHEDULE",
                    "input_schema": {"type": "object", "properties": {}},
                    "config": {"expression": "* * * * *", "execution_team_id": 8, "execution_username": "forged"},
                }
            ],
            "edges": [{"source": "clock", "target": "notify"}],
        },
    )
    mocker.patch("apps.workflow.views.ConductorClient")
    conductor = mocker.patch("apps.workflow.services.triggers.ConductorClient").return_value
    conductor.start_workflow.return_value = "engine-scheduled"
    return workflow, operator, account, rules, conductor


def _action(workflow, user, name, data=None, **headers):
    request = APIRequestFactory().post(f"/workflows/{workflow.pk}/{name}/", data or {}, format="json", **headers)
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=user)
    return WorkflowViewSet.as_view({"post": name})(request, pk=workflow.pk)


@pytest.mark.parametrize("selected_team", [7, 8])
def test_publish_and_dispatch_schedule_binds_real_publisher_and_selected_team(scheduled_workflow, selected_team):
    workflow, operator, _, _, conductor = scheduled_workflow
    if selected_team == 7:
        workflow.canvas_metadata["trigger_nodes"][0]["config"].pop("execution_team_id")
        workflow.save()
    response = _action(workflow, operator, "publish")
    assert response.status_code == 200, response.data
    config = workflow.versions.get().canvas_metadata["trigger_nodes"][0]["config"]
    assert (config["execution_username"], config["execution_team_id"]) == ("publisher", selected_team)
    other = get_user_model().objects.create(username="enabler", domain="other.test", is_superuser=True)
    for enabled in (False, True):
        assert _action(workflow, other, "set_enabled", {"enabled": enabled}).status_code == 200
    now = timezone.now()
    workflow.triggers.update(next_run_at=now)
    assert run_due_cron_triggers(now=now)["succeeded"] == 1
    run = WorkflowExecution.objects.get(workflow=workflow)
    assert (run.started_by, run.domain, run.team) == ("publisher", "example.com", [7])
    assert run.execution_team_id == selected_team
    assert run.caller_identity == {"username": "publisher", "domain": "example.com", "team_id": selected_team, "include_children": False}
    workflow.triggers.update(next_run_at=now)
    assert run_due_cron_triggers(now=now)["skipped"] == 1
    conductor.start_workflow.assert_called_once()


@pytest.mark.parametrize("change", ["disabled", "expired", "removed", "lost_owner_team", "archived", "lost_operate", "lost_execute"])
def test_due_schedule_rechecks_account_and_both_scopes(scheduled_workflow, change):
    workflow, operator, account, rules, conductor = scheduled_workflow
    response = _action(workflow, operator, "publish")
    assert response.status_code == 200, response.data
    if change == "disabled":
        account.disabled = True
    elif change == "expired":
        account.account_expires_at = timezone.now() - timedelta(hours=1)
    elif change == "removed":
        account.group_list = [7]
    elif change == "lost_owner_team":
        account.group_list = [8]
    elif change == "archived":
        Group.objects.filter(pk=8).update(is_delete=True)
    elif change == "lost_operate":
        rules.return_value = {"team": []}
    else:
        account.role_list = []
    account.save()
    now = timezone.now()
    workflow.triggers.update(next_run_at=now)
    assert run_due_cron_triggers(now=now)["failed"] == 1
    assert not workflow.executions.exists()
    conductor.start_workflow.assert_not_called()


@pytest.mark.parametrize("selected_team", [9, [7, 8], True, 0])
def test_publish_rejects_unavailable_or_invalid_execution_team(scheduled_workflow, selected_team):
    workflow, operator, *_ = scheduled_workflow
    workflow.canvas_metadata["trigger_nodes"][0]["config"]["execution_team_id"] = selected_team
    workflow.save()
    response = _action(workflow, operator, "publish")
    assert response.status_code in (400, 403), response.data
    assert not workflow.versions.exists()


def test_republication_between_schedule_scan_and_claim_preserves_new_tick(scheduled_workflow, mocker):
    workflow, operator, _, _, conductor = scheduled_workflow
    assert _action(workflow, operator, "publish").status_code == 200
    now = timezone.now()
    workflow.triggers.update(next_run_at=now)
    from apps.workflow.services.schedules import build_schedule_event

    def republish(config, **kwargs):
        assert _action(workflow, operator, "publish").status_code == 200
        workflow.triggers.update(next_run_at=now)
        return build_schedule_event(config, **kwargs)

    mocker.patch("apps.workflow.services.triggers.build_schedule_event", side_effect=republish)
    assert run_due_cron_triggers(now=now) == {"succeeded": 0, "skipped": 1, "failed": 0}
    assert workflow.triggers.get().next_run_at == now
    conductor.start_workflow.assert_not_called()


def test_manual_schedule_invoke_cannot_consume_an_automatic_tick(scheduled_workflow):
    from apps.workflow.views import WorkflowTriggerViewSet

    workflow, operator, _, _, conductor = scheduled_workflow
    assert _action(workflow, operator, "publish").status_code == 200
    trigger = workflow.triggers.get()
    request = APIRequestFactory().post(
        f"/triggers/{trigger.pk}/invoke/", {"idempotency_key": f"cron:{trigger.next_run_at.isoformat()}"}, format="json"
    )
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=operator)
    response = WorkflowTriggerViewSet.as_view({"post": "invoke"})(request, pk=trigger.pk)
    assert response.status_code == 400
    assert not workflow.executions.exists()
    assert run_due_cron_triggers(now=trigger.next_run_at)["succeeded"] == 1
    assert workflow.executions.get().execution_team_id == 8
    conductor.start_workflow.assert_called_once()


@pytest.mark.parametrize("team_id,expected_status", [(8, 201), (9, 403)])
def test_debug_schedule_uses_testers_selected_organization(scheduled_workflow, mocker, team_id, expected_status):
    workflow, operator, *_ = scheduled_workflow
    workflow.canvas_metadata["trigger_nodes"][0]["config"]["execution_team_id"] = team_id
    workflow.save()
    mocker.patch("apps.workflow.views.ConductorClient").return_value.start_workflow.return_value = "debug-schedule"
    response = _action(workflow, operator, "debug", {"trigger_id": "clock"})
    assert response.status_code == expected_status, response.data
    if expected_status == 201:
        run = workflow.executions.get()
        assert run.execution_team_id == team_id
        assert run.caller_identity == {"username": operator.username, "domain": operator.domain, "team_id": team_id, "include_children": False}
    else:
        assert not workflow.executions.exists()


@pytest.mark.skipif(not django_apps.is_installed("apps.opspilot"), reason="需要 OpsPilot 智能体")
@pytest.mark.parametrize(
    "entry,page_locale,account_locale,expected",
    [
        ("run", "cn", "en", "zh-Hans"),
        ("run", "en", "zh-Hans", "en"),
        ("debug", "zh-CN", "en", "zh-Hans"),
        ("debug", "en-US", "zh-Hans", "en"),
        ("debug", None, "en", "en"),
        ("debug", None, "", "zh-Hans"),
        ("schedule", None, "en", "en"),
        ("schedule", None, "cn", "zh-Hans"),
        ("schedule", None, "", "zh-Hans"),
    ],
)
def test_agent_reply_language_at_model_boundary(scheduled_workflow, mocker, entry, page_locale, account_locale, expected):
    from apps.opspilot.models import LLMModel, LLMSkill
    from apps.opspilot.models.model_provider_mgmt import ModelVendor
    from apps.opspilot.services.chat_service import ChatService
    from apps.workflow.management.commands.run_workflow_worker import _build_runtime_inputs
    from apps.workflow.services.opspilot_atoms import execute_agent

    workflow, publisher, account, *_ = scheduled_workflow
    vendor = ModelVendor.objects.create(name="vendor", vendor_type="openai", team=[7], enabled=True)
    model = LLMModel.objects.create(name="model", enabled=True, team=[7], vendor=vendor)
    skill = LLMSkill.objects.create(name="agent", llm_model=model, team=[7], usage_team=[7, 8])
    inputs = {"agent_id": skill.id, "message": "查询活动告警"}
    workflow.definition = {"tasks": [{"name": "bklite_agent", "taskReferenceName": "agent", "type": "SIMPLE", "inputParameters": inputs}]}
    workflow.canvas_metadata["edges"] = [{"source": "clock", "target": "agent"}]
    workflow.save()
    assert _action(workflow, publisher, "publish").status_code == 200
    if entry == "schedule":
        # 调度取触发时的偏好，发布之后仍可切换。
        account.locale = account_locale
        account.save(update_fields=["locale"])
        assert run_due_cron_triggers(now=workflow.triggers.get().next_run_at)["succeeded"] == 1
        account.locale = "zh-Hans" if expected == "en" else "en"
        account.save(update_fields=["locale"])
    else:
        operator = get_user_model().objects.create(username="tester", domain=account.domain, group_list=[7, 8], is_superuser=True)
        operator.locale = account_locale
        headers = {"HTTP_X_BK_LOCALE": page_locale} if page_locale else {}
        if entry == "run":
            request = APIRequestFactory().get("/launch-plan/")
            request.COOKIES["current_team"] = "7"
            force_authenticate(request, user=operator)
            plan = WorkflowViewSet.as_view({"get": "launch_plan"})(request, pk=workflow.pk)
            data = {"launch_token": plan.data["launch_token"]}
        else:
            data = {"trigger_id": "clock"}
        mocker.patch("apps.workflow.views.ConductorClient").return_value.start_workflow.return_value = "engine-manual"
        response = _action(workflow, operator, entry, data, **headers)
        assert response.status_code == 201, response.data
    execution = workflow.executions.get()
    payload = _build_runtime_inputs(inputs=inputs, atom_execution=None, task_type="bklite_agent", execution=execution)
    mocker.patch("apps.opspilot.services.chat_service.consume_pending_question", return_value=None)
    chat = mocker.patch.object(ChatService, "invoke_chat", return_value=({"success": True, "message": "ok"}, None, None))
    execute_agent(payload)
    formatted, _, _ = ChatService.format_chat_server_kwargs(chat.call_args.args[0], model)
    instruction = "Reply in English." if expected == "en" else "请用简体中文回复"
    assert instruction in formatted["system_message_prompt"]


@pytest.mark.skipif(not django_apps.is_installed("apps.opspilot"), reason="需要 OpsPilot 工具与记忆引擎")
def test_scheduled_agent_and_memory_use_recorded_account_and_selected_team(scheduled_workflow, mocker):
    from apps.opspilot.memory.engines.base import MemoryReadResult, MemoryWriteResult
    from apps.opspilot.metis.llm.tools.job_mgmt import job_mgmt_list_executions
    from apps.opspilot.models import LLMModel, LLMSkill, MemorySpace
    from apps.opspilot.models.model_provider_mgmt import ModelVendor
    from apps.opspilot.services.chat_service import ChatService
    from apps.workflow.management.commands.run_workflow_worker import _build_runtime_inputs
    from apps.workflow.serializers import WorkflowExecutionListSerializer, WorkflowExecutionSerializer
    from apps.workflow.services.opspilot_atoms import execute_agent, execute_memory_read, execute_memory_write

    owner_team, selected_team = 7, 8
    workflow, operator, *_ = scheduled_workflow
    vendor = ModelVendor.objects.create(name="on", vendor_type="openai", team=[owner_team], enabled=True)
    model = LLMModel.objects.create(name="model", enabled=True, team=[owner_team, selected_team], vendor=vendor)
    skill = LLMSkill.objects.create(name="shared", llm_model=model, team=[owner_team], usage_team=[owner_team, selected_team])
    workflow.definition = {
        "tasks": [
            {"name": "bklite_agent", "taskReferenceName": "agent", "type": "SIMPLE", "inputParameters": {"agent_id": skill.pk, "message": "执行历史"}}
        ]
    }
    workflow.canvas_metadata["edges"] = [{"source": "clock", "target": "agent"}]
    workflow.save()
    response = _action(workflow, operator, "publish")
    assert response.status_code == 200, response.data
    assert run_due_cron_triggers(now=workflow.triggers.get().next_run_at)["succeeded"] == 1
    execution = workflow.executions.get()
    assert execution.team == [owner_team]
    for serializer in (WorkflowExecutionListSerializer, WorkflowExecutionSerializer):
        record = serializer(execution).data
        assert (record["started_by"], record["execution_team_id"]) == (operator.username, selected_team)
    assert execution.input["__system"]["organization_id"] == str(selected_team)

    def payload(atom, **fields):
        return _build_runtime_inputs(
            inputs={**fields, "__bklite_context": {"organization_id": owner_team, "actor": {"username": "other"}}},
            atom_execution=None,
            task_type=atom,
            execution=execution,
        )

    rpc = mocker.patch("apps.opspilot.services.job_tool_service._call", return_value={"success": True, "data": {"items": []}})
    mocker.patch("apps.opspilot.services.chat_service.consume_pending_question", return_value=None)

    def invoke(params):
        formatted, _, _ = ChatService.format_chat_server_kwargs(params, model)
        job_mgmt_list_executions.invoke({}, config={"configurable": formatted["extra_config"]})
        return {"success": True, "message": "done"}, None, None

    mocker.patch.object(ChatService, "invoke_chat", side_effect=invoke)
    execute_agent(payload("bklite_agent", agent_id=skill.id, message="执行历史"))
    assert rpc.call_args.args[1] == {"user": operator.username, "domain": operator.domain, "team": selected_team, "include_children": False}

    engine = mocker.patch("apps.opspilot.memory.engines.registry.MemoryEngineRegistry.get_engine").return_value
    engine.read.return_value = MemoryReadResult(context="ok")
    engine.write.return_value = MemoryWriteResult(success=True)
    for scope, entity in [
        (MemorySpace.SCOPE_TEAM, {"organization_id": selected_team}),
        (MemorySpace.SCOPE_PERSONAL, {"user_id": f"{operator.username}@{operator.domain}"}),
    ]:
        space = MemorySpace.objects.create(name=scope, team=[selected_team], scope=scope)
        execute_memory_read(payload("bklite_memory_read", memory_space_id=space.id, query="巡检"))
        execute_memory_write(payload("bklite_memory_write", memory_space_id=space.id, content="完成"))
        assert engine.read.call_args.kwargs["entity"].to_dict() == engine.write.call_args.kwargs["entity"].to_dict() == entity
    inaccessible = MemorySpace.objects.create(name="只在原组织可用", team=[owner_team])
    with pytest.raises(ValueError, match="当前组织不可用"):
        execute_memory_read(payload("bklite_memory_read", memory_space_id=inaccessible.id, query="巡检"))
