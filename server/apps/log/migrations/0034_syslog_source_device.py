from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0033_collectinstance_removed_collector_node_id_index"),
    ]

    operations = [
        migrations.CreateModel(
            name="SyslogSourceDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cloud_region_id", models.CharField(max_length=64, verbose_name="云区域ID")),
                ("source_ip", models.CharField(max_length=128, verbose_name="源IP")),
                ("hostname", models.CharField(blank=True, default="", max_length=255, verbose_name="主机名")),
                ("first_seen", models.DateTimeField(verbose_name="首次收到")),
                ("last_seen", models.DateTimeField(verbose_name="最近收到")),
            ],
            options={
                "verbose_name": "syslog来源设备",
                "verbose_name_plural": "syslog来源设备",
                "indexes": [models.Index(fields=["last_seen"], name="log_syslog_src_last_seen_idx")],
            },
        ),
        migrations.AddConstraint(
            model_name="syslogsourcedevice",
            constraint=models.UniqueConstraint(
                fields=("cloud_region_id", "source_ip", "hostname"),
                name="log_syslog_source_device_identity_uniq",
            ),
        ),
    ]
