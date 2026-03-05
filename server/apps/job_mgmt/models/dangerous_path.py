"""高危路径模型"""

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.job_mgmt.constants import DangerousLevel


class DangerousPath(TimeInfo, MaintainerInfo):
    """
    高危路径规则

    用于限制文件分发操作的目标路径，防止向系统关键目录分发文件导致的安全风险或系统故障
    支持使用通配符和正则表达式匹配路径模式
    """

    name = models.CharField(max_length=128, verbose_name="规则名称")
    description = models.TextField(blank=True, default="", verbose_name="描述")

    # 匹配模式（支持通配符和正则表达式）
    pattern = models.CharField(max_length=512, verbose_name="路径匹配规则")

    # 处理策略（二次确认/禁止分发）
    level = models.CharField(
        max_length=32,
        choices=DangerousLevel.CHOICES,
        default=DangerousLevel.FORBIDDEN,
        verbose_name="处理策略",
    )

    # 是否启用
    is_enabled = models.BooleanField(default=True, verbose_name="是否启用")

    # 组织归属
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    class Meta:
        verbose_name = "高危路径"
        verbose_name_plural = verbose_name
        db_table = "job_dangerous_path"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}"
