import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from apps.itsm.services import vmware_delivery as delivery


def test_job_acceptance_does_not_complete_delivery():
    response = {"result": True, "data": {"status": "running", "execution_results": []}}
    with patch("apps.job_mgmt.nats_api.job_detail_query", return_value=response):
        assert delivery.read_receipt(8, 1, "itsm-42-1") is None


def test_foreign_or_missing_receipt_cannot_complete_a_ticket():
    row = {"delivery_id": "other", "status": "success", "ip": "192.0.2.1", "vm_id": "vm-2", "vm_uuid": "u"}
    response = {"result": True, "data": {"status": "success", "execution_results": [{"stdout": json.dumps(row)}]}}
    with patch("apps.job_mgmt.nats_api.job_detail_query", return_value=response), pytest.raises(ValueError):
        delivery.read_receipt(8, 1, "itsm-42-1")


def test_demo_never_submits_a_job_and_labels_each_vm():
    ticket = SimpleNamespace(pk=42, is_test=False, domain="test", logs=Mock())
    ticket.logs.filter.return_value.order_by.return_value.first.return_value.action = "approve"
    plan = {"machines": [{"cpu": 2, "memory_gib": 4, "data_disk_gib": 0}] * 2}
    with patch.object(delivery, "submit_vm") as submit:
        complete, lines = delivery.advance(ticket, "demo", {}, plan)
    assert complete and len(lines) == 2 and all("模拟" in line for line in lines)
    submit.assert_not_called()


def test_partial_delivery_only_waits_for_unfinished_vm():
    ticket = SimpleNamespace(pk=42, is_test=False, domain="test", logs=Mock(), service=SimpleNamespace(handler_group_id=1))
    approval = ticket.logs.filter.return_value.order_by.return_value.first.return_value
    approval.action, approval.operator = "approve", "approver"
    plan = {
        "quantity": 2,
        "team_id": 1,
        "target_id": 4,
        "vc_host": "vc.test",
        "template_id": "vm-2",
        "network_id": "network-1",
        "disk_policy_id": "standard",
        "cpu": 2,
        "memory_gib": 4,
        "data_disk_gib": 20,
    }
    machine = {k: plan.pop(k) for k in ("template_id", "network_id", "disk_policy_id", "cpu", "memory_gib", "data_disk_gib")}
    plan.pop("quantity")
    plan["machines"] = [machine, dict(machine, cpu=8, memory_gib=16, data_disk_gib=0)]
    receipt = {"hostname": "host", "ip": "192.0.2.5", "vm_id": "vm-99", "vm_uuid": "uuid-1"}
    state = {}
    with (
        patch.object(delivery, "handler_group_members", return_value=["approver"]),
        patch.object(delivery, "submit_vm", side_effect=[51, 52]) as submit,
        patch.object(delivery, "read_receipt", side_effect=[receipt, None, receipt]) as read,
    ):
        done, lines = delivery.advance(ticket, "lab", state, plan)
        assert not done and "作业 51" in lines[0] and "等待" in lines[1]
        done, lines = delivery.advance(ticket, "lab", state, plan)
        assert done and len(lines) == 2 and submit.call_count == 2 and read.call_count == 3
        assert [(c.args[3]["cpu"], c.args[3]["data_disk_gib"]) for c in submit.call_args_list] == [(2, 20), (8, 0)]


def test_missing_approval_rejects_even_demo():
    ticket = SimpleNamespace(pk=42, logs=Mock())
    ticket.logs.filter.return_value.order_by.return_value.first.return_value = None
    with pytest.raises(ValueError, match="审批"):
        delivery.advance(ticket, "demo", {}, {})


@pytest.mark.django_db
def test_job_platform_replays_same_delivery_and_returns_bound_receipt():
    from apps.job_mgmt.models import JobExecution, Target

    target = Target.objects.create(name="本地隔离验证", ip="192.0.2.100", domain="test", team=[1])
    plan = {"target_id": target.pk, "team_id": 1}
    req = {"delivery_id": "itsm-42-1", "profile": "test"}
    ticket = SimpleNamespace(domain="test")
    with patch("apps.job_mgmt.nats_api.dispatch_celery_task", return_value="isolated") as dispatch:
        job = delivery.submit_vm(ticket, "tester", plan, req, 1)
        assert delivery.submit_vm(ticket, "tester", plan, req, 1) == job
        assert dispatch.call_count == 1
    assert delivery.read_receipt(job, 1, req["delivery_id"]) is None
    receipt = {
        "status": "success",
        "delivery_id": req["delivery_id"],
        "hostname": "lab-1",
        "ip": "192.0.2.100",
        "vm_id": "vm-100",
        "vm_uuid": "58405e80-ab65-4230-9372-5908f158223d",
        "task_id": "task-200",
    }
    JobExecution.objects.filter(pk=job).update(status="success", execution_results=[{"stdout": json.dumps(receipt)}])
    assert delivery.read_receipt(job, 1, req["delivery_id"])["task_id"] == "task-200"


