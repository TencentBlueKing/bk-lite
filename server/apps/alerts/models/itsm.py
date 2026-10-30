import hashlib
from copy import deepcopy

from django.db import models
from django.utils import timezone

from apps.core.models.time_info import TimeInfo


class AlertItsmTicket(TimeInfo):
    alert = models.OneToOneField("alerts.Alert", on_delete=models.CASCADE, related_name="itsm_ticket")
    rule = models.ForeignKey("alerts.ActionRule", null=True, on_delete=models.SET_NULL)
    rule_name = models.CharField(max_length=100)
    team = models.JSONField(default=list)
    current_execution = models.ForeignKey("alerts.ActionExecution", null=True, on_delete=models.SET_NULL)
    connection = models.CharField(max_length=100, blank=True)
    instance_id = models.CharField(max_length=100, blank=True)
    close_alert_on_ticket_closed = models.BooleanField(default=False)
    ticket_id = models.CharField(max_length=128, null=True, blank=True)
    ticket_number = models.CharField(max_length=128, blank=True)
    ticket_title = models.CharField(max_length=500, blank=True)
    ticket_status = models.CharField(max_length=128, blank=True)
    status_label = models.CharField(max_length=128, blank=True)
    is_closed = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True)
    next_sync_at = models.DateTimeField(default=timezone.now, db_index=True)
    sync_claim = models.CharField(max_length=32, blank=True)
    sync_error = models.CharField(max_length=256, blank=True)
    sync_failures = models.PositiveIntegerField(default=0)
    close_error = models.CharField(max_length=256, blank=True)
    close_attempts = models.PositiveIntegerField(default=0)
    close_result = models.CharField(max_length=32, default="unprocessed")
    comment_event = models.CharField(max_length=32, blank=True)
    comment_error = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = "alerts_itsm_ticket"
        constraints = [models.UniqueConstraint(fields=["instance_id", "ticket_id"], name="alerts_itsm_unique_remote")]


class AlertItsmIntegration(TimeInfo):
    """当前团队的全局 ITSM 集成；凭据不进入规则和执行快照。"""

    team_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=100)
    enabled = models.BooleanField(default=False)
    config = models.JSONField(default=dict)
    encrypted_token = models.TextField()

    @property
    def reference(self):
        return f"integration:{self.pk}"

    def connection_config(self):
        from apps.alerts.itsm.config import BKLITE_RESPONSE_CONTRACT

        return {
            **{key: self.config[key] for key in ("url", "ca_pem", "failure_notification") if key in self.config},
            **deepcopy(BKLITE_RESPONSE_CONTRACT),
            "name": self.name,
            "teams": [self.team_id],
            "instance_id": "itsm:" + hashlib.sha256(self.config["url"].encode()).hexdigest(),
            "credential_id": self.pk,
        }
