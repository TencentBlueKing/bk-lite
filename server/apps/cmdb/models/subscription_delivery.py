from django.db import models

from apps.cmdb.models.subscription_rule import SubscriptionRule


class SubscriptionDeliveryStatus(models.TextChoices):
    PENDING = "pending", "待发送"
    SENDING = "sending", "发送中"
    RETRY = "retry", "待重试"
    SENT = "sent", "已发送"
    FAILED = "failed", "发送失败"


class SubscriptionDelivery(models.Model):
    dedupe_key = models.CharField(max_length=64, unique=True, verbose_name="去重键")
    rule = models.ForeignKey(SubscriptionRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="deliveries", verbose_name="订阅规则",)
    rule_id_snapshot = models.BigIntegerField(verbose_name="订阅规则ID快照")
    trigger_type = models.CharField(max_length=32, verbose_name="触发类型")
    events = models.JSONField(default=list, verbose_name="触发事件")
    recipients = models.JSONField(default=dict, verbose_name="接收对象")
    channel_id = models.BigIntegerField(verbose_name="通知渠道ID")
    status = models.CharField(
        max_length=16, choices=SubscriptionDeliveryStatus.choices, default=SubscriptionDeliveryStatus.PENDING, verbose_name="投递状态",
    )
    attempt_count = models.PositiveSmallIntegerField(default=0, verbose_name="尝试次数")
    next_retry_at = models.DateTimeField(null=True, blank=True, verbose_name="下次重试时间")
    last_error = models.TextField(blank=True, default="", verbose_name="最近错误")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="发送时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "cmdb_subscription_delivery"
        verbose_name = "订阅通知投递"
        verbose_name_plural = "订阅通知投递"
        indexes = [
            models.Index(fields=["status", "next_retry_at"], name="idx_sub_del_status_retry",),
            models.Index(fields=["rule_id_snapshot", "created_at"], name="idx_sub_del_rule_created",),
        ]
