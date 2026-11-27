from django.db import models
from django.utils import timezone

from apps.itsm.models.base import ItsmModel
from apps.itsm.models.workflow import Workflow


class ServiceCatalog(ItsmModel):
    name = models.CharField(max_length=128)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    order = models.PositiveIntegerField(default=0)
    icon = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "itsm_service_catalog"


class Service(ItsmModel):
    name = models.CharField(max_length=128)
    catalog = models.ForeignKey(ServiceCatalog, null=True, blank=True, on_delete=models.SET_NULL, related_name="services")
    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name="services")
    icon = models.CharField(max_length=64, blank=True, default="")
    description = models.CharField(max_length=500, blank=True, default="")
    is_enabled = models.BooleanField(default=True)
    handler_group = models.ForeignKey("itsm.HandlerGroup", null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_services")
    is_hot = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    visibility = models.CharField(max_length=16, choices=[("all", "全部用户"), ("restricted", "指定用户和组")], default="all")
    visible_users = models.JSONField(default=list)
    visible_groups = models.JSONField(default=list)

    class Meta:
        db_table = "itsm_service"


class ServiceFavorite(ItsmModel):
    username = models.CharField(max_length=64)
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="favorites")

    class Meta:
        db_table = "itsm_service_favorite"
        unique_together = (("domain", "username", "service"),)


class ServiceRecent(ItsmModel):
    username = models.CharField(max_length=64)
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="recents")
    last_used_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "itsm_service_recent"
        unique_together = (("domain", "username", "service"),)


class TicketFormTemplate(ItsmModel):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="ticket_form_templates")
    username = models.CharField(max_length=64)
    name = models.CharField(max_length=100)
    form_data = models.JSONField(default=dict)

    class Meta:
        db_table = "itsm_ticket_form_template"
        indexes = [models.Index(fields=["domain", "username", "workflow"], name="itsm_formtpl_owner_idx")]
