import os
from unittest.mock import patch
from uuid import uuid4

import pytest
import requests
from django.conf import settings

from apps.itsm.flowable.bpmn_builder import build_bpmn
from apps.itsm.flowable.client import FlowableClient
from apps.itsm.models import TicketLog, TicketTask, Workflow, WorkflowVersion
from apps.itsm.services.ticket.service import TicketService

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(os.environ.get("ITSM_FLOWABLE_TEST") != "1", reason="显式设置 ITSM_FLOWABLE_TEST=1 运行真实引擎验收"),
]

DESIGN = {
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "submit", "type": "submit", "name": "提单"},
        {
            "id": "approve",
            "type": "approval",
            "name": "或签",
            "assignee": {"source": "users", "value": ["alice", "bob"]},
            "multi": {"mode": "any"},
            "fallback": "admin",
        },
        {"id": "handle", "type": "handle", "name": "处理", "assignee": {"source": "users", "value": ["handler"]}, "fallback": "admin"},
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"from": "start", "to": "submit"},
        {"from": "submit", "to": "approve"},
        {"from": "approve", "to": "handle"},
        {"from": "handle", "to": "end"},
    ],
}


def _client():
    base = settings.FLOWABLE_URL
    try:
        response = requests.get(
            f"{base.rstrip('/')}/flowable-rest/service/repository/deployments",
            auth=(settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD),
            timeout=3,
        )
    except requests.RequestException:
        pytest.skip("Flowable 未启动")
    if response.status_code != 200:
        pytest.skip(f"Flowable 不可用: {response.status_code}")
    return FlowableClient(base, settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD)


@patch("apps.itsm.services.ticket.service.itsm_event.send")
@patch("apps.itsm.services.todo_sync.push_todo")
def test_submit_orsign_handle_finishes(_todo, _notify):
    from django.core.management import call_command

    call_command("init_itsm")
    client = _client()
    workflow = Workflow.objects.create(name="或签流程", key="itsm_orsign_" + uuid4().hex[:12], created_by="tester", updated_by="tester")
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design=DESIGN, created_by="tester", updated_by="tester")
    xml = build_bpmn(DESIGN, workflow.key)
    deployed = client.deploy_bpmn(workflow.key, xml)
    version.flowable_deployment_id = deployed["id"]
    version.save(update_fields=["flowable_deployment_id"])
    version.process_definition_key = workflow.key
    version.is_published = True
    version.bpmn_xml = xml
    version.save()
    service = TicketService(client)
    ticket = service.create(version, {"title": "申请服务器"}, "creator")
    submit = ticket.tasks.get(node_id="submit", status=TicketTask.TaskStatus.PENDING)
    service.operate(ticket, submit, "submit", {}, "creator")
    approve_tasks = list(ticket.tasks.filter(node_id="approve"))
    assert len(approve_tasks) >= 1
    pending = [task for task in approve_tasks if task.status == TicketTask.TaskStatus.PENDING]
    service.operate(ticket, pending[0], "approve", {"opinion": "同意"}, pending[0].assignee or "alice")
    ticket.refresh_from_db()
    handle = ticket.tasks.get(node_id="handle", status=TicketTask.TaskStatus.PENDING)
    service.operate(ticket, handle, "submit", {"opinion": "已处理"}, "handler")
    ticket.refresh_from_db()
    assert ticket.status.key == "finished"
    assert set(TicketLog.objects.filter(ticket=ticket).values_list("action", flat=True)) >= {"create", "submit", "approve"}
    assert not ticket.tasks.filter(node_id="approve", status=TicketTask.TaskStatus.PENDING).exists()

    client._request("DELETE", f"/flowable-rest/service/repository/deployments/{deployed['id']}", params={"cascade": "true"})


