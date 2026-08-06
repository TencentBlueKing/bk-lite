from django.db import migrations, models


IFMIB_METRIC_NAMES = (
    "interface_ifAdminStatus",
    "interface_ifOperStatus",
    "interface_ifSpeed",
    "interface_ifInErrors",
    "interface_ifOutErrors",
    "interface_ifInDiscards",
    "interface_ifOutDiscards",
    "interface_ifInUcastPkts",
    "interface_ifOutUcastPkts",
    "interface_ifInOctets",
    "interface_ifOutOctets",
    "interface_ifHCInOctets",
    "interface_ifHCOutOctets",
    "device_total_incoming_traffic",
    "device_total_outgoing_traffic",
)


def mark_existing_ifmib_metrics(apps, schema_editor):
    Metric = apps.get_model("monitor", "Metric")
    Metric.objects.filter(
        is_pre=True,
        name__in=IFMIB_METRIC_NAMES,
        monitor_plugin__collect_type__startswith="snmp",
    ).update(is_ifmib=True)


class Migration(migrations.Migration):
    dependencies = [("monitor", "0057_monitorinstance_node_id_cmdb_id")]

    operations = [
        migrations.AddField(
            model_name="metric",
            name="is_ifmib",
            field=models.BooleanField(default=False, verbose_name="是否来自公共IF-MIB"),
        ),
        migrations.RunPython(mark_existing_ifmib_metrics, migrations.RunPython.noop),
    ]
