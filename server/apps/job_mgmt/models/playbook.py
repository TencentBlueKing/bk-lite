"""Playbook模型"""

from django.db import models
from django_minio_backend import MinioBackend

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo

# Playbook 文件存储 bucket
PLAYBOOK_BUCKET = "job-mgmt-private"


def playbook_upload_path(instance, filename):
    """Playbook 文件上传路径"""
    from datetime import datetime

    now = datetime.now()
    return f"playbooks/{now.year}/{now.month:02d}/{now.day:02d}/{filename}"


class Playbook(TimeInfo, MaintainerInfo):
    """
    Playbook库

    上传包含 playbook.yml 和 README.md 的 ZIP 压缩包
    """

    # 基本信息（从ZIP文件名自动提取，不含扩展名）
    name = models.CharField(max_length=128, verbose_name="Playbook名称")

    # 版本号（选填，默认 v1.0.0）
    version = models.CharField(max_length=32, default="v1.0.0", verbose_name="版本号")

    # 描述
    description = models.TextField(blank=True, default="", verbose_name="描述")

    # 解析后的内容（上传时从ZIP提取）
    readme = models.TextField(blank=True, default="", verbose_name="README内容")
    file_list = models.JSONField(default=list, verbose_name="文件列表")
    params = models.JSONField(default=list, verbose_name="参数定义")

    # ZIP 文件（存储到 MinIO）
    file = models.FileField(
        verbose_name="Playbook文件",
        storage=MinioBackend(bucket_name=PLAYBOOK_BUCKET),
        upload_to=playbook_upload_path,
        blank=True,
        null=True,
    )

    # 组织归属
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    class Meta:
        verbose_name = "Playbook"
        verbose_name_plural = verbose_name
        db_table = "job_playbook"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.version})"

    def delete(self, *args, **kwargs):
        """删除时同时删除 MinIO 中的文件"""
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)

    @property
    def file_name(self) -> str:
        """文件名（兼容属性）"""
        if self.file:
            return self.file.name.split("/")[-1]
        return ""

    @property
    def file_size(self) -> int:
        """文件大小（字节）"""
        if self.file:
            try:
                return self.file.size
            except Exception:
                return 0
        return 0

    @property
    def file_key(self) -> str:
        """文件 Key（兼容属性）"""
        if self.file:
            return self.file.name
        return ""

    @property
    def bucket_name(self) -> str:
        """存储桶名称（兼容属性）"""
        return PLAYBOOK_BUCKET
