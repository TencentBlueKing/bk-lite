"""文件分发临时存储模型"""

from django.db import models


class DistributionFile(models.Model):
    """
    文件分发存储表

    用于存储待分发的文件信息，支持重新执行场景。
    所有文件都有过期时间（expire_at），由定时任务在到期后自动清理，
    不存在永久保存的文件。
    """

    original_name = models.CharField(max_length=255, verbose_name="原始文件名")
    file_key = models.CharField(max_length=512, verbose_name="存储路径")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="上传时间")
    expire_at = models.DateTimeField(db_index=True, verbose_name="过期时间")
    team = models.IntegerField(null=True, blank=True, verbose_name="团队ID")

    class Meta:
        verbose_name = "分发文件"
        verbose_name_plural = verbose_name
        db_table = "job_distribution_file"
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name
