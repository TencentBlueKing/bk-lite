# OceanBase 数据库兼容补丁
# 原始文件: apps/log/migrations/0004_alert_notice_alter_eventrawdata_data.py
# 问题:
#   AlterField 将 EventRawData.data 从 JSONField(default=dict) 改为 JSONField(default=list)
#   OceanBase 不支持 "Alter non string type not supported" (错误码 1235)
# 方案:
#   使用 FakeAlterField 跳过此变更，因为 0003 补丁中已直接定义为最终类型 S3JSONField

from django.db import migrations, models


class FakeAlterField(migrations.AlterField):
    """跳过不支持的字段类型变更，OceanBase 不支持 ALTER JSON 类型字段"""

    def database_forwards(self, *args, **kwargs):
        pass

    def database_backwards(self, *args, **kwargs):
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0003_alert_event_policy_eventrawdata_event_policy_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="notice",
            field=models.BooleanField(default=False, verbose_name="是否已通知"),
        ),
        # --- OceanBase 补丁: 跳过 AlterField ---
        # 原始: migrations.AlterField(model_name='eventrawdata', name='data', field=models.JSONField(default=list, ...))
        # 0003 补丁中 data 字段已直接定义为 S3JSONField，无需变更
        FakeAlterField(
            model_name="eventrawdata",
            name="data",
            field=models.JSONField(default=list, verbose_name="原始数据"),
        ),
    ]
