import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("module_link", "0002_monitorlinktaskitem_port"),
    ]

    operations = [
        migrations.CreateModel(
            name="MonitorCmdbTask",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("operator", models.CharField(default="", max_length=128)),
                ("team", models.JSONField(default=list)),
                ("object_name", models.CharField(default="", max_length=128)),
                ("status", models.CharField(db_index=True, default="waiting_create", max_length=32)),
                ("summary", models.JSONField(default=dict)),
                ("retain_until", models.DateTimeField(db_index=True)),
            ],
            options={
                "verbose_name": "监控-CMDB同步任务",
            },
        ),
        migrations.CreateModel(
            name="MonitorCmdbTaskItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("monitor_id", models.CharField(db_index=True, max_length=256)),
                ("object_name", models.CharField(default="", max_length=128)),
                ("model_id", models.CharField(default="", max_length=128)),
                ("inst_name", models.CharField(default="", max_length=256)),
                ("ip", models.CharField(default="", max_length=128)),
                ("organization", models.JSONField(default=list)),
                ("cloud_region_id", models.IntegerField(blank=True, null=True)),
                ("status", models.CharField(db_index=True, max_length=32)),
                ("cmdb_id", models.CharField(default="", max_length=64)),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="module_link.monitorcmdbtask",
                    ),
                ),
            ],
            options={
                "verbose_name": "监控-CMDB同步任务行",
            },
        ),
        migrations.AddIndex(
            model_name="monitorcmdbtaskitem",
            index=models.Index(fields=["task", "status"], name="module_link_task_id_rev_idx"),
        ),
    ]
