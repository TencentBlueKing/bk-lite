from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
from django.utils import timezone


def set_k8s_default_cleanup_timeout(apps, schema_editor):
    MonitorInstance = apps.get_model("monitor", "MonitorInstance")
    MonitorObject = apps.get_model("monitor", "MonitorObject")
    now = timezone.now()

    k8s_objects = MonitorObject.objects.filter(
        type_id="K8S",
        level="base",
        parent_id__isnull=True,
        cleanup_policy="timeout",
        cleanup_timeout_days=1,
        cleanup_timeout_unit="day",
    )
    k8s_object_ids = list(k8s_objects.values_list("id", flat=True))
    if not k8s_object_ids:
        return

    k8s_objects.update(
        cleanup_timeout_days=30,
        cleanup_timeout_unit="minute",
        cleanup_policy_effective_at=now,
    )
    affected_object_ids = list(
        MonitorObject.objects.filter(parent_id__in=k8s_object_ids).values_list("id", flat=True)
    )
    affected_object_ids.extend(k8s_object_ids)
    MonitorInstance.objects.filter(
        auto=True,
        monitor_object_id__in=affected_object_ids,
    ).update(missing_duration_seconds=0)


class Migration(migrations.Migration):
    dependencies = [("monitor", "0052_merge_metric_view_query_and_policy_template")]

    operations = [
        migrations.AddField(
            model_name="monitorobject",
            name="cleanup_timeout_unit",
            field=models.CharField(
                choices=[("day", "Day"), ("minute", "Minute")],
                default="day",
                max_length=10,
                verbose_name="自动发现资产超时清理时长单位",
            ),
        ),
        migrations.AlterField(
            model_name="monitorobject",
            name="cleanup_timeout_days",
            field=models.PositiveSmallIntegerField(
                default=1,
                validators=[MinValueValidator(1), MaxValueValidator(1440)],
                verbose_name="自动发现资产超时清理时长数值",
            ),
        ),
        migrations.RunPython(set_k8s_default_cleanup_timeout, migrations.RunPython.noop),
    ]
