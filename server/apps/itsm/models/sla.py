from django.db import models

from apps.itsm.models.base import ItsmModel
from apps.itsm.models.ticket import Ticket
from apps.itsm.models.workflow import Workflow


class ServiceCalendar(ItsmModel):
    name = models.CharField(max_length=128)
    timezone = models.CharField(max_length=64, default="Asia/Shanghai")
    work_days = models.JSONField(default=list)
    work_start = models.CharField(max_length=5, default="09:00")
    work_end = models.CharField(max_length=5, default="18:00")

    class Meta:
        db_table = "itsm_service_calendar"


class SLAPolicy(ItsmModel):
    class Target(models.TextChoices):
        RESPONSE = "response", "响应"
        RESOLVE = "resolve", "解决"

    name = models.CharField(max_length=128)
    category = models.CharField(max_length=16, default="sla")
    workflow = models.ForeignKey(Workflow, null=True, blank=True, on_delete=models.CASCADE, related_name="sla_policies")
    target = models.CharField(max_length=16, choices=Target.choices)
    minutes = models.PositiveIntegerField()
    calendar = models.ForeignKey(ServiceCalendar, on_delete=models.PROTECT, related_name="policies")
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "itsm_sla_policy"
        unique_together = (("workflow", "target"),)


class TicketSLARecord(ItsmModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="sla_records")
    policy = models.ForeignKey(SLAPolicy, on_delete=models.PROTECT, related_name="records")
    target = models.CharField(max_length=16)
    start_at = models.DateTimeField()
    due_at = models.DateTimeField()
    paused_at = models.DateTimeField(null=True, blank=True)
    paused_seconds = models.PositiveIntegerField(default=0)
    finished_at = models.DateTimeField(null=True, blank=True)
    breached = models.BooleanField(default=False)

    class Meta:
        db_table = "itsm_ticket_sla_record"
        unique_together = (("ticket", "target"),)
