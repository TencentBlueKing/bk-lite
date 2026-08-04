from django.db import migrations, models


def backfill_default_fixed_keys(apps, schema_editor):
    Preference = apps.get_model("monitor", "MonitorViewColumnPreference")
    for preference in Preference.objects.all().iterator():
        field_keys = preference.field_keys or []
        if "instance_name" in field_keys:
            preference.fixed_field_keys = ["instance_name"]
            preference.save(update_fields=["fixed_field_keys"])


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0054_metric_view_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorviewcolumnpreference",
            name="fixed_field_keys",
            field=models.JSONField(default=list, verbose_name="左侧固定字段及顺序"),
        ),
        migrations.RunPython(backfill_default_fixed_keys, migrations.RunPython.noop),
    ]
