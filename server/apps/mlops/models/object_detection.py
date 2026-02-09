from django.db import models
from django_minio_backend import MinioBackend, iso_date_prefix

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.mlops.constants import DatasetReleaseStatus, TrainJobStatus
from apps.mlops.models.mixins import TrainDataFileCleanupMixin, TrainJobConfigSyncMixin


class ObjectDetectionDataset(MaintainerInfo, TimeInfo):
    """目标检测数据集"""

    name = models.CharField(max_length=100, verbose_name="数据集名称")
    description = models.TextField(blank=True, null=True, verbose_name="数据集描述")

    class Meta:
        verbose_name = "目标检测数据集"
        verbose_name_plural = "目标检测数据集"

    def __str__(self):
        return self.name


class ObjectDetectionTrainData(TrainDataFileCleanupMixin, MaintainerInfo, TimeInfo):
    """目标检测训练数据（重构为 ZIP 上传）"""

    name = models.CharField(max_length=100, verbose_name="训练数据名称")

    dataset = models.ForeignKey(
        ObjectDetectionDataset,
        on_delete=models.CASCADE,
        related_name="train_data",
        verbose_name="数据集",
    )

    train_data = models.FileField(
        verbose_name="训练数据",
        storage=MinioBackend(bucket_name="munchkin-public"),
        upload_to=iso_date_prefix,
        help_text="存储在 MinIO 中的 YOLO 格式 ZIP 压缩包（images/ + labels/ + classes.txt）",
        blank=True,
        null=True,
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

    metadata = models.JSONField(
        verbose_name="元数据",
        default=dict,
        blank=True,
        help_text="""YOLO 数据集元信息，格式：
        {
            "format": "YOLO",
            "classes": ["person", "car", "dog"],
            "num_classes": 3,
            "num_images": 100,
            "labels": {
                "img001.jpg": [
                    {
                        "class_id": 0,
                        "class_name": "person",
                        "x_center": 0.512345,
                        "y_center": 0.623456,
                        "width": 0.234567,
                        "height": 0.345678
                    }
                ],
                "img002.jpg": []
            },
            "statistics": {
                "total_annotations": 250,
                "images_with_annotations": 95,
                "images_without_annotations": 5,
                "class_distribution": {"person": 120, "car": 80, "dog": 50}
            }
        }
        注意：
        - labels 字段是必需的，包含每张图片的详细标注信息
        - 坐标值（x_center, y_center, width, height）必须是归一化的（0-1范围）
        - class_id 从 0 开始，与 classes 数组索引对应
        - class_name 是冗余字段但建议包含，方便阅读和调试
        """,
    )

    class Meta:
        verbose_name = "目标检测训练数据"
        verbose_name_plural = "目标检测训练数据"

    def __str__(self):
        return f"{self.name} - {self.dataset.name}"


class ObjectDetectionDatasetRelease(MaintainerInfo, TimeInfo):
    """目标检测数据集发布版本"""

    name = models.CharField(
        max_length=100, verbose_name="发布版本名称", help_text="数据集发布版本的名称"
    )

    description = models.TextField(
        blank=True, null=True, verbose_name="版本描述", help_text="发布版本的详细描述"
    )

    dataset = models.ForeignKey(
        ObjectDetectionDataset,
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
        help_text="存储在 MinIO 中的完整 YOLO 数据集 ZIP 压缩包，包含 train/val/test 目录和 data.yaml",
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
            "classes": ["person", "car", "dog"],
            "num_classes": 3,
            "format": "YOLO",
            "splits": {
                "train": {"total": 800, "classes": {"person": 400, "car": 250, "dog": 150}},
                "val": {"total": 100, "classes": {"person": 50, "car": 30, "dog": 20}},
                "test": {"total": 100, "classes": {"person": 50, "car": 30, "dog": 20}}
            }
        }
        """,
    )

    class Meta:
        verbose_name = "目标检测数据集发布版本"
        verbose_name_plural = "目标检测数据集发布版本"
        ordering = ["-created_at"]
        unique_together = [["dataset", "version"]]

    def __str__(self):
        return f"{self.dataset.name} - {self.version}"


class ObjectDetectionTrainJob(TrainJobConfigSyncMixin, MaintainerInfo, TimeInfo):
    """目标检测训练任务"""

    _model_prefix = "ObjectDetection"

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
        help_text="使用的 YOLOv11 目标检测算法模型",
        default="YOLODetection",
    )

    dataset_version = models.ForeignKey(
        "ObjectDetectionDatasetRelease",
        on_delete=models.CASCADE,
        related_name="train_jobs",
        verbose_name="数据集版本",
        help_text="关联的目标检测数据集版本",
        null=True,
        blank=True,
    )

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
                "conf_threshold": 0.25,
                "iou_threshold": 0.45,
                "patience": 10,
                "workers": 8,
                "device": "0",
                "augmentation": {...}
            }
        }
        """,
    )

    config_url = models.FileField(
        storage=MinioBackend(bucket_name="munchkin-public"),
        upload_to=iso_date_prefix,
        blank=True,
        null=True,
        verbose_name="配置文件备份",
        help_text="MinIO 中的完整训练配置 JSON 文件备份",
    )

    max_evals = models.IntegerField(
        default=50, verbose_name="最大评估次数", help_text="超参数优化的最大评估次数"
    )

    class Meta:
        verbose_name = "目标检测训练任务"
        verbose_name_plural = "目标检测训练任务"

    def __str__(self):
        return self.name


class ObjectDetectionServing(MaintainerInfo, TimeInfo):
    """目标检测服务"""

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
        ObjectDetectionTrainJob,
        on_delete=models.CASCADE,
        related_name="servings",
        verbose_name="训练任务",
        help_text="关联的目标检测训练任务",
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
        verbose_name = "目标检测服务"
        verbose_name_plural = "目标检测服务"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
