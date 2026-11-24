from django.db import models

from apps.itsm.models.base import ItsmModel


class Integration(ItsmModel):
    name = models.CharField(max_length=128)
    kind = models.CharField(max_length=16, choices=[("api", "API 网关"), ("python", "Python 脚本"), ("todo", "待办对接")])
    config = models.JSONField(default=dict)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "itsm_integration"


class IntegrationRun(ItsmModel):
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=16, default="running")
    code = models.CharField(max_length=80, default="")
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "itsm_integration_run"


class TodoDelivery(ItsmModel):
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="deliveries")
    task = models.ForeignKey("itsm.TicketTask", on_delete=models.CASCADE)
    event_key = models.CharField(max_length=64, unique=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default="pending")
    attempts = models.PositiveIntegerField(default=0)
    code = models.CharField(max_length=80, default="")

    class Meta:
        db_table = "itsm_todo_delivery"


class TicketNoticeDelivery(models.Model):
    domain = models.CharField(max_length=100)
    event_key = models.CharField(max_length=200)
    event = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default="pending")
    message = models.CharField(max_length=200, default="")
    delivery_payload = models.JSONField(null=True)
    delivery_claimed_at = models.DateTimeField(null=True)
    delivery_attempts = models.PositiveSmallIntegerField(default=0)
    delivery_receipts = models.JSONField(default=dict)

    class Meta:
        db_table = "itsm_ticket_notice_delivery"
        unique_together = (("domain", "event_key"),)
        indexes = [models.Index(fields=["status", "id"], name="itsm_notice_due_idx")]


class EmailReceipt(models.Model):
    domain = models.CharField(max_length=100)
    mailbox = models.CharField(max_length=200)
    message_key = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default="pending")
    claimed_at = models.DateTimeField(null=True)
    service = models.ForeignKey("itsm.Service", on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    version = models.ForeignKey("itsm.WorkflowVersion", on_delete=models.PROTECT)
    ticket = models.ForeignKey("itsm.Ticket", on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "itsm_email_receipt"
        unique_together = (("domain", "mailbox", "message_key"),)
