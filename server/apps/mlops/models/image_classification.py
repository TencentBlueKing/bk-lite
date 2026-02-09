from django.db import models
from django_minio_backend import MinioBackend, iso_date_prefix

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.mlops.constants import DatasetReleaseStatus, TrainJobStatus
from apps.mlops.models.mixins import TrainDataFileCleanupMixin, TrainJobConfigSyncMixin


class ImageClassificationDataset(MaintainerInfo, TimeInfo):
    """图片分类数据集"""

    name = models.CharField(max_length=100, verbose_name="数据集名称")
    description = models.TextField(blank=True, null=True, verbose_name="数据集描述")

    class Meta:
        verbose_name = "图片分类数据集"
        verbose_name_plural = "图片分类数据集"

    def __str__(self):
        return self.name


class ImageClassificationTrainData(TrainDataFileCleanupMixin, MaintainerInfo, TimeInfo):
    """图片分类训练数据模型"""

    name = models.CharField(max_length=100, verbose_name="训练数据名称")

    dataset = models.ForeignKey(
        ImageClassificationDataset,
        on_delete=models.CASCADE,
        related_name="train_data",
        verbose_name="数据集",
    )

    train_data = models.FileField(
        verbose_name="训练数据",
        storage=MinioBackend(bucket_name="munchkin-public"),
        upload_to=iso_date_prefix,
        help_text="存储在MinIO中的图片压缩包文件（ZIP格式）",
        blank=True,
        null=True,
    )

    metadata = models.JSONField(
        verbose_name="元数据",
        default=dict,
        blank=True,
        help_text="图片标签映射和统计信息，格式：{classes: [...], labels: {filename: class}, statistics: {...}}",
    )

    is_train_data = models.BooleanField(
        default=False, verbose_name="是否为训练数据", help_text="是否为训练数据"
    )

    is_val_data = models.BooleanField(
        default=False, verbose_name="是否为验证数据", help_text="是否为验证数据"
    )

    is_test_data = models.BooleanField(
        default=False, verbose_name="是否为测试数据", help_text="是否为测试数据"
    )

    class Meta:
        verbose_name = "图片分类训练数据"
        verbose_name_plural = "图片分类训练数据"

    def __str__(self):
        return f"{self.name} - {self.dataset.name}"


class ImageClassificationDatasetRelease(MaintainerInfo, TimeInfo):
    """图片分类数据集发布版本"""

    name = models.CharField(
        max_length=100, verbose_name="发布版本名称", help_text="数据集发布版本的名称"
    )

    description = models.TextField(
        blank=True, null=True, verbose_name="版本描述", help_text="发布版本的详细描述"
    )

    dataset = models.ForeignKey(
        ImageClassificationDataset,
        on_delete=models.CASCADE,
        related_name="releases",
        verbose_name="数据集",
        help_text="关联的数据集",
    )

    version = models.CharField(
        max_length=50, verbose_name="版本号", help_text="数据集版本号，如 v1.0.0"
    )

    dataset_file = models.FileField(
        verbose_name="数据集压缩包",
        storage=MinioBackend(bucket_name="munchkin-public"),
        upload_to=iso_date_prefix,
        help_text="存储在MinIO中的完整数据集ZIP压缩包，ImageFolder格式：train/val/test目录，每个类别一个文件夹",
    )

    file_size = models.BigIntegerField(
        verbose_name="文件大小", help_text="压缩包文件大小（字节）", default=0
    )

    status = models.CharField(
        max_length=20,
        choices=DatasetReleaseStatus.CHOICES,
        default=DatasetReleaseStatus.PENDING,
        verbose_name="发布状态",
        help_text="数据集发布状态",
    )

    metadata = models.JSONField(
        verbose_name="数据集元信息",
        default=dict,
        blank=True,
        help_text="""
        完整数据集的统计信息，格式：
        {
            "total_images": 1000,
            "classes": ["cat", "dog", "bird"],
            "format": "ImageFolder",
            "splits": {
                "train": {"total": 800, "classes": {"cat": 320, "dog": 280, "bird": 200}},
                "val": {"total": 100, "classes": {"cat": 40, "dog": 35, "bird": 25}},
                "test": {"total": 100, "classes": {"cat": 40, "dog": 35, "bird": 25}}
            }
        }
        """,
    )

    class Meta:
        verbose_name = "图片分类数据集发布版本"
        verbose_name_plural = "图片分类数据集发布版本"
        ordering = ["-created_at"]
        unique_together = [["dataset", "version"]]

    def __str__(self):
        return f"{self.dataset.name} - {self.version}"


