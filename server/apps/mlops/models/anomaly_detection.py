
from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.mlops.models.data_points_features_info import DataPointFeaturesInfo


class AnomalyDetectionDataset(MaintainerInfo, TimeInfo):
    """异常检测数据集模型"""

    name = models.CharField(max_length=100, verbose_name="数据集名称")
    description = models.TextField(blank=True, null=True, verbose_name="数据集描述")

    class Meta:
        verbose_name = "异常检测数据集"
        verbose_name_plural = "异常检测数据集"

    def __str__(self):
        return self.name


class AnomalyDetectionTrainData(MaintainerInfo, TimeInfo):
    """异常检测训练数据模型"""

    name = models.CharField(max_length=100, verbose_name="训练数据名称")

    dataset = models.ForeignKey(
        AnomalyDetectionDataset,
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

    anomaly_point_count = models.PositiveIntegerField(
        default=0,
        verbose_name="异常点数量",
        help_text="异常点的数量"
    )

    class Meta:
        verbose_name = "异常检测训练数据"
        verbose_name_plural = "异常检测训练数据"

    def __str__(self):
        return f"{self.name} - {self.dataset.name}"

    def save(self, *args, **kwargs):
        """
        保存时自动计算异常点数量
        从metadata中的anomaly_point数组长度获取异常点数量
        """
        if self.metadata:
            anomaly_point = self.metadata.get('anomaly_point', [])
            self.anomaly_point_count = len(anomaly_point)
        else:
            self.anomaly_point_count = 0

        super().save(*args, **kwargs)


class AnomalyDetectionTrainJob(MaintainerInfo, TimeInfo, DataPointFeaturesInfo):
    """异常检测训练任务"""

    name = models.CharField(max_length=100, verbose_name="任务名称")
    description = models.TextField(blank=True, null=True, verbose_name="任务描述")

    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', '待训练'),
            ('running', '训练中'),
            ('completed', '已完成'),
            ('failed', '训练失败'),
        ],
        default='pending',
        verbose_name="任务状态",
        help_text="训练任务的当前状态"
    )

    algorithm = models.CharField(
        max_length=50,
        verbose_name="算法模型",
        help_text="使用的异常检测算法模型",
        choices=[
            ('RandomForest', '随机森林'),
        ]
    )

    train_data_id = models.ForeignKey(
        'AnomalyDetectionTrainData',
        on_delete=models.CASCADE,
        related_name="train_jobs",
        verbose_name="训练数据集",
        help_text="关联的异常检测训练数据集"
    )

    val_data_id = models.ForeignKey(
        'AnomalyDetectionTrainData',
        on_delete=models.CASCADE,
        related_name="val_jobs",
        verbose_name="验证数据集",
        help_text="关联的异常检测验证数据集"
    )

    test_data_id = models.ForeignKey(
        'AnomalyDetectionTrainData',
        on_delete=models.CASCADE,
        related_name="test_jobs",
        verbose_name="测试数据集",
        help_text="关联的异常检测测试数据集"
    )

    hyperopt_config = models.JSONField(
        verbose_name="超参数优化配置",
        help_text="用于超参数优化的配置参数",
        default=dict,
    )

    max_evals = models.IntegerField(
        default=200,
        verbose_name="最大评估次数",
        help_text="超参数优化的最大评估次数"
    )

    class Meta:
        verbose_name = "异常检测训练任务"
        verbose_name_plural = "异常检测训练任务"


class AnomalyDetectionTrainHistory(MaintainerInfo, TimeInfo, DataPointFeaturesInfo):
    algorithm = models.CharField(
        max_length=50,
        verbose_name="算法模型",
        help_text="使用的异常检测算法模型",
        choices=[
            ('RandomForest', '随机森林'),
        ]
    )

    train_data_id = models.ForeignKey(
        'AnomalyDetectionTrainData',
        on_delete=models.CASCADE,
        related_name="train_history",
        verbose_name="训练数据集",
        help_text="关联的异常检测训练数据集"
    )
    val_data_id = models.ForeignKey(
        'AnomalyDetectionTrainData',
        on_delete=models.CASCADE,
        related_name="val_history",
        verbose_name="验证数据集",
        help_text="关联的异常检测验证数据集"
    )

    test_data_id = models.ForeignKey(
        'AnomalyDetectionTrainData',
        on_delete=models.CASCADE,
        related_name="test_history",
        verbose_name="测试数据集",
        help_text="关联的异常检测测试数据集"
    )

    hyperopt_config = models.JSONField(
        verbose_name="超参数优化配置",
        help_text="用于超参数优化的配置参数",
        default=dict,
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ('running', '训练中'),
            ('completed', '已完成'),
            ('failed', '训练失败'),
        ],
        default='pending',
        verbose_name="任务状态",
        help_text="训练任务的当前状态"
    )

    class Meta:
        verbose_name = "异常检测训练历史"
        verbose_name_plural = "异常检测训练历史"


class AnomalyDetectionServing(MaintainerInfo, TimeInfo):
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
    anomaly_detection_train_job = models.ForeignKey(
        AnomalyDetectionTrainJob,
        on_delete=models.CASCADE,
        related_name="servings",
        verbose_name="模型ID",
        help_text="关联的异常检测训练任务模型ID",
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
    anomaly_threshold = models.FloatField(
        default=0.5,
        verbose_name="异常阈值",
        help_text="用于判断异常的阈值",
    )

    class Meta:
        verbose_name = "异常检测服务"
        verbose_name_plural = "异常检测服务"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}"
