from json import JSONDecodeError

from django.db import transaction

from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import Ticket, TicketTask
from apps.itsm.models.extend import Handover
from apps.itsm.services.ticket.actions import validated_opinion
from apps.itsm.services.ticket.batch import validate_ids
from apps.itsm.services.ticket.service import TaskAssigneeChanged, TransferRejected
from apps.itsm.services.ticket.transfer import ASSIGNEE_MAX_LENGTH

ACTIVE_STATUSES = (TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED)
RETRYABLE_RESULTS = {"pending", "failed"}


def handover_user(value):
    username = value.strip() if isinstance(value, str) else ""
    if not username or len(username) > ASSIGNEE_MAX_LENGTH:
        raise ValueError("请选择有效的交接人员")
    return username


def prepare_handover(item, service):
    item.from_user = handover_user(item.from_user)
    item.to_user = handover_user(item.to_user)
    item.opinion = validated_opinion(item.opinion)
    if item.from_user == item.to_user:
        raise ValueError("交出人和接收人必须不同")
    item.ticket_ids = validate_ids(item.ticket_ids)
    if Ticket.objects.filter(domain=item.domain, pk__in=item.ticket_ids).count() != len(item.ticket_ids):
        raise PermissionError()
    tasks = list(
        TicketTask.objects.filter(ticket__domain=item.domain, ticket_id__in=item.ticket_ids, assignee=item.from_user, status__in=ACTIVE_STATUSES)
        .select_related("ticket", "ticket__status", "ticket__workflow_version")
        .order_by("pk")
    )
    if {task.ticket_id for task in tasks} != set(item.ticket_ids):
        raise ValueError("部分所选工单已没有该交出人的待办")
    for task in tasks:
        service.check_transfer_target(task.ticket, task, item.to_user, item.created_by or item.from_user, privileged=True, opinion=item.opinion)
    item.results = [{"ticket_id": task.ticket_id, "task_id": task.id, "status": "pending", "message": "待执行"} for task in tasks]
    item.save()


@transaction.atomic
def _set_result(item_id, task_id, status, message, allowed):
    item = Handover.objects.select_for_update().get(pk=item_id)
    result = next(row for row in item.results if row["task_id"] == task_id)
    if result["status"] not in allowed:
        return False
    result.update(status=status, message=message)
    item.save(update_fields=["results", "updated_at"])
    return True


def run_handover(item, service, actor):
    for result in item.results:
        task_id = result["task_id"]
        if result["status"] not in RETRYABLE_RESULTS or not _set_result(item.pk, task_id, "unconfirmed", "结果待核对，请勿重复转交", RETRYABLE_RESULTS):
            continue
        try:
            with transaction.atomic():
                task = TicketTask.objects.select_related("ticket").get(pk=task_id, ticket_id=result["ticket_id"], ticket__domain=item.domain)
                service.operate(
                    task.ticket,
                    task,
                    "transfer",
                    {"target": item.to_user, "opinion": item.opinion},
                    actor,
                    privileged=True,
                    expected_assignee=item.from_user,
                )
                _set_result(item.pk, task_id, "succeeded", "交接成功", {"unconfirmed"})
        except (TaskAssigneeChanged, TicketTask.DoesNotExist, Ticket.DoesNotExist):
            _set_result(item.pk, task_id, "skipped", "原待办或处理人已变化，已跳过", {"unconfirmed"})
        except TransferRejected:
            _set_result(item.pk, task_id, "failed", "待办暂时无法转交所选人员", {"unconfirmed"})
        except FlowableError as exc:
            if 400 <= exc.status < 500 and exc.status != 408:
                _set_result(item.pk, task_id, "failed", "流程引擎拒绝了转交，可核对后重试", {"unconfirmed"})
        except JSONDecodeError:
            continue
    item.refresh_from_db(fields=["results"])