class ImageClassificationTrainJob(TrainJobConfigSyncMixin, MaintainerInfo, TimeInfo):
    """图片分类训练任务"""

    _model_prefix = "ImageClassification"

    name = models.CharField(max_length=100, verbose_name="任务名称")
    description = models.TextField(blank=True, null=True, verbose_name="任务描述")

    status = models.CharField(
        max_length=20,
        choices=TrainJobStatus.CHOICES,
        default=TrainJobStatus.PENDING,
        verbose_name="任务状态",
        help_text="训练任务的当前状态",
    )

    algorithm = models.CharField(
        max_length=50,
        verbose_name="算法模型",
        help_text="使用的YOLO分类算法模型",
        default="YOLOClassification",
    )

    dataset_version = models.ForeignKey(
        "ImageClassificationDatasetRelease",
        on_delete=models.CASCADE,
        related_name="train_jobs",
        verbose_name="数据集版本",
        help_text="关联的图片分类数据集版本",
        null=True,
        blank=True,
    )

    # 数据库存储 - 工作数据，供API快速查询
    hyperopt_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="训练配置",
        help_text="""
        前端传递的超参数配置，格式：
        {
            "hyperparams": {
                "epochs": 100,
                "batch_size": 16,
                "img_size": 640,
                "learning_rate": 0.01,
                "optimizer": "Adam",
                "patience": 10,
                "workers": 8,
                "device": "0",
                "augmentation": {
                    "hsv_h": 0.015,
                    "hsv_s": 0.7,
                    "hsv_v": 0.4,
                    "degrees": 0.0,
                    "translate": 0.1,
                    "scale": 0.5,
                    "shear": 0.0,
                    "perspective": 0.0,
                    "flipud": 0.0,
                    "fliplr": 0.5,
                    "mosaic": 1.0,
                    "mixup": 0.0
                }
            }
        }
        """,
    )

    # MinIO 存储 - 归档备份
    config_url = models.FileField(
        storage=MinioBackend(bucket_name="munchkin-public"),
        upload_to=iso_date_prefix,
        blank=True,
        null=True,
        verbose_name="配置文件备份",
        help_text="MinIO 中的完整训练配置 JSON 文件备份",
    )

    max_evals = models.IntegerField(
        default=50,
        verbose_name="最大评估次数",
        help_text="超参数优化的最大评估次数（YOLO训练通常不需要过多搜索）",
    )

    class Meta:
        verbose_name = "图片分类训练任务"
        verbose_name_plural = "图片分类训练任务"

    def __str__(self):
        return self.name


class ImageClassificationServing(MaintainerInfo, TimeInfo):
    """图片分类服务"""

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
    train_job = models.ForeignKey(
        ImageClassificationTrainJob,
        on_delete=models.CASCADE,
        related_name="servings",
        verbose_name="训练任务",
        help_text="关联的图片分类训练任务",
    )
    model_version = models.CharField(
        max_length=50,
        default="latest",
        verbose_name="模型版本",
        help_text="模型版本号，latest 或具体版本（1, 2, 3...）",
    )
    port = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="服务端口",
        help_text="用户指定端口，为空则由 docker 自动分配。实际端口以 container_info.port 为准",
    )
    status = models.CharField(
        max_length=20,
        choices=[("active", "Active"), ("inactive", "Inactive")],
        default="inactive",
        verbose_name="服务状态",
        help_text="用户意图：是否希望服务运行",
    )

    container_info = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="容器状态信息",
        help_text="webhookd 返回的容器实时状态，格式：{status, id, state, port, detail, ...}",
    )

    class Meta:
        verbose_name = "图片分类服务"
        verbose_name_plural = "图片分类服务"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