@patch("apps.itsm.services.ticket.service.itsm_event.send")
@patch("apps.itsm.services.todo_sync.push_todo")
def test_auto_chain_then_human_finishes(_todo, _notify):
    import time

    from django.core.management import call_command

    from apps.itsm.models import DataTable, DataTableRow
    from apps.itsm.services.external_jobs import process_job, reconcile_tickets

    call_command("init_itsm")
    client = _client()
    suffix = uuid4().hex[:12]
    table = DataTable.objects.create(name="闭环数据", key="review_" + suffix)
    design = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "submit", "type": "submit"},
            {"id": "auto_1", "type": "auto", "auto": {"kind": "table", "table_key": table.key, "data": {"verified": True}}},
            {"id": "approval_1", "type": "approval", "assignee": {"source": "users", "value": ["handler"]}},
            {"id": "end", "type": "end"},
        ],
        "edges": [{"from": a, "to": b} for a, b in [("start", "submit"), ("submit", "auto_1"), ("auto_1", "approval_1"), ("approval_1", "end")]],
    }
    workflow = Workflow.objects.create(name="自动闭环", key="review_auto_" + suffix)
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design=design, process_definition_key=workflow.key, is_published=True)
    deployed = client.deploy_bpmn(workflow.key, build_bpmn(design, workflow.key))
    version.flowable_deployment_id = deployed["id"]
    version.save(update_fields=["flowable_deployment_id"])
    try:
        service = TicketService(client)
        ticket = service.create(version, {"title": "自动节点验收"}, "creator", is_test=True)
        service.operate(ticket, ticket.tasks.get(status="pending"), "submit", {}, "creator")
        deadline = time.monotonic() + 15
        acquired = False
        while time.monotonic() < deadline:
            for job in client.acquire_jobs("itsm.auto"):
                if job.get("processInstanceId") == ticket.process_instance_id:
                    assert process_job(client, job), job
                    acquired = True
            if acquired:
                break
            time.sleep(0.2)
        assert acquired, "没有领取到本流程的自动作业"
        assert DataTableRow.objects.filter(table=table, data={"verified": True}).count() == 1
        deadline = time.monotonic() + 10
        while not ticket.tasks.filter(node_id="approval_1", status="pending").exists() and time.monotonic() < deadline:
            reconcile_tickets(client)
            time.sleep(0.1)
        task = ticket.tasks.get(node_id="approval_1", status="pending")
        service.operate(ticket, task, "claim", {}, "handler")
        service.operate(ticket, task, "approve", {}, "handler")
        ticket.refresh_from_db()
        assert ticket.status.key == "finished"
        assert not ticket.tasks.filter(status__in=["pending", "claimed"]).exists()
    finally:
        client._request("DELETE", f"/flowable-rest/service/repository/deployments/{deployed['id']}", params={"cascade": "true"})


@patch("apps.itsm.services.ticket.service.itsm_event.send")
@patch("apps.itsm.services.todo_sync.push_todo")
def test_real_suspend_transfer_return_withdraw_and_reopen(_todo, _notify):
    from django.core.management import call_command

    from apps.system_mgmt.models import User

    call_command("init_itsm")
    client = _client()
    key = "review_lifecycle_" + uuid4().hex[:12]
    workflow = Workflow.objects.create(name="生命周期回归", key=key)
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design=DESIGN, process_definition_key=key, is_published=True)
    deployment = client.deploy_bpmn(key, build_bpmn(DESIGN, key))
    version.flowable_deployment_id = deployment["id"]
    version.save(update_fields=["flowable_deployment_id"])
    try:
        service = TicketService(client)
        ticket = service.create(version, {"title": "生命周期验收"}, "creator", is_test=True)
        User.objects.create(domain=ticket.domain, username="handler", display_name="处理人")
        task = ticket.tasks.get(status="pending")
        service.operate(ticket, task, "suspend", {}, "creator")
        assert client.get_process_instance(ticket.process_instance_id)["suspended"] is True
        with pytest.raises(ValueError, match="挂起"):
            service.operate(ticket, task, "submit", {}, "creator")
        service.operate(ticket, task, "resume", {}, "creator")
        assert client.get_process_instance(ticket.process_instance_id)["suspended"] is False
        service.operate(ticket, task, "transfer", {"target": "handler"}, "creator")
        assert client.list_tasks(ticket.process_instance_id)["data"][0]["assignee"] == "handler"
        with pytest.raises(PermissionError):
            service.operate(ticket, task, "submit", {}, "creator")
        service.operate(ticket, task, "submit", {}, "handler")
        approval = ticket.tasks.filter(node_id="approve", status="pending").first()
        service.operate(ticket, approval, "return", {"return_mode": "submit"}, approval.assignee)
        assert ticket.tasks.filter(node_id="submit", status="pending").exists()
        service.operate(ticket, None, "withdraw", {}, "creator")
        ticket.refresh_from_db()
        assert ticket.status.key == "cancelled"
        assert not ticket.tasks.filter(status__in=["pending", "claimed"]).exists()
        previous = ticket.process_instance_id
        service.operate(ticket, None, "reopen", {}, "creator")
        ticket.refresh_from_db()
        assert ticket.process_instance_id != previous
        assert ticket.tasks.filter(node_id="submit", status="pending").exists()
        service.operate(ticket, None, "withdraw", {}, "creator")
    finally:
        client._request("DELETE", f"/flowable-rest/service/repository/deployments/{deployment['id']}", params={"cascade": "true"})


