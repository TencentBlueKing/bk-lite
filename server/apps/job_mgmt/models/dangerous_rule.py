"""高危命令模型"""

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.job_mgmt.constants import DangerousLevel


class DangerousRule(TimeInfo, MaintainerInfo):
    """
    高危命令规则

    用于在脚本执行前进行安全检查，检测危险命令
    支持使用正则表达式匹配命令模式
    """

    name = models.CharField(max_length=128, verbose_name="规则名称")
    description = models.TextField(blank=True, default="", verbose_name="描述")

    # 匹配模式（支持正则表达式）
    pattern = models.CharField(max_length=512, verbose_name="命令匹配规则")

    # 处理策略（二次确认/禁止执行）
    level = models.CharField(
        max_length=32,
        choices=DangerousLevel.CHOICES,
        default=DangerousLevel.CONFIRM,
        verbose_name="处理策略",
    )

    # 是否启用
    is_enabled = models.BooleanField(default=True, verbose_name="是否启用")

    # 组织归属
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    class Meta:
        verbose_name = "高危命令"
        verbose_name_plural = verbose_name
        db_table = "job_dangerous_rule"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}"
