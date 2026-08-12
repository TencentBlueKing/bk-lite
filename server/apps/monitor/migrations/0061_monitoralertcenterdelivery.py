import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("monitor", "0060_snmpifmibreconcilestate")]

    operations = [
        migrations.AddField(
            model_name="monitoralert",
            name="alert_center_delivery_backfilled",
            field=models.BooleanField(default=False, null=True, verbose_name="告警中心投递意图已对账"),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="monitoralert",
            name="alert_center_delivery_backfilled",
            field=models.BooleanField(default=True, null=True, verbose_name="告警中心投递意图已对账"),
        ),
        migrations.CreateModel(
            name="MonitorAlertCenterDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("action", models.CharField(max_length=20, verbose_name="生命周期动作")),
                ("generation", models.PositiveIntegerField(verbose_name="告警内投递代次")),
                ("delivery_id", models.CharField(max_length=64, unique=True, verbose_name="投递幂等标识")),
                ("channel_id", models.PositiveBigIntegerField(verbose_name="通知通道 ID")),
                ("payload", models.JSONField(default=dict, verbose_name="不可变投递载荷")),
                ("status", models.CharField(choices=[("pending", "待投递"), ("delivering", "投递中"), ("delivered", "已投递"), ("failed", "投递失败")], db_index=True, default="pending", max_length=16)),
                ("attempts", models.PositiveIntegerField(default=0, verbose_name="投递次数")),
                ("max_attempts", models.PositiveIntegerField(default=10, verbose_name="最大投递次数")),
                ("next_retry_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                ("alert", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alert_center_deliveries", to="monitor.monitoralert", verbose_name="监控告警")),
            ],
            options={
                "db_table": "monitor_alert_center_delivery",
                "indexes": [
                    models.Index(fields=["status", "next_retry_at"], name="idx_monitor_delivery_retry"),
                    models.Index(fields=["alert", "generation"], name="idx_monitor_delivery_order"),
                ],
                "constraints": [models.UniqueConstraint(fields=("alert", "generation"), name="uniq_monitor_alert_delivery_gen")],
            },
        ),
    ]
