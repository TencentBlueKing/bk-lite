from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from django.db import models

from apps.mlops.models.classification_train_job import ClassificationTrainJob


class ClassificationServing(MaintainerInfo, TimeInfo):
    """分类任务服务"""
    
    name = models.CharField(
        max_length=100,
        verbose_name="服务名称",
        help_text="服务的名称",
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="服务描述",
        help_text="服务的详细描述",
    )
    classification_train_job = models.ForeignKey(
        ClassificationTrainJob,
        on_delete=models.CASCADE,
        related_name="servings",
        verbose_name="模型ID",
        help_text="关联的分类训练任务模型ID",
    )
    model_version = models.CharField(
        max_length=50,
        default="latest",
        verbose_name="模型版本",
        help_text="模型版本",
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("active", "Active"),
            ("inactive", "Inactive")
        ],
        default="active",
        verbose_name="服务状态",
        help_text="服务的当前状态",
    )
    
    class Meta:
        verbose_name = "分类任务服务"
        verbose_name_plural = "分类任务服务"
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"{self.name}"