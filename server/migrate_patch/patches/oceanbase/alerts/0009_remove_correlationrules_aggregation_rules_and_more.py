# OceanBase 数据库兼容补丁
# 原始文件: apps/alerts/migrations/0009_remove_correlationrules_aggregation_rules_and_more.py
# 问题: 0005 对 alerts_sess_event_i_5ab59a_idx 使用 FakeAddIndex，0009 按名删除会失败。
# 方案: 每步删除先查库，对象不在（从未创建或上次已删）就跳过。

from django.db import migrations

from migrate_patch.patches.compat_ops import (
    AlterUniqueTogetherIfExists,
    DeleteModelIfExists,
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
        RemoveIndexIfExists(model_name="sessioneventrelation", name="alerts_sess_event_i_5ab59a_idx"),
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
