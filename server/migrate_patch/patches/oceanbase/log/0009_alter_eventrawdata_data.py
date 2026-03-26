# OceanBase 数据库兼容补丁
# 原始文件: apps/log/migrations/0009_alter_eventrawdata_data.py
# 问题:
#   AlterField 将 EventRawData.data 从 JSONField 改为 S3JSONField
#   OceanBase 不支持 "Alter non string type not supported" (错误码 1235)
# 方案:
#   使用 FakeAlterField 跳过此变更，因为 0003 补丁中已直接定义为 S3JSONField

from django.db import migrations

import apps.core.fields.s3_json_field


class FakeAlterField(migrations.AlterField):
    """跳过不支持的字段类型变更，OceanBase 不支持 ALTER JSON 类型字段"""

    def database_forwards(self, *args, **kwargs):
        pass

    def database_backwards(self, *args, **kwargs):
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0008_policy_show_fields"),
    ]

    operations = [
        # --- OceanBase 补丁: 跳过 AlterField ---
        # 原始: migrations.AlterField(model_name='eventrawdata', name='data', field=S3JSONField(...))
        # 0003 补丁中 data 字段已直接定义为 S3JSONField，无需变更
        FakeAlterField(
            model_name="eventrawdata",
            name="data",
            field=apps.core.fields.s3_json_field.S3JSONField(
                bucket_name="log-alert-raw-data",
                compressed=True,
                help_text="自动压缩并存储到 MinIO/S3",
                max_length=500,
                upload_to=apps.core.fields.s3_json_field.s3_json_upload_path,
                verbose_name="原始数据",
            ),
        ),
    ]