@patch("apps.itsm.services.ticket.service.itsm_event.send")
@patch("apps.itsm.services.todo_sync.push_todo")
def test_real_decision_parallel_join_and_notice_chain(_todo, _notify):
    import time

    from django.core.management import call_command

    from apps.itsm.models import DecisionTable
    from apps.itsm.services.external_jobs import process_job, reconcile_tickets

    call_command("init_itsm")
    client = _client()
    key = "review_parallel_" + uuid4().hex[:12]
    decision = DecisionTable.objects.create(name="金额决策", rules=[{"when": {"field": "amount", "op": ">", "value": 100}, "then": {"approved": True}}])
    design = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "submit", "type": "submit"},
            {"id": "decision", "type": "decision", "auto": {"decision_id": decision.id}},
            {"id": "branch", "type": "exclusive"},
            {"id": "fork", "type": "parallel"},
            {"id": "a", "type": "handle", "assignee": {"source": "users", "value": ["alice"]}},
            {"id": "b", "type": "handle", "assignee": {"source": "users", "value": ["bob"]}},
            {"id": "join", "type": "converge"},
            {"id": "notice", "type": "notice", "auto": {"receivers": ["creator"], "content": "验收完成"}},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"from": a, "to": b}
            for a, b in [
                ("start", "submit"),
                ("submit", "decision"),
                ("decision", "branch"),
                ("fork", "a"),
                ("fork", "b"),
                ("a", "join"),
                ("b", "join"),
                ("join", "notice"),
                ("notice", "end"),
            ]
        ]
        + [{"from": "branch", "to": "fork", "default": True}],
    }
    workflow = Workflow.objects.create(name="十节点验收", key=key)
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design=design, process_definition_key=key, is_published=True)
    deployment = client.deploy_bpmn(key, build_bpmn(design, key))
    version.flowable_deployment_id = deployment["id"]
    version.save(update_fields=["flowable_deployment_id"])
    try:
        service = TicketService(client)
        ticket = service.create(version, {"title": "决策并行通知验收", "amount": 200}, "creator", is_test=True)
        service.operate(ticket, ticket.tasks.get(status="pending"), "submit", {}, "creator")

        def drain_until(predicate):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                for topic in ["itsm.auto", "itsm.notify"]:
                    for job in client.acquire_jobs(topic):
                        if job.get("processInstanceId") == ticket.process_instance_id:
                            assert process_job(client, job)
                reconcile_tickets(client)
                ticket.refresh_from_db()
                if predicate():
                    return
                time.sleep(0.1)
            pytest.fail("流程没有到达预期状态")

        drain_until(lambda: ticket.tasks.filter(status="pending").count() == 2)
        assert ticket.form_data["approved"] is True
        service.operate(ticket, ticket.tasks.get(node_id="a", status="pending"), "submit", {}, "alice")
        assert ticket.tasks.filter(node_id="b", status="pending").exists()
        assert not ticket.auto_executions.filter(detail__node_id="notice").exists()
        with patch("apps.itsm.services.notify.service.dispatch_notification", return_value={"site": {"result": True}}) as notify:
            service.operate(ticket, ticket.tasks.get(node_id="b", status="pending"), "submit", {}, "bob")
            drain_until(lambda: ticket.status.key == "finished")
            notify.assert_called_once()
            assert notify.call_args.kwargs["site_only"] is True
        assert not ticket.tasks.filter(status__in=["pending", "claimed"]).exists()
    finally:
        client._request("DELETE", f"/flowable-rest/service/repository/deployments/{deployment['id']}", params={"cascade": "true"})


