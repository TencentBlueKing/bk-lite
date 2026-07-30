from django.db import migrations, models


def migrate_asset_ip_to_summary_facts(apps, schema_editor):
    MonitorInstance = apps.get_model("monitor", "MonitorInstance")
    for instance in MonitorInstance.objects.exclude(ip__isnull=True).iterator(chunk_size=1000):
        instance.summary_facts = {"asset.ip": str(instance.ip)}
        instance.save(update_fields=["summary_facts"])


class Migration(migrations.Migration):
    dependencies = [("monitor", "0049_backfill_monitor_object_cleanup_policy")]

    operations = [
        migrations.AddField(
            model_name="monitorobject",
            name="instance_summary_columns",
            field=models.JSONField(default=list, verbose_name="实例摘要列"),
        ),
        migrations.AddField(
            model_name="monitorplugin",
            name="instance_fact_bindings",
            field=models.JSONField(blank=True, default=list, verbose_name="实例事实绑定"),
        ),
        migrations.AddField(
            model_name="monitorinstance",
            name="summary_facts",
            field=models.JSONField(default=dict, verbose_name="实例摘要事实"),
        ),
        migrations.RunPython(migrate_asset_ip_to_summary_facts, migrations.RunPython.noop),
    ]
