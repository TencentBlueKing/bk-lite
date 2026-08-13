from django.db import models


class CmdbUuidMigrationState(models.Model):
    """维护窗清洗命令断点；不参与日常业务路径。"""

    stage = models.CharField(max_length=100, unique=True)
    cursor = models.CharField(max_length=128, blank=True, default="")
    completed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "CMDB UUID 迁移断点"
        verbose_name_plural = verbose_name
