from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class CredentialType(MaintainerInfo, TimeInfo):
    key = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    is_builtin = models.BooleanField(default=False)
    categories = models.JSONField(default=list)
    fields = models.JSONField(default=list)


class Credential(MaintainerInfo, TimeInfo):
    credential_id = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=128)
    type = models.ForeignKey(
        CredentialType,
        to_field="key",
        on_delete=models.PROTECT,
        db_column="type_key",
    )
    group_id = models.PositiveIntegerField(db_index=True)
    disabled = models.BooleanField(default=False)
    fields = models.JSONField(default=dict)
