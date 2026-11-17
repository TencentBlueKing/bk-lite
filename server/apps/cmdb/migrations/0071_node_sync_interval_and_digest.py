from django.db import migrations, models


def bump_builtin_sync_interval(apps, schema_editor):
    config = apps.get_model("cmdb", "NodeMgmtSyncConfig")
    config.objects.filter(is_builtin=True, sync_interval_minutes=5).update(sync_interval_minutes=15)
    try:
        periodic_task = apps.get_model("django_celery_beat", "PeriodicTask")
        interval_schedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    except LookupError:
        return
    task = periodic_task.objects.filter(name="cmdb_node_mgmt_sync_hosts", interval__every=300, interval__period="seconds").first()
    if task is None:
        return
    interval, _created = interval_schedule.objects.get_or_create(every=900, period="seconds")
    task.interval = interval
    task.save(update_fields=["interval"])


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0069_cmdb_scale_cursor"),
    ]

    operations = [
        migrations.AddField(
            model_name="nodemgmtsyncconfig",
            name="last_host_source_digest",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="最近节点主机摘要"),
        ),
        migrations.AlterField(
            model_name="nodemgmtsyncconfig",
            name="sync_interval_minutes",
            field=models.PositiveIntegerField(default=15, verbose_name="同步周期(分钟)"),
        ),
        migrations.RunPython(bump_builtin_sync_interval, migrations.RunPython.noop),
    ]
