from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.itsm.flowable.client import FlowableError, FlowableNotSent, NoStartedInstance
from apps.itsm.models import Ticket, TicketLog, TicketStatus
from apps.itsm.models.ticket import TicketStartAttempt
from apps.itsm.services.todo_sync import schedule_sync

CONFIRM_AFTER = timedelta(minutes=2)


def _instance(service, attempt):
    """先提交发送标记；连接中断后，后续执行者只读取引擎历史。"""
    from apps.itsm.services.ticket.service import _form_variables

    if attempt.instance_id:
        return attempt.instance_id
    ticket = attempt.ticket
    variables = {}
    if attempt.state == "ready":
        variables = {
            "initiator": ticket.creator,
            **service._assignee_variables(ticket.workflow_version, ticket.creator, ticket.form_data, service_id=ticket.service_id),
            **_form_variables(ticket.form_data),
        }
    sent_at = timezone.now()
    with transaction.atomic():
        Ticket.objects.select_for_update().only("id").get(pk=ticket.pk)
        claimed = attempt.state == "ready" and TicketStartAttempt.objects.filter(pk=attempt.pk, state="ready").update(
            state="sending", sent_at=sent_at
        )
        if claimed and attempt.kind == "initial":
            Ticket.objects.filter(pk=ticket.pk, creation_state="prepared").update(creation_state="starting")
    try:
        with transaction.atomic():
            current = TicketStartAttempt.objects.select_for_update().get(pk=attempt.pk)
            if current.instance_id:
                return current.instance_id
            if current.state != "sending":
                raise FlowableError(409, "启动操作已更新，请刷新")
            if claimed and current.sent_at == sent_at:
                started = service.client.start_process(current.definition_id, current.business_key, variables)
                instance_id = str(started.get("id") or "")
            else:
                instance_id = service.client.instance_for_business_key(current.business_key, current.definition_id)
            if not instance_id:
                raise FlowableError(502, "引擎未返回流程实例标识")
            current.instance_id = instance_id
            current.state = "bound"
            current.save(update_fields=["instance_id", "state"])
            return instance_id
    except FlowableNotSent:
        if claimed:
            TicketStartAttempt.objects.filter(pk=attempt.pk, state="sending", sent_at=sent_at).update(state="ready")
        raise


def initial_start(service, ticket):
    if ticket.process_instance_id:
        return
    definition_id = service._definition_id(ticket.workflow_version)
    with transaction.atomic():
        current = Ticket.objects.select_for_update().get(pk=ticket.pk)
        if current.process_instance_id:
            ticket.refresh_from_db()
            return
        legacy_sending = current.creation_state == "starting"
        attempt, _ = TicketStartAttempt.objects.get_or_create(
            ticket=current,
            kind="initial",
            previous_instance="",
            defaults={
                "business_key": current.sn,
                "operator": current.creator,
                "definition_id": definition_id,
                "state": "sending" if legacy_sending else "ready",
                "sent_at": timezone.now() if legacy_sending else None,
            },
        )
    instance_id = _instance(service, attempt)
    Ticket.objects.filter(pk=ticket.pk, process_instance_id="", creation_state__in=["prepared", "starting"]).update(
        process_instance_id=instance_id, creation_state="bound"
    )
    ticket.refresh_from_db()


def reopen_ticket(service, ticket, task, data, operator, privileged):
    from apps.itsm.services.ticket.manual_recovery import active_operations

    if not service.client:
        raise FlowableError(503, "流程引擎未配置")
    with transaction.atomic():
        current = Ticket.objects.select_for_update().get(pk=ticket.pk)
        if active_operations(current).exists() or current.creation_state != "complete":
            raise ValueError("工单有待核对的操作")
        task = current.tasks.get(pk=task.pk) if task else None
        if "reopen_from" in data and data["reopen_from"] != current.process_instance_id:
            service.authorize(current, None, "reopen", operator, privileged)
            previous = data["reopen_from"]
            if isinstance(previous, str) and current.start_attempts.filter(kind="reopen", previous_instance=previous, state="complete").exists():
                return current
            raise ValueError("流程轮次已变更，请刷新")
        _, data = service._validate_action(current, task, "reopen", data, operator, privileged, None, False)
        previous = current.process_instance_id
        attempt = current.start_attempts.filter(kind="reopen", previous_instance=previous).first()
        if attempt is None:
            service._status_target(current, "processing")
            if previous:
                try:
                    active = service.client.get_process_instance(previous)
                except FlowableError as exc:
                    if exc.status != 404:
                        raise
                else:
                    if not active.get("ended"):
                        raise FlowableError(409, "原流程实例仍在运行，请先核对")
            attempt = TicketStartAttempt.objects.create(
                ticket=current,
                kind="reopen",
                previous_instance=previous,
                business_key=f"{current.sn}:reopen:{uuid4().hex}",
                definition_id=service._definition_id(current.workflow_version),
                operator=operator,
                opinion=data.get("opinion", ""),
            )
    return _finish_reopen(service, attempt)


