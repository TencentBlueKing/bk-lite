from django.db import models
from django.db.models import JSONField

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class ActionRule(MaintainerInfo, TimeInfo):
    """告警处理规则（声明式动作触发）。"""

    name = models.CharField(max_length=100, verbose_name="规则名称")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    team = JSONField(default=list, verbose_name="团队")
    match_rules = JSONField(default=list, verbose_name="匹配条件(OR-of-AND)")
    trigger_events = JSONField(default=list, verbose_name="触发事件")
    scope = models.CharField(max_length=16, default="alert", verbose_name="作用层级")
    action_type = models.CharField(max_length=32, default="job", verbose_name="动作类型")
    action_config = JSONField(default=dict, verbose_name="动作配置")

    class Meta:
        db_table = "alerts_action_rule"
        verbose_name = "告警处理规则"
        verbose_name_plural = "告警处理规则"

    def __str__(self):
        return self.name


class ActionExecution(TimeInfo):
    """每次触发一条执行记录。"""

    rule = models.ForeignKey(
        ActionRule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="executions",
        verbose_name="规则",
    )
    alert = models.ForeignKey(
        "alerts.Alert",
        on_delete=models.CASCADE,
        related_name="action_executions",
        verbose_name="告警",
    )
    trigger_event = models.CharField(max_length=32, verbose_name="触发事件")
    trigger_type = models.CharField(max_length=16, default="auto", verbose_name="触发方式")
    idempotency_key = models.CharField(
        max_length=255, null=True, blank=True, unique=True, verbose_name="幂等键"
    )
    status = models.CharField(max_length=16, default="pending", db_index=True, verbose_name="状态")
    action_type = models.CharField(max_length=32, default="job", verbose_name="动作类型")
    job_task_id = models.IntegerField(null=True, blank=True, verbose_name="作业执行ID")
    job_detail_url = models.CharField(max_length=512, null=True, blank=True, verbose_name="作业详情链接")
    result = JSONField(default=dict, blank=True, verbose_name="结果")
    operator = models.CharField(max_length=64, null=True, blank=True, verbose_name="手动触发人")

    class Meta:
        db_table = "alerts_action_execution"
        verbose_name = "动作执行记录"
        verbose_name_plural = "动作执行记录"
        ordering = ["-created_at"]
