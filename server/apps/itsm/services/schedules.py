import json
from datetime import datetime, timedelta

from croniter import CroniterBadDateError, croniter
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.logger import itsm_logger as logger
from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import Ticket, Workflow
from apps.itsm.models.extend import ScheduledRun, ScheduledTask
from apps.itsm.services.ticket.service import _find_node


def schedule_config(item):
    if not isinstance(item.action, str) or len(item.action) > 32768:
        raise ValueError("定时任务参数格式错误或超过 32 KB")
    if item.action.startswith("create_ticket:"):
        return {"task": "create_ticket", "mode": "cron", "workflow_id": int(item.action.split(":", 1)[1])}
    config = json.loads(item.action)
    if not isinstance(config, dict) or config.get("task") not in {"create_ticket", "remind"}:
        raise ValueError("请选择有效的定时任务类型")
    if config.get("mode") not in {"once", "cron"}:
        raise ValueError("请选择单次或周期执行")
    if not isinstance(config.get("form_data", {}), dict):
        raise ValueError("表单参数必须是 JSON 对象")
    return config


def target_workflow(item, config):
    workflow_id = config.get("workflow_id")
    if type(workflow_id) is not int:
        raise ValueError("请选择已发布流程")
    workflow = (
        Workflow.objects.select_related("current_version")
        .filter(
            id=workflow_id,
            domain=item.domain,
            is_enabled=True,
            current_version__is_published=True,
            current_version__domain=item.domain,
        )
        .first()
    )
    if not workflow or not workflow.current_version.process_definition_key:
        raise ValueError("目标流程未发布或不可用")
    return workflow


def _next_cron(item, now):
    if not isinstance(item.cron, str) or len(item.cron) > 64 or len(item.cron.split()) != 5 or not croniter.is_valid(item.cron):
        raise ValueError("请输入有效的五段 Cron 表达式")
    try:
        return croniter(item.cron, timezone.localtime(now, timezone.get_default_timezone())).get_next(datetime)
    except CroniterBadDateError as exc:
        raise ValueError("Cron 表达式没有可执行的时间") from exc


def register_schedule(item, *, now=None, preserve_next=False):
    now = now or timezone.now()
    config = schedule_config(item)
    if config["task"] == "create_ticket":
        target_workflow(item, config)
    if config["mode"] == "once":
        value = config.get("once_at")
        due = parse_datetime(value) if isinstance(value, str) else None
        if not due or timezone.is_naive(due):
            raise ValueError("请选择有效的执行时间")
        if item.runs.filter(due_at=due).exists():
            due = None  # 已领取过的单次任务不可因编辑再次执行。
        elif due <= now and item.is_enabled and not preserve_next:
            raise ValueError("单次执行时间必须晚于当前时间")
    else:
        due = _next_cron(item, now)
    if not item.is_enabled:
        due = None
    elif preserve_next:
        due = item.next_run_at
    item.next_run_at = due
    item.save(update_fields=["next_run_at", "updated_at"])


@transaction.atomic
def _claim(schedule_id, now):
    item = ScheduledTask.objects.select_for_update().filter(id=schedule_id, is_enabled=True, next_run_at__lte=now).first()
    if item is None:
        return None
    config = schedule_config(item)
    ScheduledRun.objects.get_or_create(
        schedule=item,
        due_at=item.next_run_at,
        defaults={"schedule_name": item.name, "domain": item.domain, "created_by": item.updated_by or item.created_by, "status": "pending", "configuration": config},
    )
    # 调度恢复后每个任务补一次，跳过后续积压时点，防止停机后集中建单。
    item.next_run_at = _next_cron(item, now) if config["mode"] == "cron" else None
    item.save(update_fields=["next_run_at", "updated_at"])


