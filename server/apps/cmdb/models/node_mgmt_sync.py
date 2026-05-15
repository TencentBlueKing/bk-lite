from django.db import models
from django.db.models import JSONField

from apps.core.models.time_info import TimeInfo


class NodeMgmtSyncConfig(TimeInfo):
    name = models.CharField(max_length=128, default="节点管理同步", verbose_name="任务名称")
    is_builtin = models.BooleanField(default=True, verbose_name="是否为系统内置任务")
    auto_sync_enabled = models.BooleanField(default=True, verbose_name="是否自动同步")
    auto_collect_enabled = models.BooleanField(default=True, verbose_name="是否自动采集")
    sync_interval_minutes = models.PositiveIntegerField(default=5, verbose_name="同步周期(分钟)")
    collect_interval_minutes = models.PositiveIntegerField(default=30, verbose_name="采集周期(分钟)")
    last_sync_at = models.DateTimeField(null=True, blank=True, verbose_name="最近同步时间")
    last_collect_at = models.DateTimeField(null=True, blank=True, verbose_name="最近采集时间")

    class Meta:
        verbose_name = "节点管理同步配置"
        verbose_name_plural = verbose_name


class NodeMgmtSyncRun(TimeInfo):
    RUN_TYPE_SYNC = "sync"
    RUN_TYPE_COLLECT = "collect"
    RUN_TYPE_CHOICES = (
        (RUN_TYPE_SYNC, "同步"),
        (RUN_TYPE_COLLECT, "采集"),
    )

    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_PARTIAL_SUCCESS = "partial_success"
    STATUS_CHOICES = (
        (STATUS_RUNNING, "运行中"),
        (STATUS_SUCCESS, "成功"),
        (STATUS_FAILED, "失败"),
        (STATUS_PARTIAL_SUCCESS, "部分成功"),
    )

    task = models.ForeignKey(NodeMgmtSyncConfig, on_delete=models.CASCADE, related_name="runs", verbose_name="所属任务")
    run_type = models.CharField(max_length=32, choices=RUN_TYPE_CHOICES, verbose_name="执行类型")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_RUNNING, verbose_name="执行状态")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")
    summary_json = JSONField(default=dict, help_text="执行摘要")
    detail_json = JSONField(default=dict, help_text="执行明细")
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")

    class Meta:
        verbose_name = "节点管理同步记录"
        verbose_name_plural = verbose_name
        ordering = ["-created_at"]
