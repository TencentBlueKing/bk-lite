# OceanBase 数据库兼容补丁
# 原始文件: apps/mlops/migrations/0027_imageclassificationtraindata.py
# 问题:
#   ImageClassificationTrainData 的字段在后续迁移中变更类型:
#     0027: train_data = JSONField
#     0038: train_data → FileField
#   OceanBase 不支持 "Alter non string type not supported" (错误码 1235)
# 方案:
#   在初始创建时直接定义为最终类型，0038 使用 FakeAlterField 跳过

import django.db.models.deletion
import django_minio_backend.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mlops", "0026_imageclassificationdataset"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImageClassificationTrainData",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("name", models.CharField(max_length=100, verbose_name="训练数据名称")),
                # --- OceanBase 补丁: 直接定义为最终类型 FileField ---
                # 原始: models.JSONField(help_text='存储训练数据', verbose_name='训练数据')
                # 0038 变更: → FileField
                (
                    "train_data",
                    models.FileField(
                        blank=True,
                        help_text="存储在MinIO中的图片压缩包文件（ZIP格式）",
                        null=True,
                        storage=django_minio_backend.models.MinioBackend(bucket_name="munchkin-public"),
                        upload_to=django_minio_backend.models.iso_date_prefix,
                        verbose_name="训练数据",
                    ),
                ),
                ("meta_data", models.JSONField(blank=True, help_text="训练数据元信息", null=True, verbose_name="元数据")),
                ("is_train_data", models.BooleanField(default=False, help_text="是否为训练数据", verbose_name="是否为训练数据")),
                ("is_val_data", models.BooleanField(default=False, help_text="是否为验证数据", verbose_name="是否为验证数据")),
                ("is_test_data", models.BooleanField(default=False, help_text="是否为测试数据", verbose_name="是否为测试数据")),
                (
                    "dataset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="train_data",
                        to="mlops.imageclassificationdataset",
                        verbose_name="数据集",
                    ),
                ),
            ],
            options={
                "verbose_name": "Maintainer Fields",
                "abstract": False,
            },
        ),
    ]
