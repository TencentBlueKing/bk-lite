# 达梦数据库兼容补丁
# 原始文件: apps/alerts/migrations/0009_remove_correlationrules_aggregation_rules_and_more.py
# 问题:
#   1. 0005 补丁对 alerts_sess_event_i_5ab59a_idx 使用 FakeAddIndex（FK 已有索引，
#      再 AddIndex 会 -3236）。0009 按该名字 DROP INDEX 得到 -2139，迁移未登记。
#   2. 达梦 DDL 自动提交。失败前的删除已经生效，重跑原始 0009 会因对象已不在而失败。
# 方案:
#   - FakeRemoveIndex 跳过从未创建的命名索引
#   - 其余删除先查库，对象已不在就跳过，任意中断点都能重跑做完

from django.db import migrations

from migrate_patch.patches.compat_ops import (
    AlterUniqueTogetherIfExists,
    DeleteModelIfExists,
    FakeRemoveIndex,
    RemoveFieldIfExists,
    RemoveIndexIfExists,
)


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
        RemoveFieldIfExists(
            model_name="sessioneventrelation",
            name="event",
        ),
        RemoveFieldIfExists(
            model_name="sessioneventrelation",
            name="session",
        ),
        RemoveFieldIfExists(
            model_name="sessionwindow",
            name="events",
        ),
        DeleteModelIfExists(
            name="AggregationRules",
        ),
        DeleteModelIfExists(
            name="CorrelationRules",
        ),
        DeleteModelIfExists(
            name="SessionEventRelation",
        ),
        DeleteModelIfExists(
            name="SessionWindow",
        ),
    ]
