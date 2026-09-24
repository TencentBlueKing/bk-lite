import pytest
from django.utils import timezone

from apps.workflow_orchestration.models import Workflow, WorkflowTrigger
from apps.workflow_orchestration.services.managed_nats_channels import delete_workflow_nats_channels, sync_workflow_nats_channels


@pytest.mark.django_db
def test_sync_workflow_nats_channels_projects_runtime_trigger(mocker):
    workflow = Workflow.objects.create(
        name="主机巡检",
        team=[7],
        definition={},
        status=Workflow.Status.PUBLISHED,
        current_version=1,
        enabled=True,
    )
    trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        node_key="alert_entry",
        name="告警入口",
        trigger_type=WorkflowTrigger.Type.NATS,
        enabled=True,
        team=[7],
        config={"subject": f"bklite.workflow.{workflow.pk}.alert_entry"},
    )
    client = mocker.patch("apps.workflow_orchestration.services.managed_nats_channels.SystemMgmt").return_value
    client.sync_workflow_orchestration_nats_channels.return_value = {"result": True}

    assert sync_workflow_nats_channels(workflow.pk) == {"result": True}
    client.sync_workflow_orchestration_nats_channels.assert_called_once_with(
        workflow_id=workflow.pk,
        workflow_name=workflow.name,
        team=[7],
        nodes=[
            {
                "trigger_id": str(trigger.pk),
                "node_key": "alert_entry",
                "name": "告警入口",
                "subject": f"bklite.workflow.{workflow.pk}.alert_entry",
            }
        ],
        active=True,
    )


@pytest.mark.django_db
def test_deleted_workflow_cleans_managed_channels(mocker):
    workflow = Workflow.objects.create(name="已删除流程", team=[7], definition={}, deleted_at=timezone.now())
    client = mocker.patch("apps.workflow_orchestration.services.managed_nats_channels.SystemMgmt").return_value
    client.delete_workflow_orchestration_nats_channels.return_value = {"result": True, "data": {"deleted": 1}}

    assert sync_workflow_nats_channels(workflow.pk)["result"] is True
    assert delete_workflow_nats_channels(workflow.pk)["result"] is True
    assert client.delete_workflow_orchestration_nats_channels.call_count == 2


@pytest.mark.django_db
def test_managed_nats_sync_failure_uses_stable_log_without_leaking_downstream_message(mocker):
    workflow = Workflow.objects.create(
        name="敏感信息测试",
        team=[7],
        definition={},
        status=Workflow.Status.PUBLISHED,
        current_version=1,
        enabled=True,
    )
    secret = "SENSITIVE_TOKEN_do_not_log"
    client = mocker.patch("apps.workflow_orchestration.services.managed_nats_channels.SystemMgmt").return_value
    client.sync_workflow_orchestration_nats_channels.side_effect = RuntimeError(secret)
    logger = mocker.patch("apps.workflow_orchestration.services.managed_nats_channels.logger")

    result = sync_workflow_nats_channels(workflow.pk)

    assert result == {"result": False, "message": "托管 NATS 通道同步失败"}
    logger.error.assert_called_once()
    log_args = logger.error.call_args.args
    assert log_args[0] == ("event=workflow_managed_nats_sync_failed workflow_id=%s " "failed_stage=system_mgmt_rpc error_type=%s")
    assert log_args[1:] == (workflow.pk, "RuntimeError")
    assert secret not in (log_args[0] % log_args[1:])
    exc_type, exc_value, traceback = logger.error.call_args.kwargs["exc_info"]
    assert exc_type is RuntimeError
    assert str(exc_value) == "workflow managed NATS channel sync failed"
    assert secret not in str(exc_value)
    assert traceback is not None
