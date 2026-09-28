import pytest

from apps.workflow_orchestration import nats_api
from apps.workflow_orchestration.models import Workflow, WorkflowExecution, WorkflowTrigger
from apps.workflow_orchestration.services.definitions import DefinitionValidationError
from apps.workflow_orchestration.services.nats_triggers import build_nats_trigger_subject, invoke_nats_trigger
from apps.workflow_orchestration.services.triggers import TriggerConflict, sync_published_triggers, validate_trigger_configuration


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
    execution = WorkflowExecution.objects.create(workflow=workflow, workflow_version=1, team=[7])
    invoke = mocker.patch(
        "apps.workflow_orchestration.services.nats_triggers.invoke_trigger",
        return_value=(execution, True),
    )
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
    assert invoke_nats_trigger(data, _actor(7), message_subject=subject) == (execution, True)
    assert invoke.call_args.kwargs["started_by"] == "automation-service"
    assert invoke.call_args.kwargs["idempotency_key"] == "event-from-input"
    with pytest.raises(TriggerConflict, match="授权组织"):
        invoke_nats_trigger({**data, "team": 8}, _actor(7), message_subject=subject)
    with pytest.raises(TriggerConflict, match="主题"):
        invoke_nats_trigger(data, _actor(7), message_subject="bklite.workflow.999.trigger_nats")
    assert invoke.call_count == 1


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
        "apps.workflow_orchestration.nats_api.invoke_nats_trigger",
        side_effect=RuntimeError(sentinel),
    )
    logger = mocker.patch("apps.workflow_orchestration.nats_api.logger")

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
