from django.conf import settings
from django.db import transaction

from apps.core.logger import itsm_logger as logger
from apps.core.logger import safe_exception_info
from apps.itsm.models import TicketTag, Trigger, TriggerLog
from apps.itsm.services.form.rules import match_when
from apps.itsm.services.notify.recipients import active_users
from apps.itsm.services.notify.service import ticket_notice_variables
from apps.itsm.services.trigger_config import EVENT_ALIASES, actions_for, normalize_condition, scope_matches, status_target
from apps.itsm.services.trigger_delivery import schedule_delivery
from apps.itsm.services.trigger_fields import trigger_condition_values
from apps.itsm.services.trigger_notice import resolve_notice


def fire_triggers(ticket, action: str, operator: str, *, current_tasks=None) -> None:
    event = EVENT_ALIASES.get(action, action)
    rules = Trigger.objects.filter(domain=ticket.domain, is_enabled=True, event__in={event, action}).order_by("pk")
    for trigger in rules:
        context = {
            "trigger": trigger,
            "trigger_name": trigger.name,
            "ticket_id": ticket.pk,
            "event": event,
            "domain": ticket.domain,
            "created_by": operator,
            "updated_by": operator,
        }
        try:
            with transaction.atomic():
                config = trigger.config or {}
                if not scope_matches(config.get("scope"), ticket):
                    continue
                fields = trigger_condition_values(ticket)
                if not match_when(normalize_condition(config.get("when")), fields):
                    continue
                actions = actions_for(trigger)
        except Exception as error:
            _record_failure(context, "规则配置或条件无效", "evaluate", error)
            continue

        run_id = None
        for position, configured_action in enumerate(actions, 1):
            run_id = _run_action(ticket, {**context, "position": position, "run_id": run_id}, configured_action, current_tasks=current_tasks)


def _run_action(ticket, context, configured_action, *, current_tasks):
    kind, value = configured_action["type"], configured_action["value"]
    context = {**context, "action": kind}
    original_state = ticket.status, ticket.finished_at, ticket.updated_at
    failure = {"status": "目标状态无效，或当前状态不允许变更", "tag": "无法添加标签", "notice": "无法创建通知执行记录"}
    try:
        with transaction.atomic():
            if kind == "tag":
                tag, _created = TicketTag.objects.get_or_create(
                    domain=ticket.domain,
                    name=value,
                    defaults={"created_by": context["created_by"], "updated_by": context["updated_by"]},
                )
                ticket.tags.add(tag)
                log = _record(context, TriggerLog.Status.SUCCESS, f"已添加标签 {value}")
            elif kind == "status":
                from apps.itsm.services.ticket.service import TicketService

                if ticket.status and (ticket.status.is_terminal or ticket.status.key in {"finished", "terminated", "cancelled", "suspended"}):
                    raise ValueError("当前工单状态由流程操作管理")
                status = status_target(ticket.domain, value)
                TicketService()._set_status(ticket, status, context["created_by"])
                log = _record(context, TriggerLog.Status.SUCCESS, f"已变更状态为 {status.name}")
            else:
                payload = _notice_payload(ticket, context["trigger_name"], configured_action, current_tasks)
                log = _record(context, TriggerLog.Status.PENDING, "等待发送通知", delivery_payload=payload)
                schedule_delivery(log.pk)
    except Exception as error:
        ticket.status, ticket.finished_at, ticket.updated_at = original_state
        log = _record_failure(context, failure[kind], f"action_{kind}", error)
    return log.run_id if log is not None else context["run_id"]


def _notice_payload(ticket, trigger_name, action, current_tasks):
    notice = action.get("notice")
    if notice is None:
        recipients = [ticket.created_by or ticket.creator]
        recipient_ids = list(active_users(ticket.domain).filter(username__in=recipients).values_list("pk", flat=True))
        variables = ticket_notice_variables(ticket, link_to_ticket=True)
        base = (getattr(settings, "WEB_BASE_URL", "") or "").rstrip("/")
        variables["ticket_link"] = f"{base}{variables['ticket_path']}"
        content = action["value"] or trigger_name
    else:
        recipients, variables = resolve_notice(ticket, notice, current_tasks=current_tasks)
        content = action["value"] or f"{ticket.title}（{ticket.sn}）"
    variables.update(title=trigger_name, content=content)
    return {
        **({"recipient_ids": recipient_ids} if notice is None else {}),
        "notice": notice.model_dump(mode="json") if notice is not None else None,
        "variables": variables,
        "recipients": recipients,
        "is_test": ticket.is_test,
    }


def _record(context, status, message, **fields):
    log = TriggerLog.objects.create(**context, status=status, message=message, **fields)
    if log.run_id is None:
        log.run_id = log.pk
        log.save(update_fields=["run_id"])
    return log


def _record_failure(context, message, stage, error):
    logger.error(
        "触发器执行失败 trigger=%s ticket=%s failed_stage=%s error_type=%s",
        context["trigger"].pk,
        context["ticket_id"],
        stage,
        type(error).__name__,
        exc_info=safe_exception_info(error),
    )
    try:
        with transaction.atomic():
            return _record(context, TriggerLog.Status.FAILED, message)
    except Exception as log_error:
        logger.error(
            "触发器失败记录无法保存 trigger=%s ticket=%s failed_stage=persist error_type=%s",
            context["trigger"].pk,
            context["ticket_id"],
            type(log_error).__name__,
            exc_info=safe_exception_info(log_error),
        )
        return None
