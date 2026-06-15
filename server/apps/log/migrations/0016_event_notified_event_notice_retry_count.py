from django.db import migrations, models


def mark_existing_events_settled(apps, schema_editor):
    """存量事件不追溯补偿：统一标记为已通知，避免补偿任务上线后对历史事件发起重发风暴。

    新机制只对本迁移之后产生的事件生效（notified 默认 False，由通知流程置位）。
    """
    Event = apps.get_model("log", "Event")
    Event.objects.update(notified=True)


def reverse_noop(apps, schema_editor):
    # 字段会被一并删除，无需逆向数据处理
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0015_alter_alertsnapshot_snapshots"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="notified",
            field=models.BooleanField(db_index=True, default=False, verbose_name="通知是否已成功"),
        ),
        migrations.AddField(
            model_name="event",
            name="notice_retry_count",
            field=models.IntegerField(default=0, verbose_name="通知重试次数"),
        ),
        migrations.RunPython(mark_existing_events_settled, reverse_noop),
    ]
