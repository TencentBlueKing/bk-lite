from django.db import migrations
from django.utils import timezone


def backfill_cleanup_policy(apps, schema_editor):
    MonitorInstance = apps.get_model("monitor", "MonitorInstance")
    MonitorObject = apps.get_model("monitor", "MonitorObject")
    MonitorPlugin = apps.get_model("monitor", "MonitorPlugin")
    now = timezone.now()

    builtin_object_ids = MonitorPlugin.objects.filter(is_pre=True).values_list(
        "monitor_object__id", flat=True
    )
    MonitorObject.objects.filter(id__in=builtin_object_ids).update(is_builtin=True)
    MonitorObject.objects.filter(
        type_id="K8S", level="base", parent_id__isnull=True
    ).update(
        cleanup_policy="timeout",
        cleanup_timeout_days=1,
        cleanup_policy_effective_at=now,
    )
    MonitorInstance.objects.filter(auto=True).update(
        last_seen_at=now,
        missing_duration_seconds=0,
    )


class Migration(migrations.Migration):
    dependencies = [("monitor", "0048_monitor_object_cleanup_policy")]

    operations = [
        migrations.RunPython(backfill_cleanup_policy, migrations.RunPython.noop),
    ]