def _create_ticket(service, item, run, config):
    version = target_workflow(item, config).current_version
    if service.client is None:
        raise ValueError("流程引擎未配置")
    data = {"title": run.schedule_name, **config.get("form_data", {})}
    # 先提交建单与关联记录，再推进提单节点；推进失败时原工单仍可追踪。
    ticket = service.create(version, data, run.created_by, creation_key=f"schedule-{run.pk}")
    run.ticket = ticket
    run.save(update_fields=["ticket", "updated_at"])
    submit_node = _find_node(version.design, node_type="submit")
    if submit_node:
        task = ticket.tasks.filter(node_id=submit_node["id"], status__in=["pending", "claimed"]).get()
        service.operate(ticket, task, "submit", {}, run.created_by)
    return ticket


def _run(service_for, item, run, config):
    from apps.itsm.services.notify.service import dispatch_notification

    status, message = "succeeded", ""
    phase = "建单"
    try:
        if config["task"] == "create_ticket":
            _create_ticket(service_for(item, run, config), item, run, config)
        if config["task"] == "remind" or config.get("notify"):
            phase = "通知"
            result = dispatch_notification(
                "schedule",
                {"title": run.schedule_name, "content": run.schedule_name},
                [run.created_by],
                event_key=f"itsm-schedule-run-{run.id}",
                site_only=bool(run.ticket and run.ticket.is_test),
                domain=item.domain,
            )
            if not (result.get("site") or {}).get("result"):
                raise ValueError("通知未投递")
    except Exception as exc:
        status = "failed"
        if isinstance(exc, FlowableError):
            message = "流程引擎未确认执行结果，请核对工单及流程实例"
        elif phase == "通知":
            message = "通知未确认送达"
        elif run.ticket_id:
            message = "工单已创建，提单节点未完成，请打开工单处理"
        else:
            message = "建单失败，请检查流程是否可用及提单必填参数"
        logger.warning("定时任务失败 run_id=%s failed_stage=%s error_type=%s", run.id, phase, type(exc).__name__)
    ticket_id = run.ticket_id or _created_ticket_id(run)
    ScheduledRun.objects.filter(pk=run.pk, status__in=["running", "unconfirmed"]).update(status=status, ticket_id=ticket_id, message=message, finished_at=timezone.now(), updated_at=timezone.now())


def _created_ticket_id(run):
    return Ticket.objects.filter(domain=run.domain, creator=run.created_by, creation_key=f"schedule-{run.pk}").values_list("pk", flat=True).first()


def _reconcile_interrupted(now, limit):
    # 已经进入外部动作阶段的旧执行不能重放。保留可追踪的原工单，明确标记需要核对的结果。
    cutoff = now - timedelta(minutes=30)
    runs = ScheduledRun.objects.filter(status="running", updated_at__lt=cutoff).order_by("updated_at", "id")[:limit]
    for run in runs:
        ticket_id = run.ticket_id or _created_ticket_id(run)
        ScheduledRun.objects.filter(pk=run.pk, status="running", updated_at__lt=cutoff).update(
            status="unconfirmed", ticket_id=ticket_id, message="执行中断，请核对已关联的工单或通知记录", finished_at=now, updated_at=now,
        )


def run_due(service_for, *, now=None, limit=10):
    now = now or timezone.now()
    ids = list(ScheduledTask.objects.filter(is_enabled=True, next_run_at__lte=now).order_by("next_run_at", "id").values_list("id", flat=True)[:limit])
    for schedule_id in ids:
        _claim(schedule_id, now)
    _reconcile_interrupted(now, limit)
    count = 0
    pending = ScheduledRun.objects.select_related("schedule").filter(status="pending").order_by("due_at", "id")[:limit]
    for run in pending:
        if not ScheduledRun.objects.filter(pk=run.pk, status="pending").update(status="running", updated_at=now):
            continue
        if not run.schedule:
            ScheduledRun.objects.filter(pk=run.pk).update(status="failed", message="计划已删除", finished_at=now, updated_at=now)
            continue
        _run(service_for, run.schedule, run, run.configuration)
        count += 1
    return count
