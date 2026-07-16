import uuid

from django.db import models
from django.db.models import JSONField

from apps.core.models.time_info import TimeInfo


class NodeMgmtSyncConfig(TimeInfo):
    singleton_key = models.CharField(max_length=32, default="default", unique=True, editable=False)
    version = models.PositiveBigIntegerField(default=1)
    name = models.CharField(max_length=128, default="节点管理同步", verbose_name="任务名称")
    is_builtin = models.BooleanField(default=True, verbose_name="是否为系统内置任务")
    auto_sync_enabled = models.BooleanField(default=True, verbose_name="是否自动同步")
    auto_collect_enabled = models.BooleanField(default=True, verbose_name="是否自动采集")
    sync_interval_minutes = models.PositiveIntegerField(default=5, verbose_name="同步周期(分钟)")
    collect_interval_minutes = models.PositiveIntegerField(default=30, verbose_name="采集周期(分钟)")
    last_sync_at = models.DateTimeField(null=True, blank=True, verbose_name="最近同步时间")
    last_collect_at = models.DateTimeField(null=True, blank=True, verbose_name="最近采集时间")
    schedule_status = models.CharField(max_length=32, default="reconciling")
    node_config_status = models.CharField(max_length=32, default="reconciling")
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    reconcile_error_code = models.CharField(max_length=64, blank=True, default="")
    reconcile_error_message = models.CharField(max_length=255, blank=True, default="")

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
    STATUS_WAITING_SYNC = "waiting_sync"
    STATUS_SUBMITTED = "submitted"
    STATUS_SUCCESS = "success"
    STATUS_PARTIAL_SUCCESS = "partial_success"
    STATUS_BLOCKED = "blocked"
    STATUS_FAILED = "failed"
    STATUS_TIMEOUT = "timeout"
    STATUS_CHOICES = (
        (STATUS_WAITING_SYNC, "等待同步"),
        (STATUS_RUNNING, "运行中"),
        (STATUS_SUBMITTED, "已提交"),
        (STATUS_SUCCESS, "成功"),
        (STATUS_PARTIAL_SUCCESS, "部分成功"),
        (STATUS_BLOCKED, "已阻塞"),
        (STATUS_FAILED, "失败"),
        (STATUS_TIMEOUT, "超时"),
    )

    task = models.ForeignKey(NodeMgmtSyncConfig, on_delete=models.CASCADE, related_name="runs", verbose_name="所属任务")
    run_type = models.CharField(max_length=32, choices=RUN_TYPE_CHOICES, verbose_name="执行类型")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_RUNNING, verbose_name="执行状态")
    generation = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    active_scope = models.CharField(max_length=32, null=True, blank=True, unique=True)
    reason_code = models.CharField(max_length=64, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    submitted_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")
    summary_json = JSONField(default=dict, help_text="执行摘要")
    detail_json = JSONField(default=dict, help_text="执行明细")
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")

    class Meta:
        verbose_name = "节点管理同步记录"
        verbose_name_plural = verbose_name
        ordering = ["-created_at"]


class NodeMgmtSyncRegionState(TimeInfo):
    config = models.ForeignKey(NodeMgmtSyncConfig, related_name="region_states", on_delete=models.CASCADE)
    run = models.ForeignKey(NodeMgmtSyncRun, null=True, blank=True, related_name="region_states", on_delete=models.CASCADE,)
    scope_key = models.CharField(max_length=160, unique=True)
    cloud_region_id = models.CharField(max_length=64)
    config_version = models.PositiveBigIntegerField(default=1)
    status = models.CharField(max_length=32, default="pending")
    reason_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.CharField(max_length=255, blank=True, default="")
    collect_task = models.ForeignKey("CollectModels", null=True, blank=True, on_delete=models.SET_NULL)
    child_execution_id = models.CharField(max_length=64, blank=True, default="")
    node_config_status = models.CharField(max_length=32, default="pending")
    instance_count = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "节点管理同步区域状态"
        verbose_name_plural = verbose_name
