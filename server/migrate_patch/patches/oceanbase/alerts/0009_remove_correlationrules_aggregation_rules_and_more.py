# OceanBase 数据库兼容补丁
# 原始文件: apps/alerts/migrations/0009_remove_correlationrules_aggregation_rules_and_more.py
# 问题: 0005 对 alerts_sess_event_i_5ab59a_idx 使用 FakeAddIndex，0009 按名删除会失败。

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
