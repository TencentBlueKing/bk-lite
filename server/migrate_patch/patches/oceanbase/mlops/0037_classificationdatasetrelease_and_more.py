# OceanBase 数据库兼容补丁
# 原始文件: apps/mlops/migrations/0037_classificationdatasetrelease_and_more.py
# 问题:
#   1. AlterField 将 classificationtraindata.metadata 从 JSONField 改为 S3JSONField
#      OceanBase 不支持 "Alter non string type not supported" (错误码 1235)
#   2. AlterField 将 classificationtraindata.train_data 从 JSONField 改为 FileField
#      OceanBase 不支持 "Alter non string type not supported" (错误码 1235)
# 方案:
#   - 使用 FakeAlterField 跳过不支持的类型变更
#   - 注意: 新数据库部署需要在初始迁移中直接使用最终字段类型

import django.db.models.deletion
import django_minio_backend.models
from django.db import migrations, models

import apps.core.fields.s3_json_field


class FakeAlterField(migrations.AlterField):
    """跳过不支持的字段类型变更，OceanBase 不支持 ALTER JSON/非字符串类型字段"""

    def database_forwards(self, *args, **kwargs):
        pass

    def database_backwards(self, *args, **kwargs):
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("mlops", "0036_anomalydetectiondatasetrelease_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassificationDatasetRelease",
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
                        help_text="存储在MinIO中的数据集ZIP压缩包",
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
                    models.JSONField(blank=True, default=dict, help_text="数据集的统计信息和质量指标，不包含训练配置", verbose_name="数据集元信息"),
                ),
                (
                    "dataset",
                    models.ForeignKey(
                        help_text="关联的数据集",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="releases",
                        to="mlops.classificationdataset",
                        verbose_name="数据集",
                    ),
                ),
            ],
            options={
                "verbose_name": "分类任务数据集发布版本",
                "verbose_name_plural": "分类任务数据集发布版本",
                "ordering": ["-created_at"],
                "unique_together": {("dataset", "version")},
            },
        ),
        migrations.RemoveField(
            model_name="objectdetectiontraindata",
            name="dataset",
        ),
        migrations.RemoveField(
            model_name="classificationserving",
            name="model_version",
        ),
        migrations.RemoveField(
            model_name="classificationtrainjob",
            name="labels",
        ),
        migrations.RemoveField(
            model_name="classificationtrainjob",
            name="test_data_id",
        ),
        migrations.RemoveField(
            model_name="classificationtrainjob",
            name="train_data_id",
        ),
        migrations.RemoveField(
            model_name="classificationtrainjob",
            name="val_data_id",
        ),
        migrations.AddField(
            model_name="classificationserving",
            name="container_info",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="webhookd 返回的容器实时状态，格式：{status, id, state, port, detail, ...}",
                verbose_name="容器状态信息",
            ),
        ),
        migrations.AddField(
            model_name="classificationserving",
            name="port",
            field=models.IntegerField(
                blank=True,
                help_text="用户指定端口，为空则由 docker 自动分配。实际端口以 container_info.port 为准",
                null=True,
                verbose_name="服务端口",
            ),
        ),
        migrations.AddField(
            model_name="classificationtrainjob",
            name="config_url",
            field=models.FileField(
                blank=True,
                help_text="MinIO 中的 JSON 文件备份",
                null=True,
                storage=django_minio_backend.models.MinioBackend(bucket_name="munchkin-public"),
                upload_to=django_minio_backend.models.iso_date_prefix,
                verbose_name="配置文件备份",
            ),
        ),
        migrations.AlterField(
            model_name="classificationserving",
            name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("inactive", "Inactive")],
                default="inactive",
                help_text="用户意图：是否希望服务运行",
                max_length=20,
                verbose_name="服务状态",
            ),
        ),
        # --- OceanBase 补丁: 跳过 AlterField (S3JSONField) ---
        FakeAlterField(
            model_name="classificationtraindata",
            name="metadata",
            field=apps.core.fields.s3_json_field.S3JSONField(
                blank=True,
                bucket_name="munchkin-public",
                compressed=True,
                help_text="存储在MinIO中的训练数据元信息文件路径",
                max_length=500,
                null=True,
                verbose_name="元数据",
            ),
        ),
        # --- OceanBase 补丁: 跳过 AlterField (FileField) ---
        FakeAlterField(
            model_name="classificationtraindata",
            name="train_data",
            field=models.FileField(
                blank=True,
                help_text="存储在MinIO中的CSV训练数据文件",
                null=True,
                storage=django_minio_backend.models.MinioBackend(bucket_name="munchkin-public"),
                upload_to=django_minio_backend.models.iso_date_prefix,
                verbose_name="训练数据",
            ),
        ),
        migrations.DeleteModel(
            name="ObjectDetectionDataset",
        ),
        migrations.DeleteModel(
            name="ObjectDetectionTrainData",
        ),
        migrations.AddField(
            model_name="classificationtrainjob",
            name="dataset_version",
            field=models.ForeignKey(
                blank=True,
                help_text="关联的分类数据集版本",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="train_jobs",
                to="mlops.classificationdatasetrelease",
                verbose_name="数据集版本",
            ),
        ),
    ]
