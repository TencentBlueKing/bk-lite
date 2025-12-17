
from django.db import models
from django_minio_backend import MinioBackend, iso_date_prefix

from apps.core.fields import S3JSONField
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.mlops.models.data_points_features_info import DataPointFeaturesInfo


class TimeSeriesPredictDataset(MaintainerInfo, TimeInfo):
    """时间序列预测数据集"""

    name = models.CharField(max_length=100, verbose_name="数据集名称")
    description = models.TextField(blank=True, null=True, verbose_name="数据集描述")

    class Meta:
        verbose_name = "时间序列预测数据集"
        verbose_name_plural = "时间序列预测数据集"

    def __str__(self):
        return self.name


class TimeSeriesPredictTrainData(MaintainerInfo, TimeInfo):
    """时间序列预测训练数据模型"""

    name = models.CharField(max_length=100, verbose_name="训练数据名称")

    dataset = models.ForeignKey(
        TimeSeriesPredictDataset,
        on_delete=models.CASCADE,
        related_name="train_data",
        verbose_name="数据集",
    )

    train_data = models.FileField(
        verbose_name="训练数据",
        storage=MinioBackend(bucket_name="munchkin-public"),
        upload_to=iso_date_prefix,
        help_text="存储在MinIO中的CSV训练数据文件",
        blank=True,
        null=True,
    )

    metadata = S3JSONField(
        bucket_name="munchkin-public",
        compressed=True,
        verbose_name="元数据",
        blank=True,
        null=True,
        help_text="存储在MinIO中的训练数据元信息文件路径",
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
        verbose_name = "时间序列预测训练数据"
        verbose_name_plural = "时间序列预测训练数据"

    def __str__(self):
        return f"{self.name} - {self.dataset.name}"


class TimeSeriesPredictDatasetRelease(MaintainerInfo, TimeInfo):
    """时间序列预测数据集发布版本"""

    name = models.CharField(
        max_length=100,
        verbose_name="发布版本名称",
        help_text="数据集发布版本的名称"
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="版本描述",
        help_text="发布版本的详细描述"
    )

    dataset = models.ForeignKey(
        TimeSeriesPredictDataset,
        on_delete=models.CASCADE,
        related_name="releases",
        verbose_name="数据集",
        help_text="关联的数据集"
    )

    version = models.CharField(
        max_length=50,
        verbose_name="版本号",
        help_text="数据集版本号，如 v1.0.0"
    )

    dataset_file = models.FileField(
        verbose_name="数据集压缩包",
        storage=MinioBackend(bucket_name="munchkin-public"),
        upload_to=iso_date_prefix,
        help_text="存储在MinIO中的数据集ZIP压缩包"
    )

    file_size = models.BigIntegerField(
        verbose_name="文件大小",
        help_text="压缩包文件大小（字节）",
        default=0
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "待发布"),
            ("published", "已发布"),
            ("failed", "发布失败"),
            ("archived", "归档")
        ],
        default="pending",
        verbose_name="发布状态",
        help_text="数据集发布状态"
    )

    metadata = models.JSONField(
        verbose_name="数据集元信息",
        default=dict,
        blank=True,
        help_text="数据集的统计信息和质量指标，不包含训练配置"
    )

    class Meta:
        verbose_name = "时间序列预测数据集发布版本"
        verbose_name_plural = "时间序列预测数据集发布版本"
        ordering = ["-created_at"]
        unique_together = [["dataset", "version"]]

    def __str__(self):
        return f"{self.dataset.name} - {self.version}"


class TimeSeriesPredictTrainJob(MaintainerInfo, TimeInfo):
    """时间序列预测训练任务"""

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
        help_text="使用的时间序列预测算法模型",
        choices=[
            ('Prophet', 'Prophet'),
        ]
    )

    train_data_id = models.ForeignKey(
        'TimeSeriesPredictTrainData',
        on_delete=models.CASCADE,
        related_name="train_jobs",
        verbose_name="训练数据集",
        help_text="关联的时间序列预测训练数据集"
    )

    val_data_id = models.ForeignKey(
        'TimeSeriesPredictTrainData',
        on_delete=models.CASCADE,
        related_name="val_jobs",
        verbose_name="验证数据集",
        help_text="关联的时间序列预测验证数据集"
    )

    test_data_id = models.ForeignKey(
        'TimeSeriesPredictTrainData',
        on_delete=models.CASCADE,
        related_name="test_jobs",
        verbose_name="测试数据集",
        help_text="关联的时间序列预测测试数据集"
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
        verbose_name = "时间序列预测训练任务"
        verbose_name_plural = "时间序列预测训练任务"


class TimeSeriesPredictTrainHistory(MaintainerInfo, TimeInfo, DataPointFeaturesInfo):
    algorithm = models.CharField(
        max_length=50,
        verbose_name="算法模型",
        help_text="使用的时间序列预测算法模型",
        choices=[
            ('Prophet', 'Prophet'),
        ]
    )

    train_data_id = models.ForeignKey(
        'TimeSeriesPredictTrainData',
        on_delete=models.CASCADE,
        related_name="train_history",
        verbose_name="训练数据集",
        help_text="关联的时间序列预测训练数据集"
    )
    val_data_id = models.ForeignKey(
        'TimeSeriesPredictTrainData',
        on_delete=models.CASCADE,
        related_name="val_history",
        verbose_name="验证数据集",
        help_text="关联的时间序列预测验证数据集"
    )

    test_data_id = models.ForeignKey(
        'TimeSeriesPredictTrainData',
        on_delete=models.CASCADE,
        related_name="test_history",
        verbose_name="测试数据集",
        help_text="关联的时间序列预测测试数据集"
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
        verbose_name = "时间序列预测训练历史"
        verbose_name_plural = "时间序列预测训练历史"


class TimeSeriesPredictServing(MaintainerInfo, TimeInfo):
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
    time_series_predict_train_job = models.ForeignKey(
        TimeSeriesPredictTrainJob,
        on_delete=models.CASCADE,
        related_name="servings",
        verbose_name="模型ID",
        help_text="关联的时间序列预测训练任务模型ID",
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
        verbose_name = "时间序列预测服务"
        verbose_name_plural = "时间序列预测服务"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}"