def test_old_release_and_unknown_start_recover_at_ticket_endpoint():
    import json

    from apps.itsm.flowable.client import FlowableError
    from apps.itsm.models import Ticket
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.tickets import tickets

    client = _client()
    key = "review_version_" + uuid4().hex[:12]
    workflow = Workflow.objects.create(name="旧版本恢复", key=key)
    deployments = []
    try:
        for number in (1, 2):
            deployment_id = client.deploy_bpmn(key, build_bpmn(DESIGN, key))["id"]
            deployments.append(deployment_id)
            WorkflowVersion.objects.create(
                workflow=workflow,
                version_no=number,
                design=DESIGN,
                process_definition_key=key,
                flowable_deployment_id=deployment_id,
                is_published=True,
            )
        older = workflow.versions.get(version_no=1)
        workflow.current_version = older
        workflow.save()
        payload = {"workflow_version_id": older.id, "is_test": True, "form_data": {"title": "结果核对"}, "creation_key": uuid4().hex}
        service = TicketService(client)
        start = client.start_process

        def lose_response(*args):
            start(*args)
            raise FlowableError(0, "响应丢失")

        with patch("apps.itsm.views.tickets._service", return_value=service), patch.object(
            client, "start_process", side_effect=lose_response
        ) as remote:

            def submit():
                return tickets(request("post", payload, username="owner", permissions=["ticket-View", "ticket-Add"]))

            assert submit().status_code == 502
            assert Ticket.objects.get().creation_state == "starting"
            confirmed = json.loads(submit().content)
            assert confirmed["result"], confirmed
            assert json.loads(submit().content)["data"]["id"] == confirmed["data"]["id"]
            assert remote.call_count == 1
        ticket = Ticket.objects.get()
        older.refresh_from_db()
        assert ticket.process_instance_id and ticket.tasks.filter(status="pending").count() == 1
        assert client.get_process_instance(ticket.process_instance_id)["processDefinitionId"] == older.process_definition_id
        assert older.process_definition_id != client.definition_for_deployment(deployments[-1], key)
    finally:
        for deployment_id in deployments:
            client._request("DELETE", f"/flowable-rest/service/repository/deployments/{deployment_id}", params={"cascade": "true"})


def test_real_multi_instance_sync_reads_all_task_pages():
    import copy

    from django.core.management import call_command

    call_command("init_itsm")
    client = _client()
    design = copy.deepcopy(DESIGN)
    approval = next(row for row in design["nodes"] if row["type"] == "approval")
    people = [f"user-{n}" for n in range(105)]
    approval["assignee"]["value"] = people
    approval["multi"]["mode"] = "all"
    key = "review_pages_" + uuid4().hex[:12]
    workflow = Workflow.objects.create(name="会签分页", key=key)
    deployment = client.deploy_bpmn(key, build_bpmn(design, key))
    try:
        version = WorkflowVersion.objects.create(
            workflow=workflow, version_no=1, design=design, process_definition_key=key, flowable_deployment_id=deployment["id"], is_published=True
        )
        engine = TicketService(client)
        ticket = engine.create(version, {"title": "105 人会签"}, "creator", is_test=True)
        with patch.object(client, "_request", wraps=client._request) as wire:
            engine.operate(ticket, ticket.tasks.get(status="pending"), "submit", {}, "creator")
            engine.sync_ticket(ticket)
        pages = [c.kwargs["params"]["start"] for c in wire.call_args_list if c.args[1].endswith("/runtime/tasks")]
        assert 100 in pages
        assert set(ticket.tasks.filter(status="pending").values_list("assignee", flat=True)) == set(people)
    finally:
        client._request("DELETE", f"/flowable-rest/service/repository/deployments/{deployment['id']}", params={"cascade": "true"})


