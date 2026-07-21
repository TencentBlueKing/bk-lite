from django.db import migrations, models
from django.db.models import Count


def deduplicate_system_codes(apps, schema_editor):
    collect_models = apps.get_model("cmdb", "CollectModels")
    collect_models.objects.filter(system_code="").update(system_code=None)
    duplicate_codes = list(
        collect_models.objects.exclude(system_code__isnull=True)
        .values("system_code")
        .annotate(task_count=Count("id"))
        .filter(task_count__gt=1)
        .values_list("system_code", flat=True)
    )
    for system_code in duplicate_codes:
        task_ids = list(
            collect_models.objects.filter(system_code=system_code)
            .order_by("id")
            .values_list("id", flat=True)
        )
        collect_models.objects.filter(id__in=task_ids[1:]).update(
            is_system=False,
            is_interval=False,
            system_code=None,
        )


def noop_reverse(apps, schema_editor):
    # 去重会丢弃冲突任务的系统身份，无法可靠恢复原 system_code。
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0041_nodemgmtsyncconfig_collect_dispatch_claim"),
    ]

    operations = [
        migrations.RunPython(deduplicate_system_codes, noop_reverse),
        migrations.AlterField(
            model_name="collectmodels",
            name="system_code",
            field=models.CharField(
                blank=True,
                help_text="系统任务编码",
                max_length=128,
                null=True,
                unique=True,
            ),
        ),
    ]
