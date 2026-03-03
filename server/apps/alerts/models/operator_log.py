# -- coding: utf-8 --
# @File: operator_log.py
# @Time: 2026/2/5 16:16
# @Author: windyzhao
from django.db import models

from apps.alerts.constants.constants import LogAction, LogTargetType


class OperatorLog(models.Model):
    """操作日志模型"""

    operator = models.CharField(max_length=64, default="admin", help_text="操作人")
    action = models.CharField(
        max_length=32, choices=LogAction.CHOICES, help_text="操作类型"
    )
    target_type = models.CharField(
        max_length=32,
        choices=LogTargetType.CHOICES,
        default=LogTargetType.SYSTEM,
        help_text="目标类型",
    )
    operator_object = models.CharField(
        max_length=100, null=True, blank=True, help_text="操作对象"
    )
    target_id = models.CharField(
        max_length=100, null=True, blank=True, help_text="目标ID"
    )
    overview = models.TextField(null=True, blank=True, help_text="操作概述")
    created_at = models.DateTimeField(
        help_text="Created Time", auto_now_add=True, db_index=True
    )

    class Meta:
        db_table = "alerts_operator_log"
        verbose_name = "操作日志"
        verbose_name_plural = "操作日志"

    def __str__(self):
        return (
            f"{self.operator} - {self.action} on {self.target_type}({self.target_id})"
        )
