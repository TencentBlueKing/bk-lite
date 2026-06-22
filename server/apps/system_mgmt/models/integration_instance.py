from copy import deepcopy

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.mixinx import EncryptMixin
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class IntegrationInstanceStatusChoices(models.TextChoices):
    PENDING_VERIFICATION = "pending_verification", _("Pending Verification")
    READY = "ready", _("Ready")
    VERIFICATION_FAILED = "verification_failed", _("Verification Failed")


class IntegrationInstance(MaintainerInfo, TimeInfo, EncryptMixin):
    name = models.CharField(max_length=100)
    provider_key = models.CharField(max_length=64, db_index=True)
    config = models.JSONField(default=dict)
    status = models.CharField(
        max_length=32,
        choices=IntegrationInstanceStatusChoices.choices,
        default=IntegrationInstanceStatusChoices.PENDING_VERIFICATION,
    )
    capability_status = models.JSONField(default=dict)
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")
    team = models.JSONField(default=list)

    class Meta:
        ordering = ("-id",)

    def get_runtime_config(self):
        config = deepcopy(self.config or {})
        from apps.system_mgmt.providers import get_provider_registry

        manifest = get_provider_registry().get(self.provider_key)
        if manifest is None:
            return config

        for field in manifest.get_secret_fields():
            self.decrypt_field(field.key, config)
        return config

    def get_masked_config(self):
        config = self.get_runtime_config()
        from apps.system_mgmt.providers import get_provider_registry

        manifest = get_provider_registry().get(self.provider_key)
        if manifest is None:
            return config

        for field in manifest.get_secret_fields():
            if config.get(field.key):
                config[field.key] = "******" if field.mask_strategy == "full" else f"******{str(config[field.key])[-4:]}"
        return config
