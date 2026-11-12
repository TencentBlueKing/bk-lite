from django.db import models

from apps.itsm.models.base import ItsmModel


class HandlerGroup(ItsmModel):
    name = models.CharField(max_length=128)
    members = models.JSONField(default=list)
    leaders = models.JSONField(default=list)
    tags = models.JSONField(default=list)

    class Meta:
        db_table = "itsm_handler_group"


class TicketStatus(ItsmModel):
    class Kind(models.TextChoices):
        BUILTIN = "builtin", "内置"
        CUSTOM = "custom", "自定义"

    key = models.CharField(max_length=32)
    name = models.CharField(max_length=64)
    color = models.CharField(max_length=16, default="#1677ff")
    description = models.CharField(max_length=100, blank=True, default="")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.CUSTOM)
    is_terminal = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "itsm_ticket_status"
        unique_together = (("domain", "key"),)


class StatusTransition(ItsmModel):
    from_status = models.ForeignKey(TicketStatus, on_delete=models.CASCADE, related_name="outgoing")
    to_status = models.ForeignKey(TicketStatus, on_delete=models.CASCADE, related_name="incoming")
    name = models.CharField(max_length=64)
    is_builtin = models.BooleanField(default=False)

    class Meta:
        db_table = "itsm_status_transition"
        unique_together = (("from_status", "to_status", "name"),)


class NotifyTemplate(ItsmModel):
    event = models.CharField(max_length=64)
    channel_type = models.CharField(max_length=32, default="site")
    title_tpl = models.CharField(max_length=200)
    content_tpl = models.TextField()
    is_builtin = models.BooleanField(default=False)

    class Meta:
        db_table = "itsm_notify_template"
        unique_together = (("domain", "event", "channel_type"),)


class ItsmSetting(ItsmModel):
    key = models.CharField(max_length=64)
    value = models.JSONField(default=dict)

    class Meta:
        db_table = "itsm_setting"
        unique_together = (("domain", "key"),)
