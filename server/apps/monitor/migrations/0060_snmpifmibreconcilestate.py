from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0059_rename_monitor_object_type_host_resource_to_os"),
    ]

    operations = [
        migrations.CreateModel(
            name="SnmpIfmibReconcileState",
            fields=[
                ("version", models.PositiveIntegerField(primary_key=True, serialize=False)),
                ("owner_token", models.CharField(blank=True, default="", max_length=64)),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("cursor_created_at", models.DateTimeField(blank=True, null=True)),
                ("cursor_config_id", models.CharField(blank=True, default="", max_length=255)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "monitor_snmp_ifmib_reconcile_state"},
        ),
    ]
