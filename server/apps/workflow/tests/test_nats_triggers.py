import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from rest_framework.exceptions import PermissionDenied

from apps.rpc.workflow import invoke_nats_workflow
from apps.system_mgmt.models.channel import Channel
from apps.system_mgmt.nats.channels import sync_workflow_nats_channels
from apps.system_mgmt.utils.channel_utils import send_nats_message
from apps.workflow import nats_api
from apps.workflow.models import Workflow, WorkflowExecution, WorkflowTrigger, WorkflowVersion
from apps.workflow.services.definitions import DefinitionValidationError
from apps.workflow.services.nats_contracts import build_nats_trigger_subject
from apps.workflow.services.nats_triggers import invoke_nats_trigger
from apps.workflow.services.triggers import TriggerConflict, sync_published_triggers, validate_trigger_configuration


def _actor(*teams):
    return {
        "authorized_team_ids": list(teams),
        "username": "automation-service",
        "domain": "example.com",
    }


@pytest.mark.django_db
def test_nats_adapter_enforces_actor_team_and_generated_subject_before_invoking(mocker):
    workflow = Workflow.objects.create(
        name="NATS 流程",
        team=[7],
        definition={"tasks": []},
        current_version=1,
        status=Workflow.Status.PUBLISHED,
        enabled=True,
    )
    trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        name="告警入口",
        trigger_type=WorkflowTrigger.Type.NATS,
        enabled=True,
        team=[7],
        node_key="trigger_nats",
        config={"subject": build_nats_trigger_subject(workflow.id, "trigger_nats")},
    )
    WorkflowVersion.objects.create(workflow=workflow, version=1, definition={"tasks": []})
    engine = mocker.patch("apps.workflow.services.triggers.ConductorClient").return_value
    engine.start_workflow.side_effect = ["nats-user-run", "nats-service-run"]
    rules = mocker.patch("apps.workflow.permissions.get_permission_rules", return_value={"team": [7], "instance": []})
    data = {
        "trigger_id": str(trigger.pk),
        "team": 7,
        "event": {
            "event_id": "event-from-input",
            "occurred_at": "2026-09-17T10:00:00Z",
            "producer": "monitoring",
            "payload": {"message": "disk full"},
        },
    }

    subject = build_nats_trigger_subject(workflow.id, "trigger_nats")

    request = RequestFactory().post("/")
    request.COOKIES["current_team"] = "7"
    request.user = get_user_model().objects.create(username="alice", domain="example.com", group_list=[7])
    request.user.permission = {"workflow": {"workflow-Execute"}}

    def deliver(method, **params):
        assert method == "trigger_orchestration_workflow_by_nats"
        return nats_api.trigger_orchestration_workflow_by_nats(**params)

    transport = mocker.patch("apps.rpc.workflow.RpcClient.run", side_effect=deliver)
    result = invoke_nats_workflow(request, trigger_id=trigger.id, subject=subject, event=data["event"])
    assert result["result"], result
    execution = WorkflowExecution.objects.get(pk=result["data"]["execution_id"])
    assert execution.caller_identity == {"username": "alice", "domain": "example.com", "team_id": 7, "include_children": False}
    assert (execution.started_by, execution.domain) == ("alice", "example.com")
    params = transport.call_args.kwargs
    tampered = {**params["data"], "event": {**data["event"], "event_id": "other"}}
    assert nats_api.trigger_orchestration_workflow_by_nats(**{**params, "data": tampered})["result"] is False
    assert nats_api.trigger_orchestration_workflow_by_nats(params["data"], params["actor_context"])["result"] is False
    rules.return_value = {"team": [], "instance": []}
    assert invoke_nats_workflow(request, trigger_id=trigger.id, subject=subject, event=data["event"])["result"] is False
    request.user.permission = {}
    with pytest.raises(PermissionDenied):
        invoke_nats_workflow(request, trigger_id=trigger.id, subject=subject, event=data["event"])

    background = {**tampered, "subject": subject}
    background["event"]["payload"] = {"caller_identity": execution.caller_identity, "producer": "alice"}
    system_actor = {**_actor(7), "username": "managed-nats-channel", "domain": "domain.com"}
    assert nats_api.trigger_orchestration_workflow_by_nats(background, system_actor)["result"] is False
    sync_workflow_nats_channels(
        workflow.id,
        workflow.name,
        [7],
        [{"trigger_id": str(trigger.id), "node_key": trigger.node_key, "name": trigger.name, "subject": subject}],
        True,
    )
    channel = Channel.objects.get(config__source="workflow", config__workflow_id=workflow.id)

    def send_managed(namespace, method, _timeout, **body):
        return deliver(method, **body)

    mocker.patch("apps.system_mgmt.utils.channel_utils.nats_client.request_sync", side_effect=send_managed)
    result = send_nats_message(
        channel,
        {
            "message": "background event",
            "team": 7,
            "caller_identity": execution.caller_identity,
            "producer": "alice",
            "user_ids": ["alice"],
        },
    )
    assert result["result"], result
    background_run = WorkflowExecution.objects.get(pk=result["data"]["execution_id"])
    assert background_run.started_by == "managed-nats-channel" and background_run.caller_identity is None
    with pytest.raises(TriggerConflict, match="授权组织"):
        invoke_nats_trigger({**data, "team": 8}, _actor(7), message_subject=subject)
    with pytest.raises(TriggerConflict, match="主题"):
        invoke_nats_trigger(data, _actor(7), message_subject="bklite.workflow.999.trigger_nats")
    assert WorkflowExecution.objects.count() == 2


