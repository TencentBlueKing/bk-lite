from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class SubscriptionRule(TimeInfo, MaintainerInfo):
    name = models.CharField(max_length=128, verbose_name="规则名称", unique=True)
    organization = models.BigIntegerField(db_index=True, verbose_name="所属组织ID")
    model_id = models.CharField(
        max_length=100, db_index=True, verbose_name="目标模型ID"
    )
    filter_type = models.CharField(
        max_length=20,
        choices=[("condition", "过滤条件"), ("instances", "实例选择")],
        default="instances",
        verbose_name="筛选类型",
    )
    instance_filter = models.JSONField(default=dict, verbose_name="实例筛选数据")
    trigger_types = models.JSONField(default=list, verbose_name="触发类型列表")
    trigger_config = models.JSONField(default=dict, verbose_name="触发条件配置")
    recipients = models.JSONField(default=dict, verbose_name="接收对象")
    channel_ids = models.JSONField(default=list, verbose_name="通知渠道ID列表")
    is_enabled = models.BooleanField(
        default=True, db_index=True, verbose_name="启用状态"
    )
    last_triggered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="最近触发时间",
    )
    last_check_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="上次检查时间",
    )
    snapshot_data = models.JSONField(default=dict, verbose_name="实例快照数据")

    class Meta:
        db_table = "cmdb_subscription_rule"
        verbose_name = "订阅规则"
        verbose_name_plural = "订阅规则"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization"], name="idx_sub_rule_org"),
            models.Index(fields=["model_id"], name="idx_sub_rule_model"),
            models.Index(fields=["is_enabled"], name="idx_sub_rule_enabled"),
        ]

    def __str__(self):
        return f"SubscriptionRule({self.id}:{self.name})"
