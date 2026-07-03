from django.db import migrations, models


LEGACY_ALGORITHM_MAPPING = {
    "avg": ("avg", "avg_over_time"),
    "avg_over_time": ("avg", "avg_over_time"),
    "max": ("max", "max_over_time"),
    "max_over_time": ("max", "max_over_time"),
    "min": ("min", "min_over_time"),
    "min_over_time": ("min", "min_over_time"),
    "sum": ("sum", "sum_over_time"),
    "sum_over_time": ("sum", "sum_over_time"),
    "count": ("count", "last_over_time"),
    "count_over_time": ("count", "count_over_time"),
    "last_over_time": ("avg", "last_over_time"),
}


def migrate_policy_algorithms(apps, schema_editor):
    MonitorPolicy = apps.get_model("monitor", "MonitorPolicy")
    policies = MonitorPolicy.objects.only("algorithm", "group_algorithm")
    pending = []
    for policy in policies:
        group_algorithm, algorithm = LEGACY_ALGORITHM_MAPPING.get(
            str(policy.algorithm or "").lower(),
            ("avg", policy.algorithm),
        )
        policy.group_algorithm = group_algorithm
        policy.algorithm = algorithm
        pending.append(policy)

    if pending:
        MonitorPolicy.objects.bulk_update(pending, ["group_algorithm", "algorithm"])


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0041_monitorpolicy_trigger_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorpolicy",
            name="group_algorithm",
            field=models.CharField(default="avg", max_length=50, verbose_name="分组聚合算法"),
        ),
        migrations.RunPython(migrate_policy_algorithms, migrations.RunPython.noop),
    ]
