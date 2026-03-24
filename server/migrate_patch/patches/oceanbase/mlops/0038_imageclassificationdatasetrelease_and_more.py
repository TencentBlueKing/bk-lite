# OceanBase 数据库兼容补丁
# 原始文件: apps/mlops/migrations/0038_imageclassificationdatasetrelease_and_more.py
# 问题:
#   AlterField 变更 imageclassificationtraindata.train_data 从 JSONField → FileField
#   OceanBase 不支持 "Alter non string type not supported" (错误码 1235)
# 方案:
#   使用 FakeAlterField 跳过，因为 0027 补丁已直接定义为 FileField

import django.db.models.deletion
import django_minio_backend.models
from django.db import migrations, models


class FakeAlterField(migrations.AlterField):
    """跳过 OceanBase 不支持的 AlterField 操作"""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("mlops", "0037_classificationdatasetrelease_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImageClassificationDatasetRelease",
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
                        help_text="存储在MinIO中的完整数据集ZIP压缩包，ImageFolder格式：train/val/test目录，每个类别一个文件夹",
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
                    models.JSONField(
                        blank=True,
                        default=dict,
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
                        verbose_name="数据集元信息",
                    ),
                ),
            ],
            options={
                "verbose_name": "图片分类数据集发布版本",
                "verbose_name_plural": "图片分类数据集发布版本",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ImageClassificationServing",
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
            ],
            options={
                "verbose_name": "图片分类服务",
                "verbose_name_plural": "图片分类服务",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ImageClassificationTrainJob",
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
                        choices=[("YOLOClassification", "YOLOClassification")],
                        default="YOLOClassification",
                        help_text="使用的YOLO分类算法模型",
                        max_length=50,
                        verbose_name="算法模型",
                    ),
                ),
                (
                    "hyperopt_config",
                    models.JSONField(
                        blank=True,
                        default=dict,
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
                        verbose_name="训练配置",
                    ),
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
                (
                    "max_evals",
                    models.IntegerField(default=50, help_text="超参数优化的最大评估次数（YOLO训练通常不需要过多搜索）", verbose_name="最大评估次数"),
                ),
                (
                    "dataset_version",
                    models.ForeignKey(
                        blank=True,
                        help_text="关联的图片分类数据集版本",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="train_jobs",
                        to="mlops.imageclassificationdatasetrelease",
                        verbose_name="数据集版本",
                    ),
                ),
            ],
            options={
                "verbose_name": "图片分类训练任务",
                "verbose_name_plural": "图片分类训练任务",
            },
        ),
        migrations.CreateModel(
            name="ObjectDetectionDataset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("name", models.CharField(max_length=100, verbose_name="数据集名称")),
                ("description", models.TextField(blank=True, null=True, verbose_name="数据集描述")),
            ],
            options={
                "verbose_name": "目标检测数据集",
                "verbose_name_plural": "目标检测数据集",
            },
        ),
        migrations.CreateModel(
            name="ObjectDetectionTrainData",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("name", models.CharField(max_length=100, verbose_name="训练数据名称")),
                ("train_data", models.JSONField(help_text="存储训练数据", verbose_name="训练数据")),
                ("meta_data", models.JSONField(blank=True, help_text="训练数据元信息", null=True, verbose_name="元数据")),
                ("is_train_data", models.BooleanField(default=False, help_text="是否为训练数据", verbose_name="是否为训练数据")),
                ("is_val_data", models.BooleanField(default=False, help_text="是否为验证数据", verbose_name="是否为验证数据")),
                ("is_test_data", models.BooleanField(default=False, help_text="是否为测试数据", verbose_name="是否为测试数据")),
                (
                    "dataset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="train_data",
                        to="mlops.objectdetectiondataset",
                        verbose_name="数据集",
                    ),
                ),
            ],
            options={
                "verbose_name": "Maintainer Fields",
                "abstract": False,
            },
        ),
        migrations.AlterModelOptions(
            name="imageclassificationdataset",
            options={"verbose_name": "图片分类数据集", "verbose_name_plural": "图片分类数据集"},
        ),
        migrations.AlterModelOptions(
            name="imageclassificationtraindata",
            options={"verbose_name": "图片分类训练数据", "verbose_name_plural": "图片分类训练数据"},
        ),
        migrations.RemoveField(
            model_name="imageclassificationtraindata",
            name="meta_data",
        ),
        migrations.AddField(
            model_name="imageclassificationtraindata",
            name="metadata",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="图片标签映射和统计信息，格式：{classes: [...], labels: {filename: class}, statistics: {...}}",
                verbose_name="元数据",
            ),
        ),
        # --- OceanBase 补丁: 使用 FakeAlterField 跳过 ---
        # 原因: 0027 补丁已直接定义 train_data 为 FileField
        FakeAlterField(
            model_name="imageclassificationtraindata",
            name="train_data",
            field=models.FileField(
                blank=True,
                help_text="存储在MinIO中的图片压缩包文件（ZIP格式）",
                null=True,
                storage=django_minio_backend.models.MinioBackend(bucket_name="munchkin-public"),
                upload_to=django_minio_backend.models.iso_date_prefix,
                verbose_name="训练数据",
            ),
        ),
        migrations.DeleteModel(
            name="ClassificationTrainHistory",
        ),
        migrations.AddField(
            model_name="imageclassificationserving",
            name="train_job",
            field=models.ForeignKey(
                help_text="关联的图片分类训练任务",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="servings",
                to="mlops.imageclassificationtrainjob",
                verbose_name="训练任务",
            ),
        ),
        migrations.AddField(
            model_name="imageclassificationdatasetrelease",
            name="dataset",
            field=models.ForeignKey(
                help_text="关联的数据集",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="releases",
                to="mlops.imageclassificationdataset",
                verbose_name="数据集",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="imageclassificationdatasetrelease",
            unique_together={("dataset", "version")},
        ),
    ]
