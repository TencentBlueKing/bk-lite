from django.db import models

from apps.itsm.models.base import ItsmModel
from apps.itsm.models.org import TicketStatus
from apps.itsm.models.workflow import Workflow, WorkflowVersion


class Ticket(ItsmModel):
    sn = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=200)
    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name="tickets")
    workflow_version = models.ForeignKey(WorkflowVersion, null=True, blank=True, on_delete=models.PROTECT, related_name="tickets")
    status = models.ForeignKey(TicketStatus, null=True, blank=True, on_delete=models.PROTECT, related_name="tickets")
    creator = models.CharField(max_length=64)
    current_assignees = models.JSONField(default=list)
    form_data = models.JSONField(default=dict)
    process_instance_id = models.CharField(max_length=64, blank=True, default="")
    is_test = models.BooleanField(default=False)

    class Meta:
        db_table = "itsm_ticket"


class TicketTask(ItsmModel):
    class TaskStatus(models.TextChoices):
        PENDING = "pending", "待处理"
        CLAIMED = "claimed", "已认领"
        DONE = "done", "已完成"

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="tasks")
    flowable_task_id = models.CharField(max_length=64, blank=True, default="")
    node_id = models.CharField(max_length=64)
    node_name = models.CharField(max_length=128, blank=True, default="")
    assignee = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=TaskStatus.choices, default=TaskStatus.PENDING)

    class Meta:
        db_table = "itsm_ticket_task"


class TicketLog(ItsmModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="logs")
    task = models.ForeignKey(TicketTask, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs")
    action = models.CharField(max_length=32)
    operator = models.CharField(max_length=64)
    message = models.TextField(blank=True, default="")
    detail = models.JSONField(default=dict)

    class Meta:
        db_table = "itsm_ticket_log"
