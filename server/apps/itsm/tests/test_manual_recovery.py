from unittest.mock import Mock

import pytest

from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import TicketLog
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.tests import test_review_regressions

sample = test_review_regressions.sample


@pytest.mark.django_db
def test_ack_lost_after_approval_recovers_opinion_and_form_once(sample):
    ticket, task = sample
    version = ticket.workflow_version
    version.design["nodes"][1]["fallback"] = "handler"
    version.save()
    task.flowable_task_id = "engine-task"
    task.save()
    ticket.process_instance_id = "engine-instance"
    ticket.save()
    client = Mock()
    receipts = set()

    def complete(task_id, variables):
        assert task_id == "engine-task"
        receipts.add(variables["itsm_operation_receipt"])
        raise FlowableError(0, "模拟引擎已执行，应答中断")

    client.complete_task.side_effect = complete
    client.confirmed_manual_action.side_effect = lambda op: str(op.token) in receipts
    client.list_tasks_including_children.return_value = []
    client.get_process_instance.return_value = {"ended": True}
    service = TicketService(client)
    with pytest.raises(FlowableError):
        service.operate(ticket, task, "approve", {"opinion": "核查同意", "form_data": {"amount": 17}}, "handler")
    assert not TicketLog.objects.filter(ticket=ticket, action="approve").exists()
    from apps.itsm.services.ticket.manual_recovery import reconcile_manual_operations

    reconcile_manual_operations(client)
    reconcile_manual_operations(client)
    ticket.refresh_from_db()
    task.refresh_from_db()
    assert task.status == "done"
    assert ticket.form_data["amount"] == 17
    log = TicketLog.objects.get(ticket=ticket, action="approve")
    assert (log.operator, log.detail["opinion"]) == ("handler", "核查同意")
    client.complete_task.assert_called_once()


@pytest.mark.django_db
def test_engine_bound_action_cannot_finish_locally(sample):
    ticket, task = sample
    task.flowable_task_id = "engine-task"
    task.save()
    ticket.process_instance_id = "process"
    ticket.save()
    with pytest.raises(FlowableError):
        TicketService().operate(ticket, task, "approve", {"opinion": "等待引擎恢复"}, "handler")
    task.refresh_from_db()
    assert task.status == "pending"
    assert not TicketLog.objects.filter(ticket=ticket, action="approve").exists()


@pytest.mark.django_db
def test_unknown_response_blocks_competing_action_and_unauthorized_recovery(sample):
    from apps.itsm.services.ticket.actions import NodeActionValidationError
    from apps.itsm.services.ticket.manual_recovery import reconcile_manual_operations
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.tickets import operation_recovery

    ticket, task = sample
    version = ticket.workflow_version
    version.design["nodes"][1]["fallback"] = "handler"
    version.save()
    task.flowable_task_id = "lost-task"
    task.save()
    ticket.process_instance_id = "process"
    ticket.save()
    client = Mock()
    client.complete_task.side_effect = FlowableError(0, "连接中断")
    client.confirmed_manual_action.return_value = False
    service = TicketService(client)
    with pytest.raises(FlowableError):
        service.operate(ticket, task, "approve", {"opinion": "待核对"}, "handler")
    with pytest.raises(NodeActionValidationError):
        service.operate(ticket, task, "reject", {}, "handler")
    assert reconcile_manual_operations(client) == 0
    assert operation_recovery(request("post", username="owner", domain=ticket.domain), ticket.pk).status_code == 403
    assert not TicketLog.objects.filter(ticket=ticket, action="approve").exists()
    client.complete_task.assert_called_once()


def test_connect_timeout_is_safe_to_retry_but_read_timeout_is_ambiguous():
    import requests

    from apps.itsm.flowable.client import FlowableClient, FlowableNotSent

    client = FlowableClient("http://localhost", "user", "fixture")
    client.session = Mock()
    client.session.request.side_effect = requests.ConnectTimeout()
    with pytest.raises(FlowableNotSent):
        client.complete_task("task", {})
    client.session.request.side_effect = requests.ReadTimeout()
    with pytest.raises(FlowableError) as error:
        client.complete_task("task", {})
    assert not isinstance(error.value, FlowableNotSent)
    assert client.session.request.call_count == 2


