from django.db import migrations

PRESET_KEY = "builtin_cmdb_resource"
BUSINESS_SYSTEM = "business_system"


def drop_business_system(apps, schema_editor):
    rule_model = apps.get_model("alerts", "EnrichmentRule")
    for rule in rule_model.objects.filter(preset_key=PRESET_KEY):
        projection = list(rule.output_projection or [])
        filtered = [item for item in projection if not (isinstance(item, dict) and item.get("source") == BUSINESS_SYSTEM)]
        if filtered == projection:
            continue
        if not filtered:
            filtered = [{"source": "owner"}]
        rule.output_projection = filtered
        rule.save(update_fields=["output_projection"])


def noop(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0040_merge_itsm_and_escalation_cycle"),
    ]

    operations = [
        migrations.RunPython(drop_business_system, noop),
    ]
