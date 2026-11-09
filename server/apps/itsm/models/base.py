from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class ItsmModel(TimeInfo, MaintainerInfo):
    team = models.JSONField(default=list)

    class Meta:
        abstract = True