@pytest.mark.django_db
def test_worker_reclaim_waits_for_job_then_acknowledges_only_once():
    from apps.itsm.models import Ticket, Workflow, WorkflowVersion
    from apps.itsm.services.external_jobs import process_job

    workflow = Workflow.objects.create(key="vmware_test", name="虚拟机申请")
    node = {"id": "provision", "type": "auto", "name": "创建", "auto": {"kind": "vmware_provision", "profile": "lab"}}
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design={"nodes": [node]})
    ticket = Ticket.objects.create(workflow=workflow, workflow_version=version, creator="owner", process_instance_id="parent", sn="vm-qa")
    client = Mock()
    client.list_tasks_including_children.return_value = []
    client.get_process_instance.return_value = {"id": "parent"}
    job = {"id": "external1", "processInstanceId": "parent", "elementId": "provision"}
    with (
        patch.object(delivery, "load_delivery", return_value={"quantity": 1}),
        patch.object(delivery, "advance", side_effect=[(False, ["等待交付"]), (True, ["已收到 VM 回执"])]) as advance,
    ):
        assert not process_job(client, job)
        assert ticket.auto_executions.get().status == "awaiting_job"
        client.complete_external_job.assert_not_called()
        assert process_job(client, job)
        assert process_job(client, job)
        ticket.refresh_from_db()
        assert ticket.form_data["delivery_result"] == "已收到 VM 回执"
        assert advance.call_count == 2
        client.complete_external_job.assert_called_once()


@pytest.mark.django_db
def test_batch_retry_dispatches_only_failed_row_and_script_reads_its_original_parameters():
    import runpy
    import shlex

    from apps.itsm.models import Service, Ticket, Workflow, WorkflowVersion
    from apps.itsm.services.external_jobs import process_job
    from apps.job_mgmt.models import JobExecution, Target

    workflow = Workflow.objects.create(key="batch", name="批量申请")
    node = {"id": "create", "type": "auto", "auto": {"kind": "vmware_provision", "profile": "lab"}}
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design={"nodes": [node]})
    service = Service.objects.create(workflow=workflow, name="批量交付")
    ticket = Ticket.objects.create(
        service=service, workflow=workflow, workflow_version=version, domain="test", process_instance_id="batch-1", creator="owner", sn="batch-1"
    )
    ticket.logs.create(task=ticket.tasks.create(node_id="approve", status="done"), operator="admin", action="approve")
    target = Target.objects.create(ip="192.0.2.100", name="受管执行机", team=[1], domain="test")
    small = dict(cpu=2, memory_gib=4, template_id="vm-1", network_id="network-1", disk_policy_id="standard", data_disk_gib=0)
    medium = dict(small, cpu=4, memory_gib=8, template_id="vm-2", network_id="network-2", data_disk_gib=80)
    plan = {"machines": [small, medium], "vc_host": "vc.test", "team_id": 1, "target_id": target.pk}
    job = {"id": "ext1", "elementId": "create", "processInstanceId": "batch-1"}
    client = Mock()
    client.list_tasks_including_children.return_value = []
    client.get_process_instance.return_value = {"id": "batch-1"}
    decode = runpy.run_path(str(delivery.SCRIPT))["decode"]
    with (
        patch.object(delivery, "load_delivery", return_value=plan),
        patch.object(delivery, "handler_group_members", return_value=["admin"]),
        patch("apps.job_mgmt.nats_api.dispatch_celery_task", return_value="isolated") as dispatch,
    ):
        assert not process_job(client, job)
        first, second = JobExecution.objects.order_by("pk")
        for i, (record, machine) in enumerate([(first, small), (second, medium)], 1):
            assert decode(shlex.split(record.params)[0]) == dict(machine, delivery_id=f"itsm-{ticket.pk}-{i}", profile="lab", vc_host="vc.test")
        first.status = "failed"
        first.save(update_fields=["status"])
        receipt = dict(
            status="success", hostname="vm-2", ip="192.0.2.2", vm_id="vm-2", vm_uuid="u2", task_id="task-2", delivery_id=f"itsm-{ticket.pk}-2"
        )
        second.status, second.execution_results = "success", [{"stdout": json.dumps(receipt)}]
        second.save(update_fields=["status", "execution_results"])
        assert not process_job(client, job)
        assert ticket.auto_executions.get().status == "failed"
        ticket.auto_executions.update(status="queued")
        assert not process_job(client, job)
        retry = JobExecution.objects.latest("pk")
        assert retry.pk != first.pk and retry.params == first.params
        assert dispatch.call_count == 3
        receipt.update(hostname="vm-1", ip="192.0.2.1", vm_id="vm-1", vm_uuid="u1", task_id="task-1", delivery_id=f"itsm-{ticket.pk}-1")
        retry.status, retry.execution_results = "success", [{"stdout": json.dumps(receipt)}]
        retry.save(update_fields=["status", "execution_results"])
        assert process_job(client, job)
        client.complete_external_job.assert_called_once()
        assert dispatch.call_count == 3
