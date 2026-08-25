from django.db import models

from apps.core.models.time_info import TimeInfo


class DatasetReleaseExecution(TimeInfo):
    """数据集发布长任务的内部执行归属，不暴露到业务 API。"""

    release_type = models.CharField(max_length=100)
    release_id = models.PositiveBigIntegerField()
    owner_token = models.CharField(max_length=64, blank=True, default="")
    lease_expires_at = models.DateTimeField()
    attempt = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "mlops_dataset_release_execution"
        constraints = [
            models.UniqueConstraint(
                fields=["release_type", "release_id"],
                name="uniq_mlops_release_execution",
            )
        ]
        indexes = [
            models.Index(
                fields=["release_type", "lease_expires_at"],
                name="mlops_release_lease_idx",
            )
        ]


class DatasetReleaseObjectCleanup(TimeInfo):
    """上传成功到 DB 提交之间的持久外部对象补偿意图。"""

    release_type = models.CharField(max_length=100)
    release_id = models.PositiveBigIntegerField()
    owner_token = models.CharField(max_length=64)
    object_path = models.CharField(max_length=1024)
    cleanup_token = models.CharField(max_length=64, blank=True, default="")
    cleanup_lease_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "mlops_dataset_release_object_cleanup"
        constraints = [
            models.UniqueConstraint(
                fields=["release_type", "release_id", "owner_token"],
                name="uniq_mlops_release_cleanup",
            )
        ]
        indexes = [
            models.Index(
                fields=["release_type", "release_id"],
                name="mlops_release_cleanup_idx",
            )
        ]


class DatasetReleaseObjectCleanupCursor(TimeInfo):
    """对象补偿 sweep 的持久 keyset 断点。"""

    scope = models.CharField(max_length=32, unique=True, default="global")
    last_intent_id = models.PositiveBigIntegerField(default=0)

    class Meta:
        db_table = "mlops_dataset_release_cleanup_cursor"
