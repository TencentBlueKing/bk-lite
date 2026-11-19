from unittest.mock import Mock, patch

import pytest

from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import AutoExecution, DataTable, DataTableRow, Ticket, Workflow, WorkflowVersion
from apps.itsm.services import external_jobs
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views import tickets

pytestmark = pytest.mark.django_db


@pytest.fixture
def workflow():
    workflow = Workflow.objects.create(key="recovery", name="恢复测试", domain="domain.com")
    version = WorkflowVersion.objects.create(
        workflow=workflow,
        domain=workflow.domain,
        version_no=1,
        is_published=True,
        process_definition_key="recovery-v1",
        design={"nodes": [{"id": "auto", "name": "写入结果", "type": "auto", "auto": {"kind": "table", "table_key": "result"}}]},
    )
    workflow.current_version = version
    workflow.save()
    return workflow


def test_failed_node_retry_is_scoped_and_ack_never_replays(workflow):
    ticket = Ticket.objects.create(
        sn="RECOVERY",
        title="恢复",
        domain=workflow.domain,
        workflow=workflow,
        workflow_version=workflow.current_version,
        creator="owner",
        process_instance_id="p",
    )
    job = {"id": "job", "processInstanceId": "p", "elementId": "auto"}
    client = Mock()
    client.list_tasks_including_children.return_value = []
    client.get_process_instance.return_value = {"id": "p"}
    client.complete_external_job.side_effect = [FlowableError(503, "private"), None]
    assert not external_jobs.process_job(client, job)
    execution = AutoExecution.objects.get(ticket=ticket)
    assert execution.detail["node_id"] == "auto"
    assert tickets._ticket_detail(ticket)["history"][0]["state"] == "failed"
    allowed = ["ticket-View", "ticket-Operate", "workflow-Edit"]
    assert tickets.retry_auto_node(request("post", username="owner"), ticket.id, execution.id).status_code == 403
    assert tickets.retry_auto_node(request("post", username="owner", permissions=allowed, domain="other"), ticket.id, execution.id).status_code == 404
    table = DataTable.objects.create(key="result", name="结果", domain=workflow.domain)
    assert tickets.retry_auto_node(request("post", username="owner", permissions=allowed), ticket.id, execution.id).status_code == 200
    assert tickets.retry_auto_node(request("post", username="owner", permissions=allowed), ticket.id, execution.id).status_code == 200
    assert ticket.logs.filter(action="auto_retry", operator="owner").count() == 1
    assert not external_jobs.process_job(client, job)
    execution.refresh_from_db()
    assert execution.status == "executed"
    assert "动作已完成" in execution.detail["reason"]
    assert external_jobs.process_job(client, job)
    assert external_jobs.process_job(client, job)
    assert DataTableRow.objects.filter(table=table).count() == 1
    execution.refresh_from_db()
    assert execution.status == "done"


def test_unknown_external_failure_is_not_replayed(workflow):
    version = workflow.current_version
    version.design["nodes"][0]["auto"] = {"kind": "http"}
    version.save()
    ticket = Ticket.objects.create(
        sn="UNCERTAIN",
        title="不确定",
        domain=workflow.domain,
        workflow=workflow,
        workflow_version=version,
        creator="owner",
        process_instance_id="p",
    )
    job = {"id": "job", "processInstanceId": "p", "elementId": "auto"}
    with patch.object(external_jobs, "run_auto_action", return_value=("failed", {"error_type": "ReadTimeout"})) as execute:
        assert not external_jobs.process_job(Mock(), job)
        execution = AutoExecution.objects.get(ticket=ticket)
        allowed = ["ticket-View", "ticket-Operate", "workflow-Edit"]
        assert tickets.retry_auto_node(request("post", username="owner", permissions=allowed), ticket.id, execution.id).status_code == 409
        assert not external_jobs.process_job(Mock(), job)
        execute.assert_called_once()