def test_nats_configuration_and_payload_are_bounded():
    validate_trigger_configuration(WorkflowTrigger.Type.NATS, {})
    with pytest.raises(DefinitionValidationError, match="不需要配置"):
        validate_trigger_configuration(WorkflowTrigger.Type.NATS, {"channel_key": "alerts.workflow"})
    with pytest.raises(DefinitionValidationError, match="1 MiB"):
        invoke_nats_trigger(
            {
                "trigger_id": "00000000-0000-0000-0000-000000000001",
                "team": 7,
                "event": {
                    "event_id": "large",
                    "occurred_at": "2026-09-17T10:00:00Z",
                    "producer": "test",
                    "payload": {"message": "x" * (1024 * 1024)},
                },
            },
            _actor(7),
            message_subject="bklite.workflow.7.trigger_nats",
        )


@pytest.mark.django_db
def test_publishing_nats_trigger_generates_stable_subject_without_draft_configuration():
    workflow = Workflow.objects.create(name="NATS 流程", team=[7], definition={"tasks": []})

    sync_published_triggers(
        workflow,
        {
            "trigger_nodes": [
                {
                    "id": "trigger_nats",
                    "name": "事件入口",
                    "trigger_type": "NATS",
                    "input_schema": {},
                    "config": {},
                }
            ],
        },
        username="admin",
        domain="example.com",
    )

    trigger = WorkflowTrigger.objects.get(workflow=workflow, node_key="trigger_nats")
    assert trigger.config == {"subject": f"bklite.workflow.{workflow.id}.trigger_nats"}


def test_nats_rpc_boundary_hides_unbounded_errors_and_keeps_stable_log(mocker):
    sentinel = "SENSITIVE-NATS-PAYLOAD"
    mocker.patch(
        "apps.workflow.nats_api.invoke_nats_trigger",
        side_effect=RuntimeError(sentinel),
    )
    logger = mocker.patch("apps.workflow.nats_api.logger")

    result = nats_api.trigger_orchestration_workflow_by_nats(
        {"inputs": {"secret": sentinel}},
        _actor(7),
    )

    assert result == {"result": False, "message": "编排服务暂不可用"}
    logger.error.assert_called_once()
    template, error_type = logger.error.call_args.args
    assert "%s" in template
    assert error_type == "RuntimeError"
    assert sentinel not in template
    assert sentinel not in str(logger.error.call_args.kwargs["exc_info"][1])
