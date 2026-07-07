from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class LoginAuthBindingPlatformFieldChoices(models.TextChoices):
    USERNAME = "username", _("Platform Username")
    PHONE = "phone", _("Platform Mobile")
    EMAIL = "email", _("Platform Email")


class LoginAuthBindingUnmatchedActionChoices(models.TextChoices):
    DENY = "deny", _("Deny Login")
    CREATE = "create", _("Create User")


class LoginAuthBinding(MaintainerInfo, TimeInfo):
    name = models.CharField(max_length=100)
    integration_instance = models.ForeignKey("system_mgmt.IntegrationInstance", on_delete=models.CASCADE, related_name="login_auth_bindings")
    icon = models.CharField(max_length=64, blank=True, default="")
    description = models.TextField(blank=True, default="")
    order = models.PositiveIntegerField(default=0, db_index=True)
    enabled = models.BooleanField(default=True)
    external_field = models.CharField(max_length=100)
    platform_field = models.CharField(max_length=32, choices=LoginAuthBindingPlatformFieldChoices.choices)
    unmatched_user_action = models.CharField(
        max_length=16,
        choices=LoginAuthBindingUnmatchedActionChoices.choices,
        default=LoginAuthBindingUnmatchedActionChoices.DENY,
    )
    default_group_name = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        ordering = ("order", "id")
        unique_together = ("name", "integration_instance")
