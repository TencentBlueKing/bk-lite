"""文件分发临时存储模型"""

from django.db import models


class DistributionFile(models.Model):
    """
    文件分发临时存储表

    用于存储待分发的文件信息，支持重新执行场景
    文件通过定时任务在 7 天后自动清理
    """

    original_name = models.CharField(max_length=255, verbose_name="原始文件名")
    file_key = models.CharField(max_length=512, verbose_name="存储路径")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="上传时间")

    class Meta:
        verbose_name = "分发文件"
        verbose_name_plural = verbose_name
        db_table = "job_distribution_file"
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name
