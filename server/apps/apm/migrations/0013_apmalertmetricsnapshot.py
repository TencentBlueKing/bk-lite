import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("apm", "0012_apmpolicy_no_data_alert_name")]

    operations = [
        migrations.DeleteModel(name="ApmPolicyState"),
        migrations.RemoveField(model_name="apmpolicy", name="comparator"),
        migrations.RemoveField(model_name="apmpolicy", name="threshold"),
        migrations.RemoveField(model_name="apmpolicy", name="duration_window"),
        migrations.RemoveField(model_name="apmpolicy", name="recovery_window"),
        migrations.RemoveField(model_name="apmpolicy", name="severity"),
        migrations.RemoveField(model_name="apmpolicy", name="notice"),
        migrations.RemoveField(model_name="apmpolicy", name="notice_type_ids"),
        migrations.RemoveField(model_name="apmpolicy", name="notice_users"),
        migrations.CreateModel(
            name="ApmAlertMetricSnapshot",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("unit", models.CharField(blank=True, default="", max_length=32)),
                (
                    "aggregation",
                    models.CharField(
                        choices=[("avg", "平均值"), ("max", "最大值"), ("min", "最小值"), ("last", "最新值")],
                        max_length=16,
                    ),
                ),
                ("evaluation_interval", models.PositiveIntegerField()),
                ("metric_window", models.PositiveIntegerField()),
                ("snapshots", models.JSONField(default=list, verbose_name="快照数据集合")),
                (
                    "alert",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="metric_snapshot",
                        to="apm.apmalert",
                    ),
                ),
            ],
            options={
                "verbose_name": "APM 告警指标快照",
                "verbose_name_plural": "APM 告警指标快照",
            },
        ),
    ]
