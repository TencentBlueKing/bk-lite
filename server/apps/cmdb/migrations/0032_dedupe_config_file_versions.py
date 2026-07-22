from django.db import migrations, models


def dedupe_config_file_versions(apps, _schema_editor):
    config_file_version = apps.get_model("cmdb", "ConfigFileVersion")
    duplicate_keys = (
        config_file_version.objects.exclude(collect_task_id=None)
        .values("collect_task_id", "instance_id", "version")
        .annotate(record_count=models.Count("id"))
        .filter(record_count__gt=1)
    )

    for duplicate_key in duplicate_keys.iterator():
        duplicate_ids = list(
            config_file_version.objects.filter(
                collect_task_id=duplicate_key["collect_task_id"],
                instance_id=duplicate_key["instance_id"],
                version=duplicate_key["version"],
            )
            .order_by("created_at", "id")
            .values_list("id", flat=True)
        )
        config_file_version.objects.filter(id__in=duplicate_ids[1:]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0031_subscriptiondelivery"),
    ]

    operations = [
        migrations.RunPython(dedupe_config_file_versions, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="configfileversion",
            constraint=models.UniqueConstraint(
                fields=("collect_task", "instance_id", "version"),
                name="uniq_cfg_ver_task_inst_version",
            ),
        ),
    ]
