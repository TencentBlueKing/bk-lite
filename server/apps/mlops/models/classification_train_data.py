from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.mlops.models.classification_dataset import ClassificationDataset


class ClassificationTrainData(MaintainerInfo, TimeInfo):
    """分类任务训练数据模型"""

    name = models.CharField(max_length=100, verbose_name="训练数据名称")
    
    dataset = models.ForeignKey(
        ClassificationDataset,
        on_delete=models.CASCADE,
        related_name="train_data",
        verbose_name="数据集",
    )
    
    train_data = models.JSONField(
        verbose_name="训练数据",
        help_text="存储训练数据",
    )
    
    metadata = models.JSONField(
        verbose_name="元数据",
        blank=True,
        null=True,
        help_text="训练数据元信息",
    )

    is_train_data = models.BooleanField(
        default=False,
        verbose_name="是否为训练数据",
        help_text="是否为训练数据"
    )

    is_val_data = models.BooleanField(
        default=False,
        verbose_name="是否为验证数据",
        help_text="是否为验证数据"
    )

    is_test_data = models.BooleanField(
        default=False,
        verbose_name="是否为测试数据",
        help_text="是否为测试数据"
    )
    
    class Meta:
        verbose_name = "分类任务训练数据"
        verbose_name_plural = "分类任务训练数据"

    def __str__(self):
        return f"{self.name} - {self.dataset.name}"