from django.db import migrations


def pause_empty_instance_scans(apps, schema_editor):
    MonitorPolicy = apps.get_model("monitor", "MonitorPolicy")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    for policy in MonitorPolicy.objects.all().iterator():
        source = policy.source or {}
        if source.get("type") not in {"instance", "organization"}:
            continue
        if source.get("values"):
            continue
        PeriodicTask.objects.filter(name=f"scan_policy_task_{policy.id}", enabled=True).update(enabled=False)


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0080_repair_policy_group_scan_settings"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
    ]

    operations = [
        migrations.RunPython(pause_empty_instance_scans, migrations.RunPython.noop),
    ]
