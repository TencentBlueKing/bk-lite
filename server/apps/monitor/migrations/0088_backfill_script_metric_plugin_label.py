from django.db import migrations


def backfill_script_metric_queries(apps, schema_editor):
    Metric = apps.get_model("monitor", "Metric")
    Plugin = apps.get_model("monitor", "MonitorPlugin")
    plugins = {plugin.id: plugin for plugin in Plugin.objects.filter(collect_type__iexact="script")}
    pending = []
    for metric in Metric.objects.filter(monitor_plugin_id__in=list(plugins)).iterator():
        plugin = plugins.get(metric.monitor_plugin_id)
        label = str(getattr(plugin, "template_id", None) or plugin.id or "")
        query = metric.query or ""
        if not label or "plugin_id=" in query or "__$labels__" not in query:
            continue
        escaped = label.replace("\\", "\\\\").replace('"', '\\"')
        metric.query = query.replace("__$labels__", f'plugin_id="{escaped}",__$labels__')
        pending.append(metric)
        if len(pending) >= 500:
            Metric.objects.bulk_update(pending, ["query"])
            pending = []
    if pending:
        Metric.objects.bulk_update(pending, ["query"])


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0087_collectconfig_plugin_scope"),
    ]

    operations = [
        migrations.RunPython(backfill_script_metric_queries, migrations.RunPython.noop),
    ]
