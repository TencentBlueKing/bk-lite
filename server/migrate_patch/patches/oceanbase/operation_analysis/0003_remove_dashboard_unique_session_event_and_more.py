# OceanBase 数据库兼容补丁
# 原始文件: apps/operation_analysis/migrations/0003_remove_dashboard_unique_session_event_and_more.py
# 问题:
#   RemoveConstraint 尝试删除不存在的约束 unique_session_event
#   错误: (1091, "Can't DROP 'unique_session_event'; check that column/key exists")
#   这是由于数据库中断导致的状态不一致（约束本来就不存在）
# 方案:
#   - 使用 FakeRemoveConstraint 跳过删除不存在的约束

from django.db import migrations, models


class FakeRemoveConstraint(migrations.RemoveConstraint):
    """跳过删除不存在的约束操作"""

    def database_forwards(self, *args, **kwargs):
        pass

    def database_backwards(self, *args, **kwargs):
        pass


class FakeAddConstraint(migrations.AddConstraint):
    """跳过添加可能已存在的约束操作"""

    def database_forwards(self, *args, **kwargs):
        pass

    def database_backwards(self, *args, **kwargs):
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0002_alter_datasourceapimodel_options_dashboard_and_more"),
    ]

    operations = [
        # --- OceanBase 补丁: 跳过删除不存在的约束 ---
        FakeRemoveConstraint(
            model_name="dashboard",
            name="unique_session_event",
        ),
        migrations.AlterField(
            model_name="datasourceapimodel",
            name="name",
            field=models.CharField(max_length=255, verbose_name="数据源名称"),
        ),
        migrations.AlterField(
            model_name="datasourceapimodel",
            name="rest_api",
            field=models.CharField(max_length=255, verbose_name="REST API URL"),
        ),
        # --- OceanBase 补丁: 跳过可能已存在的约束 ---
        FakeAddConstraint(
            model_name="dashboard",
            constraint=models.UniqueConstraint(fields=("name", "type"), name="unique_name_type"),
        ),
        FakeAddConstraint(
            model_name="datasourceapimodel",
            constraint=models.UniqueConstraint(fields=("name", "rest_api"), name="unique_name_rest_api"),
        ),
    ]