def test_real_once_schedule_resumes_claim_and_creates_one_instance():
    import json

    from django.core.management import call_command
    from django.utils import timezone

    from apps.itsm.models.extend import ScheduledTask
    from apps.itsm.services import schedules

    call_command("init_itsm")
    client = _client()
    key = "review_scheduler_" + uuid4().hex[:12]
    workflow = Workflow.objects.create(name="恢复定时建单", key=key)
    design = {**DESIGN, "settings": {"is_test": True}}
    deployment = client.deploy_bpmn(key, build_bpmn(design, key))
    try:
        version = WorkflowVersion.objects.create(
            workflow=workflow, version_no=1, design=design, process_definition_key=key, flowable_deployment_id=deployment["id"], is_published=True
        )
        workflow.current_version = version
        workflow.save()
        due = timezone.now()
        item = ScheduledTask.objects.create(
            name="一次建单",
            created_by="owner",
            next_run_at=due,
            action=json.dumps({"mode": "once", "task": "create_ticket", "workflow_id": workflow.pk, "once_at": due.isoformat()}),
        )
        schedules._claim(item.pk, due)

        def service_for(*_):
            return TicketService(client)

        with patch.object(client, "start_process", wraps=client.start_process) as start:
            assert schedules.run_due(service_for, now=due) == 1
            assert schedules.run_due(service_for, now=due) == 0
            start.assert_called_once()
        run = item.runs.get()
        assert run.status == "succeeded" and run.ticket.creation_key == f"schedule-{run.pk}"
        assert set(run.ticket.tasks.filter(status="pending", node_id="approve").values_list("assignee", flat=True)) == {"alice", "bob"}
    finally:
        client._request("DELETE", f"/flowable-rest/service/repository/deployments/{deployment['id']}", params={"cascade": "true"})


def test_real_reopen_lost_reply_and_pre_send_crash_recovery():
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    from apps.itsm.flowable.client import FlowableError, NoStartedInstance
    from apps.itsm.models import Ticket
    from apps.itsm.models.ticket import TicketStartAttempt
    from apps.itsm.services.ticket.start_recovery import confirm_not_started, reconcile_starts

    call_command("init_itsm")
    client = _client()
    key = "recovery_" + uuid4().hex[:12]
    flow = Workflow.objects.create(name="轮次恢复", key=key)
    dep = client.deploy_bpmn(key, build_bpmn(DESIGN, key))
    try:
        version = WorkflowVersion.objects.create(
            workflow=flow,
            version_no=1,
            design=DESIGN,
            is_published=True,
            process_definition_key=key,
            flowable_deployment_id=dep["id"],
        )
        service = TicketService(client)
        real_start = client.start_process
        with patch.object(client, "start_process", side_effect=FlowableError(0, "模拟发送前中断")):
            with pytest.raises(FlowableError):
                service.create(version, {"title": "启动故障"}, "owner", is_test=True, creation_key="request-one")
        ticket = Ticket.objects.get(creation_key="request-one")
        attempt = TicketStartAttempt.objects.get(ticket=ticket)
        with pytest.raises(NoStartedInstance):
            client.instance_for_business_key(attempt.business_key, attempt.definition_id)
        TicketStartAttempt.objects.filter(pk=attempt.pk).update(sent_at=timezone.now() - timedelta(minutes=5))
        confirm_not_started(service, ticket, attempt.pk, "已确认测试请求在发送前退出", "manager")
        ticket.refresh_from_db()
        previous = ticket.process_instance_id
        assert previous == client.instance_for_business_key(attempt.business_key, attempt.definition_id)

        submit = ticket.tasks.get(status="pending")
        service.operate(ticket, submit, "withdraw", {}, "owner")
        payload = {"reopen_from": previous, "opinion": "再审"}

        def lose_reply(*args):
            real_start(*args)
            raise FlowableError(0, "模拟引擎成功后的应答丢失")

        with patch.object(client, "start_process", side_effect=lose_reply) as start:
            with pytest.raises(FlowableError):
                service.operate(ticket, None, "reopen", payload, "owner")
            assert reconcile_starts(client) == 1
            service.operate(ticket, None, "reopen", payload, "owner")
            start.assert_called_once()
        ticket.refresh_from_db()
        reopened = ticket.start_attempts.get(kind="reopen")
        assert ticket.process_instance_id != previous
        assert ticket.process_instance_id == client.instance_for_business_key(reopened.business_key, reopened.definition_id)
        assert ticket.tasks.filter(node_id="submit", status="pending").count() == 1
        assert TicketLog.objects.filter(ticket=ticket, action="reopen").count() == 1
    finally:
        client._request("DELETE", f"/flowable-rest/service/repository/deployments/{dep['id']}", params={"cascade": "true"})


