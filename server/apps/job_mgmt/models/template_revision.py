"""作业模板版本快照。

脚本和 Playbook 的当前行仍是执行入口。这里只追加每次变更后的内容，
供版本列表、对比和恢复使用。Playbook 的语义版本号仍留在 Playbook.version。
"""

import uuid

from django.db import models
from django.utils import timezone
from django_minio_backend import MinioBackend

from apps.job_mgmt.constants import ScriptType
from apps.job_mgmt.models.playbook import PLAYBOOK_BUCKET, Playbook
from apps.job_mgmt.models.script import Script


def playbook_revision_upload_path(instance, filename):
    """历史压缩包使用独立路径，避免和当前包或同一天的其他快照互相覆盖。"""
    return f"playbook-revisions/{instance.playbook_id}/{uuid.uuid4().hex}/{filename}"


class ScriptRevision(models.Model):
    """脚本库的一次内容快照。"""

    script = models.ForeignKey(Script, on_delete=models.CASCADE, related_name="revisions", verbose_name="脚本")
    label = models.CharField(max_length=32, verbose_name="版本号")
    name = models.CharField(max_length=128, verbose_name="脚本名称")
    description = models.TextField(blank=True, default="", verbose_name="描述")
    script_type = models.CharField(max_length=32, choices=ScriptType.CHOICES, verbose_name="脚本类型")
    content = models.TextField(verbose_name="脚本内容")
    params = models.JSONField(default=list, verbose_name="参数定义")
    timeout = models.IntegerField(default=60, verbose_name="超时时间")
    content_hash = models.CharField(max_length=64, verbose_name="内容摘要")
    created_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="版本时间")
    created_by = models.CharField(max_length=32, blank=True, default="", verbose_name="操作人")

    class Meta:
        verbose_name = "脚本版本"
        verbose_name_plural = verbose_name
        db_table = "job_script_revision"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["script", "label"], name="uniq_job_script_revision_label"),
        ]

    def __str__(self):
        return f"{self.script_id}:{self.label}"


class PlaybookRevision(models.Model):
    """Playbook 库的一次内容快照，包含压缩包副本。"""

    playbook = models.ForeignKey(Playbook, on_delete=models.CASCADE, related_name="revisions", verbose_name="Playbook")
    label = models.CharField(max_length=32, verbose_name="版本号")
    name = models.CharField(max_length=128, verbose_name="Playbook名称")
    description = models.TextField(blank=True, default="", verbose_name="描述")
    version = models.CharField(max_length=32, default="v1.0.0", verbose_name="语义版本号")
    readme = models.TextField(blank=True, default="", verbose_name="README内容")
    file_list = models.JSONField(default=list, verbose_name="文件列表")
    params = models.JSONField(default=list, verbose_name="参数定义")
    file_sha256 = models.CharField(max_length=64, blank=True, default="", verbose_name="压缩包摘要")
    content_hash = models.CharField(max_length=64, verbose_name="内容摘要")
    file = models.FileField(
        verbose_name="Playbook文件",
        storage=MinioBackend(bucket_name=PLAYBOOK_BUCKET),
        upload_to=playbook_revision_upload_path,
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="版本时间")
    created_by = models.CharField(max_length=32, blank=True, default="", verbose_name="操作人")

    class Meta:
        verbose_name = "Playbook版本"
        verbose_name_plural = verbose_name
        db_table = "job_playbook_revision"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["playbook", "label"], name="uniq_job_playbook_revision_label"),
        ]

    def __str__(self):
        return f"{self.playbook_id}:{self.label}"

    def delete(self, *args, **kwargs):
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)
