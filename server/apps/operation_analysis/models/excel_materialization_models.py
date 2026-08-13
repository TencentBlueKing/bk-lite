# -- coding: utf-8 --
from django.db import models, transaction
from django.db.models import JSONField
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django_minio_backend.models import MinioBackend, iso_date_prefix

from apps.core.logger import operation_analysis_logger as logger
from apps.core.models.time_info import TimeInfo
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

EXCEL_PRIVATE_BUCKET = "operation-analysis-private"


class ExcelMaterializationSlot(TimeInfo):
    """Excel 成功/候选物化槽位（每数据源最多各保留一个）。"""

    ROLE_CANDIDATE = "candidate"
    ROLE_SUCCESS = "success"
    ROLE_CHOICES = (
        (ROLE_CANDIDATE, "候选"),
        (ROLE_SUCCESS, "当前成功"),
    )

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_PENDING, "待处理"),
        (STATUS_PROCESSING, "处理中"),
        (STATUS_SUCCEEDED, "成功"),
        (STATUS_FAILED, "失败"),
    )

    datasource = models.ForeignKey(
        DataSourceAPIModel,
        on_delete=models.CASCADE,
        related_name="excel_slots",
        verbose_name="数据源",
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_CANDIDATE, verbose_name="槽位角色")
    generation = models.PositiveIntegerField(default=0, verbose_name="候选代数")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)

    source_filename = models.CharField(max_length=255, blank=True, default="", verbose_name="原文件名")
    source_file = models.FileField(
        storage=MinioBackend(bucket_name=EXCEL_PRIVATE_BUCKET),
        upload_to=iso_date_prefix,
        blank=True,
        null=True,
        verbose_name="原 Excel 文件",
    )
    result_file = models.FileField(
        storage=MinioBackend(bucket_name=EXCEL_PRIVATE_BUCKET),
        upload_to=iso_date_prefix,
        blank=True,
        null=True,
        verbose_name="物化结果文件",
    )

    transform_enabled = models.BooleanField(default=False, verbose_name="是否启用转换")
    script_snapshot = models.TextField(blank=True, default="", verbose_name="脚本快照")
    script_hash = models.CharField(max_length=64, blank=True, default="", verbose_name="脚本哈希")

    row_count = models.PositiveIntegerField(default=0, verbose_name="行数")
    field_schema = JSONField(default=list, blank=True, verbose_name="字段定义")
    error_code = models.CharField(max_length=64, blank=True, default="", verbose_name="错误码")
    error_summary = models.CharField(max_length=512, blank=True, default="", verbose_name="错误摘要")

    class Meta:
        db_table = "operation_analysis_excel_materialization_slot"
        verbose_name = "Excel 物化槽位"
        indexes = [
            models.Index(fields=["datasource", "role", "-id"], name="oa_excel_slot_role_idx"),
            models.Index(fields=["datasource", "generation"], name="oa_excel_slot_gen_idx"),
        ]

    def __str__(self):
        return f"ExcelSlot(ds={self.datasource_id}, role={self.role}, status={self.status}, gen={self.generation})"


@receiver(post_delete, sender=ExcelMaterializationSlot)
def delete_excel_slot_files_after_commit(sender, instance, **kwargs):
    """DB 删除提交后再删对象，避免事务回滚留下断裂引用。"""
    slot_id = instance.pk
    files = [
        (field.storage, field.name)
        for field in (instance.source_file, instance.result_file)
        if field and field.name
    ]

    def _delete_files():
        for storage, name in files:
            try:
                storage.delete(name)
            except Exception:  # noqa: BLE001 - DB delete has committed; cleanup is compensating work.
                logger.error(
                    "[ExcelMaterializationSlot] file cleanup failed slot_id=%s name=%s",
                    slot_id,
                    name,
                    exc_info=True,
                )

    transaction.on_commit(_delete_files)
