# 达梦数据库兼容补丁
# 原始文件: apps/alerts/migrations/0009_remove_correlationrules_aggregation_rules_and_more.py
# 问题:
#   1. 0005 补丁对 alerts_sess_event_i_5ab59a_idx 使用 FakeAddIndex（FK 已有索引，
#      再 AddIndex 会 -3236）。0009 按该名字 DROP INDEX 得到 -2139，迁移未登记。
#   2. 达梦 DDL 自动提交。关联表已删、0009 未登记时重跑会先 -2106 缺表。
# 方案:
#   - FakeRemoveIndex 跳过从未创建的命名索引
#   - 已执行过的删除改为不存在则跳过，保证半成功 schema 可恢复

from django.db import migrations

from migrate_patch.patches.compat_ops import AlterUniqueTogetherIfExists, FakeRemoveIndex, RemoveFieldIfExists, RemoveIndexIfExists


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0008_alarmstrategy_and_more"),
    ]

    operations = [
        RemoveFieldIfExists(
            model_name="correlationrules",
            name="aggregation_rules",
        ),
        AlterUniqueTogetherIfExists(
            name="sessioneventrelation",
            unique_together=None,
        ),
        FakeRemoveIndex(model_name="sessioneventrelation", name="alerts_sess_event_i_5ab59a_idx"),
        RemoveIndexIfExists(model_name="sessioneventrelation", name="alerts_sess_session_76b0b9_idx"),
        migrations.RemoveField(
            model_name="sessioneventrelation",
            name="event",
        ),
        migrations.RemoveField(
            model_name="sessioneventrelation",
            name="session",
        ),
        migrations.RemoveField(
            model_name="sessionwindow",
            name="events",
        ),
        migrations.DeleteModel(
            name="AggregationRules",
        ),
        migrations.DeleteModel(
            name="CorrelationRules",
        ),
        migrations.DeleteModel(
            name="SessionEventRelation",
        ),
        migrations.DeleteModel(
            name="SessionWindow",
        ),
    ]
