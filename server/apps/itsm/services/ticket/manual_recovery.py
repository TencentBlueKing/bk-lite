"""保存人工操作意图。Flowable 写入结果不明时按回执或精确目标状态核对。"""

from datetime import datetime, timedelta
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from apps.itsm.flowable.client import FlowableError, FlowableNotSent
from apps.itsm.models import Ticket, TicketLog, TicketStatus
from apps.itsm.models.ticket import ManualOperation
from apps.itsm.services.ticket.actions import NodeActionValidationError
from apps.itsm.services.ticket.service import TicketService, _form_variables, ticket_schema
from apps.itsm.services.ticket.subforms import has_subform_rows, materialize_subforms

COMPLETIONS = {"approve", "submit", "reject"}
ASSIGNMENTS = {"claim", "transfer"}
DELETIONS = {"withdraw", "terminate", "close"}
PENDING = ("prepared", "sending", "applied")
CONFIRM_AFTER = timedelta(minutes=5)


def active_operations(ticket):
    return ManualOperation.objects.filter(ticket=ticket, status__in=PENDING)


def requires_engine(ticket, task, action):
    if ticket.process_instance_id and action in COMPLETIONS | ASSIGNMENTS | {"return"} and not (task and task.flowable_task_id):
        raise NodeActionValidationError("待办缺少流程任务标识，请刷新核对")
    if action in COMPLETIONS | ASSIGNMENTS:
        return bool(task and task.flowable_task_id)
    return bool(ticket.process_instance_id and action in DELETIONS | {"suspend", "resume", "return"})


def creates_child(ticket, action, data):
    if action not in COMPLETIONS | {"save", "claim"}:
        return False
    incoming = data.get("form_data") or {}
    if not isinstance(incoming, dict):
        return False
    return has_subform_rows(ticket_schema(ticket), {**(ticket.form_data or {}), **incoming}, only_unprepared=True)


def prepare(service, ticket, task, action, data, operator, node, *, handover_id=None, local_parent=False):
    payload = {"data": data, "node": node, "previous_assignee": task.assignee if task else "", "local_parent": local_parent}
    transitions = {"withdraw": "cancelled", "terminate": "terminated", "close": "finished", "suspend": "suspended", "resume": "processing"}
    target = transitions.get(action)
    if action == "return":
        from apps.itsm.services.ticket.service import _find_node

        submit = _find_node(ticket.workflow_version.design, node_type="submit")
        target = "new" if data["return_node_id"] == submit.get("id") else "processing"
    if action in COMPLETIONS and not local_parent and ticket.status_id and ticket.status.key == "new":
        target = "processing"
    if target:
        payload["status_id"] = service._status_target(ticket, target).pk
    if handover_id is not None:
        payload["handover_id"] = handover_id
    token = uuid4()
    if action in COMPLETIONS | {"claim", "save"}:
        ticket.form_data = service._validated_form(ticket, node, data, task)
        materialize_subforms(service, ticket, ticket_schema(ticket), operator, operation_key=str(token), defer_children=True)
        payload["form"] = ticket.form_data
        if action in COMPLETIONS and not local_parent:
            payload["assignees"] = service._assignee_variables(ticket.workflow_version, ticket.creator, payload["form"], service_id=ticket.service_id)
    return ManualOperation.objects.create(
        ticket=ticket,
        task=task,
        token=token,
        action=action,
        operator=operator,
        payload=payload,
        task_ref=task.flowable_task_id if task else "",
        process_id=(task.process_instance_id if task and action in COMPLETIONS | ASSIGNMENTS else "") or ticket.process_instance_id,
    )


def _send(client, op):
    if op.action in COMPLETIONS:
        node_id = op.payload["node"]["id"]
        variables = {
            **_form_variables(op.payload["form"]),
            **op.payload["assignees"],
            "result": op.action,
            f"out_{node_id}_result": op.action,
            "itsm_operation_receipt": str(op.token),
        }
        client.complete_task(op.task_ref, variables)
    elif op.action in ASSIGNMENTS:
        target = op.operator if op.action == "claim" else op.payload["data"]["target"]
        client.update_task_assignee(op.task_ref, target)
    elif op.action in DELETIONS:
        client.delete_process_instance(op.process_id, reason=str(op.token))
    elif op.action in {"suspend", "resume"}:
        client.set_process_suspended(op.process_id, op.action == "suspend")
    elif op.action == "return":
        client.change_state(op.process_id, [op.payload["node"]["id"]], [op.payload["data"]["return_node_id"]])
    else:
        raise ValueError("未知引擎操作")


def _finish_handover(op):
    if not op.payload.get("handover_id"):
        return
    from apps.itsm.services.ticket.handover import _set_result

    if op.status == "done":
        _set_result(op.payload["handover_id"], op.task_id, "succeeded", "交接成功", {"unconfirmed"})
    elif op.status == "rejected":
        _set_result(op.payload["handover_id"], op.task_id, "failed", "已确认未完成转交，可重新执行", {"unconfirmed"})