def test_real_manual_receipts_survive_lost_responses():
    from django.core.management import call_command

    from apps.itsm.flowable.client import FlowableError
    from apps.itsm.services.ticket.manual_recovery import active_operations, reconcile_manual_operations

    call_command("init_itsm")
    client = _client()
    key = "manual_receipts_" + uuid4().hex[:12]
    workflow = Workflow.objects.create(name="人工操作回执", key=key)
    deployment = client.deploy_bpmn(key, build_bpmn(DESIGN, key))
    try:
        version = WorkflowVersion.objects.create(
            workflow=workflow,
            version_no=1,
            design=DESIGN,
            process_definition_key=key,
            flowable_deployment_id=deployment["id"],
            is_published=True,
        )
        service = TicketService(client)
        ticket = service.create(version, {"title": "人工操作回执"}, "creator", is_test=True)

        def verify(method, action, data, actor, task):
            remote = getattr(client, method)

            def lose_response(*args, **kwargs):
                remote(*args, **kwargs)
                raise FlowableError(0, "应答丢失")

            with patch.object(client, method, side_effect=lose_response) as send:
                with pytest.raises(FlowableError):
                    service.operate(ticket, task, action, data, actor)
                op = active_operations(ticket).get()
                assert client.confirmed_manual_action(op), action
                assert reconcile_manual_operations(client) == 1
                assert reconcile_manual_operations(client) == 0
                assert send.call_count == 1
            assert TicketLog.objects.filter(ticket=ticket, action=action, detail__opinion=data["opinion"]).count() == 1

        from apps.system_mgmt.models import User

        User.objects.create(domain=ticket.domain, username="handler", display_name="处理人")
        submit = ticket.tasks.get(status="pending")
        verify("set_process_suspended", "suspend", {"opinion": "暂停确认"}, "creator", submit)
        verify("set_process_suspended", "resume", {"opinion": "恢复确认"}, "creator", submit)
        verify("update_task_assignee", "transfer", {"target": "handler", "opinion": "转交确认"}, "creator", submit)
        verify("complete_task", "submit", {"opinion": "提交确认"}, "handler", submit)
        approve = ticket.tasks.filter(status="pending", node_id="approve").first()
        verify("change_state", "return", {"return_mode": "submit", "opinion": "退回确认"}, approve.assignee, approve)
        verify("delete_process_instance", "withdraw", {"opinion": "撤回确认"}, "creator", None)
    finally:
        client._request("DELETE", f"/flowable-rest/service/repository/deployments/{deployment['id']}", params={"cascade": "true"})
