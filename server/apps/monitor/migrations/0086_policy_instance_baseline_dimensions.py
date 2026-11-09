import ast

from django.db import migrations, models


def backfill_baseline_dimensions(apps, schema_editor):
    Baseline = apps.get_model("monitor", "PolicyInstanceBaseline")
    Policy = apps.get_model("monitor", "MonitorPolicy")
    group_by_by_policy = {policy.id: list(policy.group_by or []) for policy in Policy.objects.all().only("id", "group_by")}
    pending = []
    for baseline in Baseline.objects.all().iterator():
        keys = group_by_by_policy.get(baseline.policy_id) or []
        dimensions = _dimensions_from_tuple_text(baseline.metric_instance_id, keys)
        if not dimensions:
            continue
        baseline.dimensions = dimensions
        pending.append(baseline)
        if len(pending) >= 500:
            Baseline.objects.bulk_update(pending, ["dimensions"])
            pending = []
    if pending:
        Baseline.objects.bulk_update(pending, ["dimensions"])


def _dimensions_from_tuple_text(metric_instance_id, keys):
    if not keys or not isinstance(metric_instance_id, str):
        return {}
    try:
        parsed = ast.literal_eval(metric_instance_id)
    except (ValueError, SyntaxError):
        return {}
    if not isinstance(parsed, tuple):
        return {}
    return {keys[index]: parsed[index] for index in range(min(len(keys), len(parsed)))}


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0085_collectconfig_executor_node_removed"),
    ]

    operations = [
        migrations.AddField(
            model_name="policyinstancebaseline",
            name="dimensions",
            field=models.JSONField(default=dict, verbose_name="维度值"),
        ),
        migrations.RunPython(backfill_baseline_dimensions, migrations.RunPython.noop),
    ]
