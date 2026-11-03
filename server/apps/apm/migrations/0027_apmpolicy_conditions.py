from django.db import migrations, models


def backfill_conditions(apps, schema_editor):
    policy_model = apps.get_model("apm", "ApmPolicy")
    for policy in policy_model.objects.all().iterator():
        if policy.conditions:
            continue
        anchor = {
            "ref": "a",
            "role": "regular",
            "metric_type": policy.metric_type,
            "compare_mode": policy.compare_mode or "absolute",
            "compare_offset_amount": policy.compare_offset_amount,
            "compare_value_kind": policy.compare_value_kind or "",
            "min_request_count": policy.min_request_count,
            "slow_threshold_ms": policy.slow_threshold_ms,
            "apdex_threshold_ms": policy.apdex_threshold_ms,
            "thresholds": list(policy.thresholds or []),
        }
        if hasattr(policy, "aggregation"):
            anchor["aggregation"] = policy.aggregation
        policy.conditions = [anchor]
        policy.save(update_fields=["conditions"])


class Migration(migrations.Migration):
    dependencies = [
        ("apm", "0026_alter_apmevent_item"),
    ]

    operations = [
        migrations.AddField(
            model_name="apmpolicy",
            name="conditions",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(backfill_conditions, migrations.RunPython.noop),
    ]
