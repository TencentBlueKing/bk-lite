import gzip

from django.core.files.base import ContentFile
from django.db import models
from django_minio_backend import MinioBackend

from apps.cmdb.models.collect_model import CollectModels

CONFIG_FILE_BUCKET = "cmdb-config-file"


def config_file_upload_to(_instance, filename):
    return filename


class ConfigFileVersionStatus(object):
    SUCCESS = "success"
    FILE_NOT_FOUND = "file_not_found"
    PERMISSION_DENIED = "permission_denied"
    FILE_TOO_LARGE = "file_too_large"
    NOT_TEXT = "not_text"
    ERROR = "error"

    CHOICES = (
        (SUCCESS, "采集成功"),
        (FILE_NOT_FOUND, "文件不存在"),
        (PERMISSION_DENIED, "权限不足"),
        (FILE_TOO_LARGE, "文件超限"),
        (NOT_TEXT, "非文本文件"),
        (ERROR, "采集异常"),
    )


class ConfigFileVersion(models.Model):
    collect_task = models.ForeignKey(
        CollectModels,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="config_file_versions",
        help_text="关联的采集任务（手动创建时为空）",
    )
    instance_id = models.CharField(max_length=128, help_text="主机实例 ID")
    model_id = models.CharField(max_length=64, help_text="模型 ID")
    version = models.CharField(max_length=32, help_text="版本号（采集时间戳）")
    file_path = models.CharField(max_length=512, help_text="采集时的文件绝对路径")
    file_name = models.CharField(max_length=256, help_text="配置文件名称")
    content_hash = models.CharField(max_length=64, blank=True, default="", help_text="文件内容 SHA256 哈希")
    content = models.FileField(
        storage=MinioBackend(bucket_name=CONFIG_FILE_BUCKET),
        upload_to=config_file_upload_to,
        blank=True,
        null=True,
        help_text="MinIO 中的文本配置文件内容",
    )
    file_size = models.PositiveIntegerField(default=0, help_text="文件大小（字节）")
    status = models.CharField(max_length=32, choices=ConfigFileVersionStatus.CHOICES, help_text="采集结果状态")
    error_message = models.TextField(blank=True, default="", help_text="失败原因描述")
    created_at = models.DateTimeField(auto_now_add=True, help_text="记录创建时间")

    class Meta:
        verbose_name = "配置文件版本"
        verbose_name_plural = "配置文件版本"
        ordering = ["-created_at"]
        index_together = [("instance_id", "file_path"), ("collect_task_id",)]
        constraints = [
            models.UniqueConstraint(
                fields=["collect_task", "instance_id", "version"],
                name="uniq_cfg_ver_task_inst_version",
            ),
        ]

    @property
    def content_key(self) -> str:
        return self.content.name if self.content else ""

    def save_content(self, text: str, object_key: str):
        raw_content = (text or "").encode("utf-8")
        self.content.save(object_key, ContentFile(raw_content, name=object_key), save=False)

    def read_content(self) -> str:
        raw_content = self.read_content_bytes()
        if not raw_content:
            return ""
        return raw_content.decode("utf-8", errors="replace")

    def read_content_bytes(self) -> bytes:
        if not self.content:
            return b""
        with self.content.open("rb") as content_file:
            raw_content = content_file.read()
            try:
                return gzip.decompress(raw_content)
            except OSError:
                return raw_content

    def delete(self, using=None, keep_parents=False):
        if self.content:
            self.content.delete(save=False)
        return super().delete(using=using, keep_parents=keep_parents)
