# OceanBase 数据库兼容补丁
# 原始文件: apps/mlops/migrations/0039_objectdetectiondatasetrelease_and_more.py
# 问题:
#   AlterField 将 objectdetectiontraindata.train_data 从 JSONField 改为 FileField
#   OceanBase 不支持 "Alter non string type not supported" (错误码 1235)
# 方案:
#   - 使用 FakeAlterField 跳过不支持的类型变更
#   - 注意: 新数据库部署需要在初始迁移中直接使用最终字段类型

import django.db.models.deletion
import django_minio_backend.models
from django.db import migrations, models


class FakeAlterField(migrations.AlterField):
    """跳过不支持的字段类型变更，OceanBase 不支持 ALTER JSON/非字符串类型字段"""

    def database_forwards(self, *args, **kwargs):
        pass

    def database_backwards(self, *args, **kwargs):
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("mlops", "0038_imageclassificationdatasetrelease_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ObjectDetectionDatasetRelease",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("name", models.CharField(help_text="数据集发布版本的名称", max_length=100, verbose_name="发布版本名称")),
                ("description", models.TextField(blank=True, help_text="发布版本的详细描述", null=True, verbose_name="版本描述")),
                ("version", models.CharField(help_text="数据集版本号，如 v1.0.0", max_length=50, verbose_name="版本号")),
                (
                    "dataset_file",
                    models.FileField(
                        help_text="存储在 MinIO 中的完整 YOLO 数据集 ZIP 压缩包，包含 train/val/test 目录和 data.yaml",
                        storage=django_minio_backend.models.MinioBackend(bucket_name="munchkin-public"),
                        upload_to=django_minio_backend.models.iso_date_prefix,
                        verbose_name="数据集压缩包",
                    ),
                ),
                ("file_size", models.BigIntegerField(default=0, help_text="压缩包文件大小（字节）", verbose_name="文件大小")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "待发布"), ("published", "已发布"), ("failed", "发布失败"), ("archived", "归档")],
                        default="pending",
                        help_text="数据集发布状态",
                        max_length=20,
                        verbose_name="发布状态",
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict, help_text="完整数据集的统计信息", verbose_name="数据集元信息"),
                ),
                (
                    "dataset",
                    models.ForeignKey(
                        help_text="关联的数据集",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="releases",
                        to="mlops.objectdetectiondataset",
                        verbose_name="数据集",
                    ),
                ),
            ],
            options={
                "verbose_name": "目标检测数据集发布版本",
                "verbose_name_plural": "目标检测数据集发布版本",
                "ordering": ["-created_at"],
                "unique_together": {("dataset", "version")},
            },
        ),
        migrations.AlterModelOptions(
            name="objectdetectiontraindata",
            options={"verbose_name": "目标检测训练数据", "verbose_name_plural": "目标检测训练数据"},
        ),
        migrations.RemoveField(
            model_name="objectdetectiontraindata",
            name="meta_data",
        ),
        migrations.AddField(
            model_name="objectdetectiontraindata",
            name="metadata",
            field=models.JSONField(blank=True, default=dict, help_text="YOLO 数据集元信息", verbose_name="元数据"),
        ),
        # --- OceanBase 补丁: 跳过 AlterField (FileField) ---
        FakeAlterField(
            model_name="objectdetectiontraindata",
            name="train_data",
            field=models.FileField(
                blank=True,
                help_text="存储在 MinIO 中的 YOLO 格式 ZIP 压缩包（images/ + labels/ + classes.txt）",
                null=True,
                storage=django_minio_backend.models.MinioBackend(bucket_name="munchkin-public"),
                upload_to=django_minio_backend.models.iso_date_prefix,
                verbose_name="训练数据",
            ),
        ),
        migrations.CreateModel(
            name="ObjectDetectionTrainJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("name", models.CharField(max_length=100, verbose_name="任务名称")),
                ("description", models.TextField(blank=True, null=True, verbose_name="任务描述")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "待训练"), ("running", "训练中"), ("completed", "已完成"), ("failed", "训练失败")],
                        default="pending",
                        help_text="训练任务的当前状态",
                        max_length=20,
                        verbose_name="任务状态",
                    ),
                ),
                (
                    "algorithm",
                    models.CharField(
                        choices=[("YOLODetection", "YOLODetection")],
                        default="YOLODetection",
                        help_text="使用的 YOLOv11 目标检测算法模型",
                        max_length=50,
                        verbose_name="算法模型",
                    ),
                ),
                (
                    "hyperopt_config",
                    models.JSONField(blank=True, default=dict, help_text="前端传递的超参数配置", verbose_name="训练配置"),
                ),
                (
                    "config_url",
                    models.FileField(
                        blank=True,
                        help_text="MinIO 中的完整训练配置 JSON 文件备份",
                        null=True,
                        storage=django_minio_backend.models.MinioBackend(bucket_name="munchkin-public"),
                        upload_to=django_minio_backend.models.iso_date_prefix,
                        verbose_name="配置文件备份",
                    ),
                ),
                ("max_evals", models.IntegerField(default=50, help_text="超参数优化的最大评估次数", verbose_name="最大评估次数")),
                (
                    "dataset_version",
                    models.ForeignKey(
                        blank=True,
                        help_text="关联的目标检测数据集版本",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="train_jobs",
                        to="mlops.objectdetectiondatasetrelease",
                        verbose_name="数据集版本",
                    ),
                ),
            ],
            options={
                "verbose_name": "目标检测训练任务",
                "verbose_name_plural": "目标检测训练任务",
            },
        ),
        migrations.CreateModel(
            name="ObjectDetectionServing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("name", models.CharField(help_text="服务的名称", max_length=100, verbose_name="服务名称")),
                ("description", models.TextField(blank=True, help_text="服务的详细描述", null=True, verbose_name="服务描述")),
                (
                    "model_version",
                    models.CharField(default="latest", help_text="模型版本号，latest 或具体版本（1, 2, 3...）", max_length=50, verbose_name="模型版本"),
                ),
                (
                    "port",
                    models.IntegerField(
                        blank=True,
                        help_text="用户指定端口，为空则由 docker 自动分配。实际端口以 container_info.port 为准",
                        null=True,
                        verbose_name="服务端口",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("inactive", "Inactive")],
                        default="inactive",
                        help_text="用户意图：是否希望服务运行",
                        max_length=20,
                        verbose_name="服务状态",
                    ),
                ),
                (
                    "container_info",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="webhookd 返回的容器实时状态，格式：{status, id, state, port, detail, ...}",
                        verbose_name="容器状态信息",
                    ),
                ),
                (
                    "train_job",
                    models.ForeignKey(
                        help_text="关联的目标检测训练任务",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="servings",
                        to="mlops.objectdetectiontrainjob",
                        verbose_name="训练任务",
                    ),
                ),
            ],
            options={
                "verbose_name": "目标检测服务",
                "verbose_name_plural": "目标检测服务",
                "ordering": ["-created_at"],
            },
        ),
    ]
