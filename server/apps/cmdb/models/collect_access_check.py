from django.db import models

from apps.cmdb.models.collect_model import CollectModels


class CollectAccessCheck(models.Model):
    """一个采集任务只保留最近一次连通性测试。"""

    task = models.OneToOneField(
        CollectModels,
        on_delete=models.CASCADE,
        related_name="access_check",
    )
    status = models.CharField(max_length=16)
    total_count = models.PositiveIntegerField(default=0)
    finished_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    operator = models.CharField(max_length=150, default="", blank=True)
    error_code = models.CharField(max_length=64, default="", blank=True)

    class Meta:
        db_table = "cmdb_collect_access_check"


class CollectAccessCheckRow(models.Model):
    """一个目标上的一条凭据。不保存口令。"""

    access_check = models.ForeignKey(
        CollectAccessCheck,
        on_delete=models.CASCADE,
        related_name="rows",
        db_column="check_id",
    )
    position = models.PositiveIntegerField()
    target = models.CharField(max_length=255)
    credential_id = models.CharField(max_length=64, default="", blank=True)
    credential_name = models.CharField(max_length=255, default="", blank=True)
    conclusion = models.CharField(max_length=32)
    detail_code = models.CharField(max_length=64, default="", blank=True)
    attempted = models.BooleanField(default=False)

    class Meta:
        db_table = "cmdb_collect_access_check_row"
        constraints = [
            models.UniqueConstraint(
                fields=("access_check", "target", "credential_id"),
                name="cmdb_collect_access_check_row_uniq",
            )
        ]
