# -- coding: utf-8 --
# @File: models.py
# @Time: 2025/7/14 16:03
# @Author: windyzhao
from django.db import models
from django.db.models import JSONField
from rest_framework.exceptions import ValidationError

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.core.models.group_info import Groups


class Directory(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="目录名称")
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, related_name="sub_directories", null=True, blank=True, verbose_name="父目录"
    )
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    desc = models.TextField(verbose_name="描述", blank=True, null=True)

    class Meta:
        db_table = "operation_analysis_directory"
        verbose_name = "目录"
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'parent'],
                name='unique_name_parent'
            ),
        ]

    def clean(self):
        # 确保目录层级不超过3层
        if self.parent and self.parent.get_level() >= 2:
            raise ValidationError("Directory hierarchy cannot exceed 3 levels.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def has_children(self):
        return self.sub_directories.exists()

    def get_level(self):
        level = 0
        parent = self.parent
        while parent is not None:
            level += 1
            parent = parent.parent
        return level

    def __str__(self):
        return self.name


class Dashboard(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="仪表盘名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(
        Directory, on_delete=models.CASCADE, related_name="dashboards", verbose_name="所属目录", null=True, blank=True
    )
    filters = JSONField(help_text="仪表盘公共过滤条件", verbose_name="过滤条件", blank=True, null=True)
    other = JSONField(help_text="仪表盘其他配置", verbose_name="其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="仪表盘视图集配置", verbose_name="视图集配置", default=list)

    class Meta:
        db_table = "operation_analysis_dashboard"
        verbose_name = "仪表盘"

    def __str__(self):
        return self.name


class Topology(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="拓扑图名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(
        Directory, on_delete=models.CASCADE, related_name="topology", verbose_name="所属目录", null=True, blank=True
    )
    other = JSONField(help_text="拓扑图其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="拓扑图视图集配置", default=list)

    class Meta:
        db_table = "operation_analysis_topology"
        verbose_name = "拓扑图"

    def __str__(self):
        return self.name

    def has_directory(self):
        return self.directory is not None


class Architecture(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="架构图名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(
        Directory, on_delete=models.CASCADE, related_name="architecture", verbose_name="所属目录", null=True, blank=True
    )
    other = JSONField(help_text="架构图其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="架构图视图集配置", default=list)

    class Meta:
        db_table = "operation_analysis_architecture"
        verbose_name = "架构图"

    def __str__(self):
        return self.name

    def has_directory(self):
        return self.directory is not None
