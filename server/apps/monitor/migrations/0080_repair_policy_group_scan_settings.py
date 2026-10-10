from django.db import migrations


def repair_group_rule_scan_defaults(apps, schema_editor):
    PolicyGroupRule = apps.get_model("monitor", "PolicyGroupRule")
    default_period = {"type": "min", "value": 5}
    for rule in PolicyGroupRule.objects.select_related("policy").iterator():
        policy = rule.policy
        fields = []
        if not policy.period:
            policy.period = default_period
            fields.append("period")
        if not policy.enable_alerts:
            policy.enable_alerts = ["threshold"]
            fields.append("enable_alerts")
        if fields:
            policy.save(update_fields=[*fields, "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0079_policy_group_default"),
    ]

    operations = [
        migrations.RunPython(repair_group_rule_scan_defaults, migrations.RunPython.noop),
    ]
