from django.db import models

from apps.core.models.time_info import TimeInfo


class UploadedProviderPack(TimeInfo):
    key = models.CharField(max_length=64, unique=True, db_index=True)
    pack_revision = models.PositiveIntegerField()
    archive = models.BinaryField()
    author_version = models.CharField(max_length=64, blank=True, default="")
    name = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        db_table = "system_mgmt_uploadedproviderpack"
        ordering = ("key",)
