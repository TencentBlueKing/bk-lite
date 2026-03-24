# 达梦数据库兼容补丁
# 原始文件: apps/alerts/migrations/0010_remove_alert_alert_created_btree_and_more.py
# 问题: 此迁移移除 PostgreSQL 专属索引并添加标准索引
#       对于达梦数据库:
#       - RemoveIndex: 这些索引在 0001 patch 中用 FakeAddIndex 跳过，索引名不存在，跳过删除
#       - AddIndex (JSONField): 达梦 CLOB 不支持索引，跳过创建

from django.db import migrations, models


class FakeRemoveIndex(migrations.RemoveIndex):
    """跳过不存在的索引删除操作"""

    def database_forwards(self, *args, **kwargs):
        pass

    def database_backwards(self, *args, **kwargs):
        pass


class FakeAddIndex(migrations.AddIndex):
    """跳过 JSONField 上的索引创建，达梦 CLOB 不支持索引"""

    def database_forwards(self, *args, **kwargs):
        pass

    def database_backwards(self, *args, **kwargs):
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0009_remove_correlationrules_aggregation_rules_and_more"),
    ]

    operations = [
        # --- RemoveIndex: 全部跳过，索引在 0001 patch 中未创建 ---
        FakeRemoveIndex(
            model_name="alert",
            name="alert_created_btree",
        ),
        FakeRemoveIndex(
            model_name="alert",
            name="alert_operator_gin",
        ),
        FakeRemoveIndex(
            model_name="event",
            name="event_labels_gin",
        ),
        FakeRemoveIndex(
            model_name="incident",
            name="incident_created_btree",
        ),
        FakeRemoveIndex(
            model_name="incident",
            name="incident_operator_gin",
        ),
        # --- AddIndex: JSONField 索引全部跳过，达梦 CLOB 不支持 ---
        FakeAddIndex(
            model_name="alert",
            index=models.Index(fields=["operator"], name="alert_operator_gin"),
        ),
        FakeAddIndex(
            model_name="event",
            index=models.Index(fields=["labels"], name="event_labels_gin"),
        ),
        FakeAddIndex(
            model_name="incident",
            index=models.Index(fields=["operator"], name="incident_operator_gin"),
        ),
    ]
