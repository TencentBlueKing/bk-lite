from django.db import migrations, models


def migrate_notice_type_id_to_ids(apps, schema_editor):
    MonitorPolicy = apps.get_model("monitor", "MonitorPolicy")
    MonitorAlert = apps.get_model("monitor", "MonitorAlert")

    for policy in MonitorPolicy.objects.exclude(notice_type_id=0).iterator():
        policy.notice_type_ids = [policy.notice_type_id]
        policy.save(update_fields=["notice_type_ids"])

    for alert in MonitorAlert.objects.exclude(notice_type_id=0).iterator():
        alert.notice_type_ids = [alert.notice_type_id]
        alert.save(update_fields=["notice_type_ids"])


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0035_monitoralert_notice_type_id_monitoralert_notice_users"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorpolicy",
            name="notice_type_ids",
            field=models.JSONField(default=list, verbose_name="通知方式ID列表"),
        ),
        migrations.AddField(
            model_name="monitoralert",
            name="notice_type_ids",
            field=models.JSONField(default=list, verbose_name="通知方式ID列表"),
        ),
        migrations.AddField(
            model_name="monitoralert",
            name="notice_logs",
            field=models.JSONField(default=list, verbose_name="通知记录"),
        ),
        migrations.RunPython(migrate_notice_type_id_to_ids, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="monitorpolicy",
            name="notice_type_id",
        ),
        migrations.RemoveField(
            model_name="monitoralert",
            name="notice_type_id",
        ),
    ]
