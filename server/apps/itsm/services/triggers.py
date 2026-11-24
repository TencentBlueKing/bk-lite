from functools import partial

from django.conf import settings
from django.db import transaction

from apps.core.logger import itsm_logger as logger
from apps.itsm.models import TicketTag, Trigger, TriggerLog
from apps.itsm.services.form.rules import match_when
from apps.itsm.services.notify.service import dispatch_notification, ticket_notice_variables
from apps.itsm.services.trigger_config import EVENT_ALIASES, actions_for, normalize_condition, scope_matches, status_target
from apps.itsm.services.trigger_fields import trigger_condition_values
from apps.itsm.services.trigger_notice import deliver_configured_notice, resolve_notice


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
            _record_failure(context, "规则配置或条件无效", error)
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
            elif "notice" in configured_action:
                notice = configured_action["notice"]
                recipients, variables = resolve_notice(ticket, notice, current_tasks=current_tasks)
                variables.update(title=context["trigger_name"], content=value or f"{ticket.title}（{ticket.sn}）")
                log = _record(context, TriggerLog.Status.PENDING, "等待发送通知")
                transaction.on_commit(partial(_deliver_selected_notice, log, notice, variables, recipients, ticket.is_test), robust=True)
            else:
                recipients = [ticket.created_by or ticket.creator]
                log = _record(context, TriggerLog.Status.PENDING, "等待发送通知")
                variables = ticket_notice_variables(ticket, link_to_ticket=True)
                base = (getattr(settings, "WEB_BASE_URL", "") or "").rstrip("/")
                variables["ticket_link"] = f"{base}{variables['ticket_path']}"
                variables.update(title=context["trigger_name"], content=value or context["trigger_name"])
                send = partial(_deliver_notice, log, variables, recipients, ticket.is_test)
                transaction.on_commit(send, robust=True)
    except Exception as error:
        ticket.status, ticket.finished_at, ticket.updated_at = original_state
        log = _record_failure(context, failure[kind], error)
    return log.run_id if log is not None else context["run_id"]


def _deliver_selected_notice(log, notice, variables, recipients, is_test):
    status, message = TriggerLog.Status.FAILED, "通知发送失败"
    try:
        success, message = deliver_configured_notice(
            notice, variables, recipients, domain=log.domain, event_key=f"itsm-trigger-{log.pk}", is_test=is_test
        )
        if success:
            status = TriggerLog.Status.SUCCESS
    except Exception as error:
        logger.warning("触发器通知发送失败 log=%s error_type=%s", log.pk, type(error).__name__)
    TriggerLog.objects.filter(pk=log.pk).update(status=status, message=message)


def _record(context, status, message):
    log = TriggerLog.objects.create(**context, status=status, message=message)
    if log.run_id is None:
        log.run_id = log.pk
        log.save(update_fields=["run_id"])
    return log


def _record_failure(context, message, error):
    logger.warning("触发器执行失败 trigger=%s event=%s error_type=%s", context["trigger"].pk, context["event"], type(error).__name__)
    try:
        with transaction.atomic():
            return _record(context, TriggerLog.Status.FAILED, message)
    except Exception as log_error:
        logger.error("触发器失败记录无法保存 trigger=%s error_type=%s", context["trigger"].pk, type(log_error).__name__)
        return None


def _deliver_notice(log, variables, recipients, site_only):
    status, message = TriggerLog.Status.FAILED, "通知发送失败"
    try:
        result = dispatch_notification(
            "trigger",
            variables,
            recipients,
            event_key=f"itsm-trigger-{log.pk}",
            site_only=site_only,
            domain=log.domain,
            im_link=variables["ticket_link"],
        )
        site, im = result["site"], result["im"]
        if site.get("result"):
            status, message = TriggerLog.Status.SUCCESS, "已发送站内通知"
            if im.get("partial_success") or (not im.get("result") and not im.get("skipped")):
                status, message = TriggerLog.Status.FAILED, "站内通知已发送，即时消息投递失败"
            elif im.get("result"):
                message = "已发送站内通知和即时消息"
    except Exception as error:
        logger.warning("触发器通知发送失败 log=%s error_type=%s", log.pk, type(error).__name__)
    TriggerLog.objects.filter(pk=log.pk).update(status=status, message=message)
