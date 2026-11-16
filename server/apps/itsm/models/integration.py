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