def _send_claimed(client, operation):
    error = None
    # sending 已独立提交；行锁在 HTTP 请求结束后释放，避免人工撤销与在途写入竞争。
    with transaction.atomic():
        op = ManualOperation.objects.select_for_update().get(pk=operation.pk)
        if op.status != "sending":
            return
        try:
            _send(client, op)
        except FlowableNotSent as exc:
            error = exc
            op.status = "prepared"
        except FlowableError as exc:
            error = exc
            if 400 <= exc.status < 500 and exc.status not in {408, 429}:
                op.status = "rejected"
        else:
            op.status = "applied"
        op.save(update_fields=["status", "updated_at"])
        _finish_handover(op)
    if error is not None:
        raise error


def can_abandon(op):
    sent_at = op.payload.get("sent_at")
    return bool(op.status == "sending" and sent_at and datetime.fromisoformat(sent_at) <= timezone.now() - CONFIRM_AFTER)


def abandon(service, ticket, data, actor):
    reason = data.get("reason")
    if data.get("verified") is not True or not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
        raise NodeActionValidationError("请确认出站请求已结束且未被引擎受理，并填写核对依据")
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
        op = active_operations(ticket).select_for_update().first()
        if not op or not can_abandon(op) or str(op.token) != data.get("token") or op.payload["sent_at"] != data.get("sent_at"):
            raise NodeActionValidationError("核对记录已变更或仍在处理，请刷新")
        if service.client.confirmed_manual_action(op):
            op.status = "applied"
        elif service.client.manual_action_unchanged(op):
            op.status = "rejected"
        else:
            raise NodeActionValidationError("引擎状态不能证明原操作未执行，已保留操作记录")
        op.save(update_fields=["status", "updated_at"])
        _finish_handover(op)
        TicketLog.objects.create(
            ticket=ticket,
            domain=ticket.domain,
            action="manual_reconcile",
            operator=actor,
            message="管理员已核对引擎操作",
            detail={"reason": reason.strip(), "token": str(op.token), "result": op.status},
            created_by=actor,
            updated_by=actor,
        )
    if op.status == "applied":
        advance(service, op)
    return ticket


def advance(service, operation):
    if operation.status == "prepared":
        if operation.action == "return":
            ticket = Ticket.objects.only("creation_state").get(pk=operation.ticket_id)
            if ticket.creation_state != "complete" or ticket.start_attempts.exclude(state="complete").exists():
                raise NodeActionValidationError("流程启动仍在确认，已保留回退操作")
        if "form" in operation.payload:
            ticket = operation.ticket
            ticket.form_data = operation.payload["form"]
            materialize_subforms(service, ticket, ticket_schema(ticket), operation.operator, operation_key=str(operation.token))
            operation.payload["form"] = ticket.form_data
        now = timezone.now()
        local_parent = operation.payload.get("local_parent")
        operation.payload["sent_at"] = now.isoformat()
        claimed = ManualOperation.objects.filter(pk=operation.pk, status="prepared").update(
            status="applied" if local_parent else "sending",
            payload=operation.payload,
            updated_at=now,
        )
        if claimed and not local_parent:
            _send_claimed(service.client, operation)
    operation.refresh_from_db()
    if operation.status == "sending":
        if not service.client.confirmed_manual_action(operation):
            raise NodeActionValidationError("引擎操作尚无确认回执，请稍后核对")
        ManualOperation.objects.filter(pk=operation.pk, status="sending").update(status="applied", updated_at=timezone.now())
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(pk=operation.ticket_id)
        op = ManualOperation.objects.select_for_update().get(pk=operation.pk)
        if op.status == "done":
            return ticket
        if op.status != "applied":
            raise NodeActionValidationError("引擎操作未确认")
        if op.payload.get("status_id"):
            ticket._approved_transition = TicketStatus.objects.get(pk=op.payload["status_id"])
        service._apply_action(ticket, op.task, op.action, op.payload["data"], op.operator, op.payload["node"], saved_form=op.payload.get("form"))
        op.status = "done"
        op.save(update_fields=["status", "updated_at"])
        _finish_handover(op)
    if not op.payload.get("local_parent") and op.action in COMPLETIONS | {"return"}:
        service.sync_ticket(ticket)
        service.finish_if_ended(ticket, op.operator)
    return ticket


def reconcile_manual_operations(client, limit=100):
    due = list(ManualOperation.objects.filter(status__in=PENDING).order_by("updated_at", "pk")[:limit])
    applied = 0
    for op in due:
        try:
            advance(TicketService(client), op)
        except (FlowableError, ValueError):
            ManualOperation.objects.filter(pk=op.pk, status__in=PENDING).update(updated_at=timezone.now())
        else:
            applied += 1
    return applied
