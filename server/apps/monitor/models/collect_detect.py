from django.db import models

from apps.core.models.time_info import TimeInfo


class CollectDetectTask(TimeInfo):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
    )

    PHASE_CHOICES = (
        ("validate", "Validate"),
        ("render_config", "Render Config"),
        ("prepare_runtime", "Prepare Runtime"),
        ("execute_once", "Execute Once"),
        ("parse_output", "Parse Output"),
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="检测状态")
    phase = models.CharField(max_length=40, choices=PHASE_CHOICES, default="validate", verbose_name="检测阶段")
    monitor_plugin_id = models.IntegerField(verbose_name="监控插件ID")
    monitor_object_id = models.IntegerField(verbose_name="监控对象ID")
    collector = models.CharField(max_length=100, verbose_name="采集器")
    collect_type = models.CharField(max_length=50, verbose_name="采集类型")
    node_id = models.CharField(max_length=100, verbose_name="节点ID")
    instance_key = models.CharField(max_length=100, blank=True, default="", verbose_name="实例行标识")
    request_fingerprint = models.CharField(max_length=64, verbose_name="请求指纹")
    created_by = models.CharField(max_length=150, verbose_name="发起人")
    organization = models.IntegerField(verbose_name="组织ID")
    request_snapshot = models.JSONField(default=dict, verbose_name="脱敏请求快照")
    result = models.JSONField(default=dict, verbose_name="检测结果")
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")

    class Meta:
        verbose_name = "采集检测任务"
        verbose_name_plural = "采集检测任务"
        indexes = [
            models.Index(fields=["created_by", "organization", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["request_fingerprint"]),
        ]
