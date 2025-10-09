from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class ClassificationDataset(MaintainerInfo, TimeInfo):
    """分类任务数据集"""
    
    name = models.CharField(max_length=100, verbose_name="数据集名称")
    description = models.TextField(blank=True, null=True, verbose_name="数据集描述")


    class Meta:
        verbose_name = "分类任务数据集"
        verbose_name_plural = "分类任务数据集"

    def __str__(self):
        return self.name