def _finish_reopen(service, attempt):
    instance_id = _instance(service, attempt)
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(pk=attempt.ticket_id)
        attempt = TicketStartAttempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.state == "complete":
            return ticket
        if (
            ticket.process_instance_id != attempt.previous_instance
            or not ticket.status_id
            or ticket.status.key not in {"finished", "cancelled", "terminated"}
        ):
            raise FlowableError(409, "原工单状态发生变化，需要核对重开结果")
        # 该轮创建前已校验允许重开。回执到达后按当时获准的状态转换落库。
        ticket._approved_transition = TicketStatus.objects.get(key="processing")
        service._set_status(ticket, "processing")
        ticket.process_instance_id = instance_id
        ticket.save(update_fields=["process_instance_id", "updated_at"])
        ticket.tasks.filter(status__in=["pending", "claimed"]).update(status="done")
        service.sync_ticket(ticket)
        service._log(ticket, None, "reopen", {"round_started_at": attempt.created_at.isoformat(), "opinion": attempt.opinion}, attempt.operator)
        attempt.state = "complete"
        attempt.save(update_fields=["state"])
        schedule_sync(ticket)
        return ticket


def _recover(service, attempt):
    if attempt.kind == "reopen":
        return _finish_reopen(service, attempt)
    return service._resume_creation(attempt.ticket)


def recover_attempt(service, ticket, attempt_id):
    attempt = ticket.start_attempts.get(pk=attempt_id)
    if attempt.state == "complete":
        return ticket
    if not service.client:
        raise FlowableError(503, "流程引擎未配置")
    return _recover(service, attempt)


def confirm_not_started(service, ticket, attempt_id, reason, operator, *, expected_sent_at=None):
    if not isinstance(reason, str) or not (1 <= len(reason.strip()) <= 1000):
        raise ValueError("请填写引擎未受理的核对依据（最多 1000 字）")
    if not service.client:
        raise FlowableError(503, "流程引擎未配置")
    with transaction.atomic():
        current = Ticket.objects.select_for_update().get(pk=ticket.pk)
        attempt = current.start_attempts.select_for_update().get(pk=attempt_id)
        if (
            attempt.state != "sending"
            or not attempt.sent_at
            or attempt.sent_at > timezone.now() - CONFIRM_AFTER
            or (expected_sent_at is not None and attempt.sent_at.isoformat() != expected_sent_at)
        ):
            raise ValueError("启动仍在处理，或核对记录已变更，请刷新")
        if attempt.kind == "reopen" and current.process_instance_id != attempt.previous_instance:
            raise ValueError("工单流程轮次已变更")
        if attempt.kind == "initial" and current.process_instance_id:
            raise ValueError("工单已绑定流程实例")
        try:
            instance_id = service.client.instance_for_business_key(attempt.business_key, attempt.definition_id)
        except NoStartedInstance:
            attempt.state = "ready"
        else:
            attempt.state = "bound"
            attempt.instance_id = instance_id
        attempt.confirmations = [
            *attempt.confirmations,
            {
                "sent_at": attempt.sent_at.isoformat(),
                "checked_at": timezone.now().isoformat(),
                "operator": operator,
                "reason": reason.strip(),
                "result": attempt.state,
            },
        ]
        attempt.save(update_fields=["state", "instance_id", "confirmations"])
        TicketLog.objects.create(
            ticket=current,
            domain=current.domain,
            action="start_reconcile",
            operator=operator,
            message="管理员已核对流程启动记录",
            detail={"state": attempt.state},
            created_by=operator,
            updated_by=operator,
        )
    return _recover(service, attempt)


def start_recovery_info(ticket, can_confirm):
    attempt = ticket.start_attempts.exclude(state="complete").order_by("-id").first()
    if not attempt:
        return None
    return {
        "id": attempt.pk,
        "kind": attempt.kind,
        "state": attempt.state,
        "business_key": attempt.business_key,
        "sent_at": attempt.sent_at.isoformat() if attempt.sent_at else None,
        "can_confirm": bool(can_confirm and attempt.state == "sending" and attempt.sent_at and attempt.sent_at <= timezone.now() - CONFIRM_AFTER),
    }


def reconcile_starts(client, limit=100):
    from django.core.cache import cache

    from apps.itsm.services.ticket.service import TicketService

    if not client:
        return 0
    service = TicketService(client)
    pending = Ticket.objects.filter(
        ~Q(creation_state="complete") | Q(start_attempts__kind="reopen", start_attempts__state__in=["ready", "sending", "bound"])
    ).distinct()
    cursor_key = "itsm:start-recovery-cursor"
    cursor = int(cache.get(cursor_key) or 0)
    ids = list(pending.filter(pk__gt=cursor).order_by("pk").values_list("pk", flat=True)[:limit])
    if not ids and cursor:
        ids = list(pending.order_by("pk").values_list("pk", flat=True)[:limit])
    completed = 0
    for ticket in Ticket.objects.select_related("workflow_version").filter(pk__in=ids):
        try:
            if ticket.creation_state != "complete":
                service._resume_creation(ticket)
            else:
                attempt = ticket.start_attempts.filter(kind="reopen").exclude(state="complete").first()
                if not attempt:
                    continue
                _finish_reopen(service, attempt)
        except (FlowableError, ValueError, PermissionError):
            continue
        completed += 1
    cache.set(cursor_key, max(ids) if ids else 0, timeout=600)
    return completed
