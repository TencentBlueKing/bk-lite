from django.db import migrations, models


def mark_builtin_preset(apps, schema_editor):
    rule_model = apps.get_model("alerts", "EnrichmentRule")
    existing = rule_model.objects.filter(name="内置-CMDB资源丰富", preset_key="").order_by("id").first()
    if not existing:
        return
    existing.preset_key = "builtin_cmdb_resource"
    existing.input_binding = {"model_id": "resource_type", "inst_uuid": "resource_id"}
    existing.provider_config = {"query_timeout_seconds": 3}
    existing.output_projection = [{"source": "owner"}, {"source": "business_system"}]
    existing.save(
        update_fields=[
            "preset_key",
            "input_binding",
            "provider_config",
            "output_projection",
        ]
    )


class Migration(migrations.Migration):
    dependencies = [("alerts", "0027_alert_monitor_objects_event_cmdb_id_event_monitor_id_and_more")]

    operations = [
        migrations.AddField(
            model_name="enrichmentrule",
            name="preset_key",
            field=models.CharField(blank=True, db_index=True, default="", help_text="内置预设稳定标识", max_length=64),
        ),
        migrations.AlterField(
            model_name="enrichmentrule",
            name="output_projection",
            field=models.JSONField(default=list, help_text="出参投影 [{source, as}]，必须显式声明"),
        ),
        migrations.RunPython(mark_builtin_preset, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="enrichmentrule",
            constraint=models.UniqueConstraint(
                condition=~models.Q(preset_key=""),
                fields=("preset_key",),
                name="alerts_enrichment_preset_key_uniq",
            ),
        ),
    ]
