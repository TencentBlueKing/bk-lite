# OceanBase 数据库兼容补丁
# 原始文件: apps/mlops/migrations/0032_alter_timeseriespredicttraindata_metadata_and_more.py
# 问题:
#   AlterField 将 TimeSeriesPredictTrainData 字段类型变更:
#     metadata: JSONField → S3JSONField
#     train_data: JSONField → FileField
#   OceanBase 不支持 "Alter non string type not supported" (错误码 1235)
# 方案:
#   使用 FakeAlterField 跳过，因为 0021 补丁中已直接定义为最终类型

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
        ("mlops", "0031_objectdetectiondataset_objectdetectiontraindata"),
    ]

    operations = [
        # --- OceanBase 补丁: 跳过 AlterField ---
        # 原始: migrations.AlterField(model_name='timeseriespredicttraindata', name='metadata', field=S3JSONField(...))
        # 0021 补丁中 metadata 字段已直接定义为 S3JSONField，无需变更
        FakeAlterField(
            model_name="timeseriespredicttraindata",
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
        # --- OceanBase 补丁: 跳过 AlterField ---
        # 原始: migrations.AlterField(model_name='timeseriespredicttraindata', name='train_data', field=FileField(...))
        # 0021 补丁中 train_data 字段已直接定义为 FileField，无需变更
        FakeAlterField(
            model_name="timeseriespredicttraindata",
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
    ]
