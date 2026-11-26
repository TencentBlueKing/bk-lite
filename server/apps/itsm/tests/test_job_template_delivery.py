import shlex
from unittest.mock import Mock, patch

import pytest

from apps.itsm.models import Ticket, TicketLog, TicketTask, Workflow, WorkflowVersion
from apps.itsm.services.external_jobs import process_job
from apps.job_mgmt.models import JobExecution, Script, Target
from apps.job_mgmt.services.template_revision import payload_hash, script_payload

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def flow():
    script = Script.objects.create(name="读取申请", content='echo "$1"', params=[{"name": "spec", "is_required": True}], team=[1])
    target = Target.objects.create(name="执行机", ip="192.0.2.11", team=[1])
    auto = {"kind": "job_template", "script_id": script.id, "target_id": target.id, "table_key": "machines", "params": {"spec": "size"}}
    auto["binding"] = {"operator": "publisher", "team_id": 1, "script_hash": payload_hash(script_payload(script))}
    workflow = Workflow.objects.create(key="batch", name="批量只读")
    nodes = [{"id": "review", "type": "approval"}, {"id": "inspect", "type": "auto", "auto": auto}]
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, is_published=True, design={"nodes": nodes})
    ticket = Ticket.objects.create(
        workflow=workflow,
        workflow_version=version,
        creator="staff",
        team=[1],
        sn="REQ-1",
        process_instance_id="parent",
        form_data={"machines": [{"size": "生产网段（上海 A）, vlan-012"}, {"size": "4 cpu"}]},
    )
    task = TicketTask.objects.create(ticket=ticket, node_id="review", process_instance_id="parent", status="done", assignee="operator")
    TicketLog.objects.create(ticket=ticket, task=task, action="approve", operator="operator")
    client = Mock()
    client.list_tasks_including_children.return_value = []
    client.get_process_instance.return_value = {"id": "parent"}
    return ticket, script, target, client, {"id": "fj1", "processInstanceId": "parent", "elementId": "inspect"}


@pytest.mark.parametrize("lost_ack", [False, True])
def test_two_rows_use_real_job_records_and_wait_for_all(flow, lost_ack):
    from datetime import timedelta

    from django.utils import timezone

    from apps.itsm.flowable.client import FlowableError
    from apps.itsm.services.external_jobs import reconcile_stale_executions

    ticket, script, target, client, job = flow
    with (
        patch("apps.itsm.services.job_template_delivery.require_job_permission"),
        patch("apps.job_mgmt.services.execution_service.ExecutionService._dispatch_or_raise") as dispatch,
    ):
        assert not process_job(client, job)
        jobs = list(JobExecution.objects.order_by("pk"))
        assert len(jobs) == 2
        assert [shlex.split(record.params) for record in jobs] == [["生产网段（上海 A）, vlan-012"], ["4 cpu"]]
        assert all(
            record.executor_user == "publisher" and record.script_id == script.pk and record.target_list == [{"target_id": target.pk}]
            for record in jobs
        )
        JobExecution.objects.filter(pk=jobs[0].pk).update(status="success")
        assert not process_job(client, job)
        client.complete_external_job.assert_not_called()
        JobExecution.objects.filter(pk=jobs[1].pk).update(status="success")
        if lost_ack:
            client.complete_external_job.side_effect = FlowableError(0, "引擎完成后连接中断")
            assert not process_job(client, job)
            pending = ticket.auto_executions.get()
            assert pending.status == "executed"
            assert [r["job_id"] for r in pending.detail["job_template"]["rows"]] == [record.pk for record in jobs]
            ticket.auto_executions.update(updated_at=timezone.now() - timedelta(minutes=6))
            client.confirmed_external_job.return_value = True
            assert reconcile_stale_executions(client) == 1
        else:
            assert process_job(client, job)
        assert process_job(client, job)
        assert ticket.auto_executions.get().status == "done"
        assert dispatch.call_count == 2
    assert ticket.auto_executions.get().detail["job_template"]["rows"] == [
        {"row": i, "job_id": record.pk, "status": "success"} for i, record in enumerate(jobs, 1)
    ]
    client.complete_external_job.assert_called_once()