@pytest.mark.django_db
def test_saving_new_subform_resumes_original_child_after_parent_save_failure(sample):
    from unittest.mock import patch

    from apps.itsm.models import Workflow, WorkflowVersion
    from apps.itsm.services.ticket.manual_recovery import active_operations, reconcile_manual_operations

    ticket, task = sample
    child_flow = Workflow.objects.create(name="关联", key="recovery-child")
    child_version = WorkflowVersion.objects.create(workflow=child_flow, version_no=1, is_published=True)
    form = ticket.workflow.form.current_version
    form.schema["fields"].append({"key": "children", "type": "subProcessForm", "props": {"workflow_version_id": child_version.pk}})
    form.save()
    service = TicketService()
    with patch.object(service, "_log", side_effect=RuntimeError("保存中断")):
        with pytest.raises(RuntimeError):
            service.operate(ticket, task, "save", {"form_data": {"children": [{"form_data": {"title": "子单"}}]}}, "handler")
    assert active_operations(ticket).get().status == "applied"
    assert ticket.relations.count() == 1
    assert reconcile_manual_operations(None) == 1
    ticket.refresh_from_db()
    assert ticket.relations.get().related_id == ticket.form_data["children"][0]["ticket_id"]
    assert TicketLog.objects.filter(ticket=ticket, action="save").count() == 1


@pytest.mark.django_db
def test_missing_runtime_and_history_cannot_mark_ticket_finished(sample):
    ticket, _ = sample
    ticket.process_instance_id = "lost-instance"
    ticket.save()
    client = Mock()
    client.get_process_instance.side_effect = FlowableError(404, "")
    client._request.side_effect = FlowableError(404, "")
    TicketService(client).finish_if_ended(ticket)
    ticket.refresh_from_db()
    assert ticket.status.key != "finished"


@pytest.mark.django_db
def test_abandon_requires_unchanged_evidence_and_records_actor(sample):
    from datetime import timedelta
    from uuid import uuid4

    from django.utils import timezone

    from apps.itsm.models.ticket import ManualOperation
    from apps.itsm.services.ticket.actions import NodeActionValidationError
    from apps.itsm.services.ticket.manual_recovery import abandon

    ticket, task = sample
    sent_at = (timezone.now() - timedelta(minutes=10)).isoformat()
    op = ManualOperation.objects.create(
        token=uuid4(),
        ticket=ticket,
        task=task,
        action="approve",
        operator="handler",
        status="sending",
        payload={"sent_at": sent_at},
        task_ref="runtime-task",
        process_id="expected",
    )
    body = {"token": str(op.token), "sent_at": sent_at, "verified": True, "reason": "出站日志已核实未发送"}
    service = TicketService(Mock())
    service.client.confirmed_manual_action.return_value = False
    service.client.manual_action_unchanged.return_value = False
    with pytest.raises(NodeActionValidationError):
        abandon(service, ticket, body, "admin")
    service.client.manual_action_unchanged.return_value = True
    with pytest.raises(NodeActionValidationError):
        abandon(service, ticket, {**body, "sent_at": "旧回执"}, "admin")
    abandon(service, ticket, body, "admin")
    op.refresh_from_db()
    assert op.status == "rejected"
    log = TicketLog.objects.get(ticket=ticket, action="manual_reconcile")
    assert (log.operator, log.detail["reason"]) == ("admin", body["reason"])
    assert not TicketLog.objects.filter(ticket=ticket, action="approve").exists()
    service.client.complete_task.assert_not_called()


@pytest.mark.django_db
def test_invalid_second_child_rolls_back_first_preparation(sample):
    from apps.itsm.models import Workflow, WorkflowVersion
    from apps.itsm.services.ticket.manual_recovery import active_operations

    ticket, task = sample
    child_flow = Workflow.objects.create(name="子单", key="validated-child")
    child_version = WorkflowVersion.objects.create(
        workflow=child_flow,
        version_no=1,
        is_published=True,
        process_definition_id="child:1:abc",
        design={"form_schema": {"fields": [{"key": "title", "type": "input", "required": True}]}},
    )
    form = ticket.workflow.form.current_version
    form.schema["fields"].append({"key": "children", "type": "subProcessForm", "props": {"workflow_version_id": child_version.pk}})
    form.save()
    client = Mock()
    client.start_process.return_value = {"id": "child-id"}
    client.list_tasks_including_children.return_value = []
    rows = [{"form_data": {"title": "首行"}}, {"form_data": {}}]
    with pytest.raises(ValueError):
        TicketService(client).operate(ticket, task, "save", {"form_data": {"children": rows}}, "handler")
    assert not active_operations(ticket).exists()
    assert not ticket.relations.exists()
    client.start_process.assert_not_called()


@pytest.mark.django_db
def test_missing_runtime_task_reference_cannot_complete_bound_ticket(sample):
    from apps.itsm.services.ticket.actions import NodeActionValidationError

    ticket, task = sample
    ticket.process_instance_id = "existing-instance"
    ticket.save()
    assert not task.flowable_task_id
    for client in [None, Mock()]:
        with pytest.raises(NodeActionValidationError):
            TicketService(client).operate(ticket, task, "approve", {}, "handler")
    task.refresh_from_db()
    assert task.status == "pending"
    assert not TicketLog.objects.filter(ticket=ticket, action="approve").exists()
