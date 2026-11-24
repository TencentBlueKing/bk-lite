"""自动节点 ACK 丢包后只核对引擎回执，不重新执行业务。"""

import os
import time
from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.itsm.flowable.bpmn_builder import build_bpmn
from apps.itsm.flowable.client import FlowableClient, FlowableError
from apps.itsm.models import AutoExecution, DataTable, DataTableRow, Ticket, Workflow, WorkflowVersion
from apps.itsm.services import external_jobs
from apps.itsm.tests import test_auto_recovery
from apps.itsm.tests.test_ticket_orsign_flow import _client

workflow = test_auto_recovery.workflow

pytestmark = pytest.mark.django_db


def test_ack_404_does_not_complete_without_exact_engine_receipt(workflow):
    table = DataTable.objects.create(key="result", name="结果", domain=workflow.domain)
    ticket = Ticket.objects.create(
        sn="ACK-404",
        title="回执丢失",
        workflow=workflow,
        workflow_version=workflow.current_version,
        domain=workflow.domain,
        process_instance_id="p",
    )
    client = Mock()
    client.complete_external_job.side_effect = FlowableError(404, "not found")
    job = {"id": "job", "processInstanceId": "p", "elementId": "auto"}
    assert not external_jobs.process_job(client, job)
    receipt = ticket.auto_executions.get()
    assert receipt.status == "executed"
    old = timezone.now() - timedelta(minutes=10)
    AutoExecution.objects.filter(pk=receipt.pk).update(updated_at=old)
    client.confirmed_external_job.return_value = False
    assert external_jobs.reconcile_stale_executions(client) == 0
    receipt.refresh_from_db()
    assert receipt.status == "executed"
    AutoExecution.objects.filter(pk=receipt.pk).update(updated_at=old)
    client.confirmed_external_job.return_value = True
    assert external_jobs.reconcile_stale_executions(client) == 1
    assert external_jobs.reconcile_stale_executions(client) == 0
    receipt.refresh_from_db()
    assert receipt.status == "done" and not receipt.detail.get("reason")
    client.complete_external_job.assert_called_once()
    assert DataTableRow.objects.filter(table=table).count() == 1


@pytest.mark.parametrize("mismatch", ["", "instance", "job", "attempt", "task_scope", "duplicate", "missing"])
def test_ack_history_requires_exact_instance_job_and_attempt(mismatch):
    client = FlowableClient("http://unused", "", "")
    variable = {"name": "__bk_itsm_ack_1", "scope": "global", "type": "string", "value": "job-a:attempt-a"}
    row = {"processInstanceId": "p", "variable": dict(variable)}
    if mismatch == "instance":
        row["processInstanceId"] = "other"
    if mismatch == "job":
        row["variable"]["value"] = "job-b:attempt-a"
    if mismatch == "attempt":
        row["variable"]["value"] = "job-a:attempt-b"
    if mismatch == "task_scope":
        row["variable"]["scope"] = "local"
    rows = [] if mismatch == "missing" else [row, row] if mismatch == "duplicate" else [row]
    with patch.object(client, "_request", return_value={"data": rows, "total": len(rows)}):
        assert client.confirmed_external_job("p", variable["name"], variable["value"]) is (not mismatch)


def test_ack_history_batches_make_progress_past_missing_legacy_receipt(workflow):
    ticket = Ticket.objects.create(
        sn="ACK-PAGE",
        title="分批核对",
        workflow=workflow,
        workflow_version=workflow.current_version,
        domain=workflow.domain,
        process_instance_id="p",
    )
    receipts = [
        AutoExecution.objects.create(ticket=ticket, kind="external", status="executed", detail={"process_id": "p", "job_id": job})
        for job in ("old", "new")
    ]
    AutoExecution.objects.filter(pk__in=[r.pk for r in receipts]).update(updated_at=timezone.now() - timedelta(minutes=10))
    client = Mock()
    client.confirmed_external_job.side_effect = [FlowableError(503, "history unavailable"), True]
    assert external_jobs.reconcile_stale_executions(client, limit=1) == 0
    assert external_jobs.reconcile_stale_executions(client, limit=1) == 1
    assert list(ticket.auto_executions.order_by("pk").values_list("status", flat=True)) == ["executed", "done"]
    assert client.confirmed_external_job.call_count == 2
    client.complete_external_job.assert_not_called()


@pytest.mark.skipif(os.environ.get("ITSM_FLOWABLE_TEST") != "1", reason="需要真实 Flowable")
def test_real_engine_ack_lost_after_commit():
    client = _client()
    key = "ack_" + uuid4().hex[:12]
    table = DataTable.objects.create(name="回执测试", key=key)
    workflow = Workflow.objects.create(name="回执恢复", key=key)
    design = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "auto", "type": "auto", "auto": {"kind": "table", "table_key": key}},
            {"id": "end", "type": "end"},
        ],
        "edges": [{"from": "start", "to": "auto"}, {"from": "auto", "to": "end"}],
    }
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design=design, process_definition_key=key, is_published=True)
    deployment = client.deploy_bpmn(key, build_bpmn(design, key).replace("itsm.auto", key))
    try:
        definition_id = client.definition_for_deployment(deployment["id"], key)
        instance = client.start_process(definition_id, key)["id"]
        ticket = Ticket.objects.create(sn=key, title="回执恢复", workflow=workflow, workflow_version=version, process_instance_id=instance)
        jobs = []
        deadline = time.monotonic() + 15
        while not jobs and time.monotonic() < deadline:
            jobs = client.acquire_jobs(key)
            if not jobs:
                time.sleep(0.1)
        assert len(jobs) == 1
        complete = client.complete_external_job

        def drop_response(*args, **kwargs):
            complete(*args, **kwargs)
            raise FlowableError(0, "客户端丢失引擎成功响应")

        with patch.object(client, "complete_external_job", side_effect=drop_response) as ack:
            assert not external_jobs.process_job(client, jobs[0])
            assert client.acquire_jobs(key) == []
            receipt = ticket.auto_executions.get()
            assert receipt.status == "executed"
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                AutoExecution.objects.filter(pk=receipt.pk).update(updated_at=timezone.now() - timedelta(minutes=10))
                if external_jobs.reconcile_stale_executions(client):
                    break
                time.sleep(0.1)
            receipt.refresh_from_db()
            assert receipt.status == "done"
            history = client._request("GET", f"/flowable-rest/service/history/historic-process-instances/{instance}")
            assert history["endTime"]
            assert external_jobs.reconcile_stale_executions(client) == 0
            assert ack.call_count == 1
            assert DataTableRow.objects.filter(table=table).count() == 1
    finally:
        client._request("DELETE", f"/flowable-rest/service/repository/deployments/{deployment['id']}", params={"cascade": "true"})