@pytest.mark.parametrize(
    "invalid",
    ["domain", "target_team", "approval", "test", "last_row", "permission", "template_change", "non_scalar", "multiline", "nul", "template_syntax"],
)
def test_refuses_invalid_batch_before_dispatch(flow, invalid):
    ticket, script, target, client, job = flow
    if invalid == "domain":
        Script.objects.filter(pk=script.pk).update(domain="other")
    elif invalid == "target_team":
        target.team = [2]
        target.save()
    elif invalid == "approval":
        ticket.logs.update(action="reject")
    elif invalid == "test":
        Ticket.objects.filter(pk=ticket.pk).update(is_test=True)
    elif invalid == "template_change":
        Script.objects.filter(pk=script.pk).update(content="date")
    elif invalid in {"non_scalar", "multiline", "nul", "template_syntax"}:
        bad = {"non_scalar": [12, 13], "multiline": "multi\nline", "nul": "a\0b", "template_syntax": "{{ spec }}"}[invalid]
        Ticket.objects.filter(pk=ticket.pk).update(form_data={"machines": [{"size": "yes"}, {"size": bad}]})
    elif invalid == "last_row":
        Ticket.objects.filter(pk=ticket.pk).update(form_data={"machines": [{"size": "yes"}, {}]})
    with patch(
        "apps.itsm.services.job_template_delivery.require_job_permission",
        side_effect=PermissionError("缺少执行权限") if invalid == "permission" else None,
    ):
        assert not process_job(client, job)
    assert not JobExecution.objects.exists()
    assert ticket.auto_executions.get().status == "failed"


def test_terminal_failure_keeps_original_jobs_and_blocks_ack(flow):
    ticket, script, target, client, job = flow
    with (
        patch("apps.itsm.services.job_template_delivery.require_job_permission"),
        patch("apps.job_mgmt.services.execution_service.ExecutionService._dispatch_or_raise") as dispatch,
    ):
        assert not process_job(client, job)
        jobs = list(JobExecution.objects.order_by("pk"))
        JobExecution.objects.filter(pk=jobs[0].pk).update(status="failed")
        assert not process_job(client, job)
        JobExecution.objects.filter(pk=jobs[1].pk).update(status="success")
        assert not process_job(client, job)
        assert not process_job(client, job)
        assert dispatch.call_count == 2
    execution = ticket.auto_executions.get()
    assert execution.status == "failed" and not execution.detail["retryable"]
    assert "第 1 行" in execution.detail["reason"]
    assert execution.detail["job_template"]["rows"][0]["job_id"] == jobs[0].pk
    client.complete_external_job.assert_not_called()


def test_portal_submission_stamps_the_selected_authorized_team(flow):
    from apps.core.openapi.identity import CallerIdentity
    from apps.itsm.services.ticket.service import TicketService
    from apps.system_mgmt.models import Group

    existing, _, _, _, _ = flow
    Group.objects.get_or_create(pk=1, defaults={"name": "one"})
    Group.objects.get_or_create(pk=2, defaults={"name": "two"})
    identity = CallerIdentity(user="new-user", domain=existing.domain, credential_type="jwt", team_ids=[1, 2])
    version = existing.workflow_version
    with patch.object(TicketService, "_resume_creation", side_effect=lambda t: t):
        ticket = TicketService(identity=identity, current_team=1).create(version, {}, "new-user")
        assert ticket.team == [1]
        with pytest.raises(PermissionError):
            TicketService(identity=identity, current_team=2).create(version, {}, "new-user")
        identity.team_ids = [2]
        with pytest.raises(PermissionError):
            TicketService(identity=identity, current_team=1).create(version, {}, "new-user")


def test_publisher_requires_live_job_permission_in_selected_team():
    from apps.base.models import User as LoginUser
    from apps.itsm.services.job_template_delivery import require_job_permission
    from apps.system_mgmt.models import Group, Menu, Role, User

    group = Group.objects.create(name="作业域")
    other = Group.objects.create(name="其他域")
    right = Menu.objects.create(name="quick_exec-Add", app="job")
    role = Role.objects.create(name="run", app="job", menu_list=[right.pk])
    group.roles.add(role)
    actor = User.objects.create(username="publisher", group_list=[group.pk, other.pk])
    LoginUser.objects.create(username="publisher", domain="domain.com", is_active=True)
    require_job_permission(actor.username, actor.domain, group.pk)
    with pytest.raises(PermissionError):
        require_job_permission(actor.username, actor.domain, other.pk)
    actor.disabled = True
    actor.save()
    with pytest.raises(PermissionError):
        require_job_permission(actor.username, actor.domain, group.pk)
