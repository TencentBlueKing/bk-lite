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


@pytest.mark.parametrize("outcome", ["executed", "not_executed"])
def test_crashed_external_worker_requires_verified_outcome(workflow, outcome):
    from datetime import timedelta

    from django.utils import timezone

    version = workflow.current_version
    version.design["nodes"][0]["auto"] = {"kind": "integration", "result_field": "external_id"}
    version.save()
    ticket = Ticket.objects.create(
        sn="CRASH", title="中断", domain=workflow.domain, workflow=workflow, workflow_version=version, creator="owner", process_instance_id="p"
    )
    job = {"id": "job", "processInstanceId": "p", "elementId": "auto"}
    client = Mock()
    client.list_tasks_including_children.return_value = []
    with patch.object(external_jobs, "run_auto_action", side_effect=SystemExit) as execute:
        with pytest.raises(SystemExit):
            external_jobs.process_job(client, job)
        execution = ticket.auto_executions.get()
        assert external_jobs.reconcile_stale_executions(client) == 0
        AutoExecution.objects.filter(pk=execution.pk).update(updated_at=timezone.now() - timedelta(minutes=10))
        assert external_jobs.reconcile_stale_executions(client) == 1
        assert not external_jobs.process_job(client, job)
        execute.assert_called_once()
    row = next(row for row in tickets._ticket_detail(ticket, can_retry=True)["history"] if row.get("execution_id"))
    payload = {"outcome": outcome, "note": "核对下游执行记录", "review_token": row["review_token"]}
    allowed = ["ticket-View", "ticket-Operate", "workflow-Edit"]

    def call(data, permissions=allowed, domain=workflow.domain):
        return tickets.reconcile_auto_node(
            request("post", data, username="owner", permissions=permissions, domain=domain), ticket.pk, execution.pk
        ).status_code

    assert call(payload, allowed[:2]) == 403
    assert call(payload, domain="other") == 404
    assert call({**payload, "review_token": "previous-attempt"}) == 409
    assert call({**payload, "note": ""}) == 400
    if outcome == "executed":
        assert call(payload) == 400
        payload["result_value"] = "external-42"
    assert call(payload) == 200
    assert call(payload) == 409
    with patch.object(external_jobs, "run_auto_action", return_value=("done", {})) as execute:
        assert external_jobs.process_job(client, job)
        assert execute.call_count == (outcome == "not_executed")
    if outcome == "executed":
        ticket.refresh_from_db()
        assert ticket.form_data["external_id"] == "external-42"
    assert ticket.logs.filter(action="auto_reconcile", operator="owner", detail__opinion=payload["note"]).count() == 1
    client.complete_external_job.assert_called_once()


def test_orphaned_local_action_retries_and_fences_delayed_worker(workflow):
    from datetime import timedelta

    from django.utils import timezone

    ticket = Ticket.objects.create(
        sn="LOCAL",
        title="本地动作",
        domain=workflow.domain,
        workflow=workflow,
        workflow_version=workflow.current_version,
        creator="owner",
        process_instance_id="p",
    )
    job = {"id": "j", "processInstanceId": "p", "elementId": "auto"}
    table = DataTable.objects.create(key="result", name="结果", domain=workflow.domain)
    client = Mock()
    client.list_tasks_including_children.return_value = []
    with patch.object(external_jobs, "_execute", side_effect=SystemExit) as attempt:
        with pytest.raises(SystemExit):
            external_jobs.process_job(client, job)
    execution = ticket.auto_executions.get()
    AutoExecution.objects.filter(pk=execution.pk).update(updated_at=timezone.now() - timedelta(minutes=6))
    assert external_jobs.reconcile_stale_executions(client) == 1
    external_jobs._execute(*attempt.call_args.args)
    assert not DataTableRow.objects.filter(table=table).exists()
    assert external_jobs.process_job(client, job)
    assert DataTableRow.objects.filter(table=table).count() == 1


@pytest.mark.django_db(transaction=True)
def test_stale_scan_skips_worker_still_executing(workflow):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from threading import Event

    from django.db import connection, connections
    from django.utils import timezone

    if not connection.features.has_select_for_update_skip_locked:
        pytest.skip("并发领取需要行锁和 SKIP LOCKED")
    ticket = Ticket.objects.create(
        sn="SLOW",
        title="慢调用",
        domain=workflow.domain,
        workflow=workflow,
        workflow_version=workflow.current_version,
        creator="owner",
        process_instance_id="p",
    )
    job = {"id": "slow", "processInstanceId": "p", "elementId": "auto"}
    client = Mock()
    client.list_tasks_including_children.return_value = []
    claimed = Event()
    proceed = Event()
    run = external_jobs._execute

    def age_claim(t, execution, node, detail):
        AutoExecution.objects.filter(pk=execution.pk).update(updated_at=timezone.now() - timedelta(minutes=10))
        run(t, execution, node, detail)

    def slow(*args, **kwargs):
        claimed.set()
        assert proceed.wait(5)
        return {}

    def worker():
        try:
            return external_jobs.process_job(client, job)
        finally:
            connections.close_all()

    with patch.object(external_jobs, "_execute", side_effect=age_claim), patch.object(external_jobs, "execute_node", side_effect=slow):
        with ThreadPoolExecutor(max_workers=1) as workers:
            task = workers.submit(worker)
            try:
                assert claimed.wait(5)
                assert external_jobs.reconcile_stale_executions(client) == 0
                assert ticket.auto_executions.get().status == "running"
            finally:
                proceed.set()
            assert task.result(timeout=5)
    assert ticket.auto_executions.get().status == "done"
