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
