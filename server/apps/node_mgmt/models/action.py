from django.db import models
from django.db.models import JSONField

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Node, Collector


class CollectorActionTask(TimeInfo, MaintainerInfo):
    ACTION_CHOICES = (
        ("start", "启动"),
        ("restart", "重启"),
        ("stop", "停止"),
    )

    collector = models.ForeignKey(
        Collector, on_delete=models.CASCADE, verbose_name="采集器"
    )
    cloud_region = models.ForeignKey(
        CloudRegion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="云区域",
    )
    action = models.CharField(
        max_length=20, choices=ACTION_CHOICES, verbose_name="动作类型"
    )
    status = models.CharField(
        max_length=100, default="waiting", verbose_name="任务状态"
    )
    total_count = models.IntegerField(default=0, verbose_name="总节点数")
    success_count = models.IntegerField(default=0, verbose_name="成功节点数")
    error_count = models.IntegerField(default=0, verbose_name="失败节点数")

    class Meta:
        verbose_name = "采集器动作任务"
        verbose_name_plural = "采集器动作任务"
        indexes = [
            models.Index(fields=["status"], name="nm_action_task_status_idx"),
        ]


class CollectorActionTaskNode(models.Model):
    task = models.ForeignKey(
        CollectorActionTask, on_delete=models.CASCADE, verbose_name="任务"
    )
    node = models.ForeignKey(Node, on_delete=models.CASCADE, verbose_name="节点")
    status = models.CharField(
        max_length=100, default="waiting", verbose_name="任务状态"
    )
    result = JSONField(default=dict, verbose_name="结果")

    class Meta:
        verbose_name = "采集器动作任务节点"
        verbose_name_plural = "采集器动作任务节点"
        unique_together = ("task", "node")
        indexes = [
            models.Index(fields=["node", "status"], name="nm_action_node_status_idx"),
            models.Index(
                fields=["task", "status"], name="nm_action_tasknode_status_idx"
            ),
        ]
