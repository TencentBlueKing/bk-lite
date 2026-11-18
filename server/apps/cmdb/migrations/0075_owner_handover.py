import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0074_collectmodels_enabled"),
    ]

    operations = [
        migrations.AlterField(
            model_name="changerecord",
            name="scenario",
            field=models.CharField(
                choices=[
                    ("device_lifecycle", "设备流转"),
                    ("relation_change", "关系变更"),
                    ("ordinary_attribute_change", "普通属性变更"),
                    ("collect_automation_change", "自动采集"),
                    ("model_management_change", "模型管理变更"),
                    ("custom_reporting_change", "自定义上报变更"),
                    ("governance_confirm", "确认仍有效"),
                    ("owner_handover", "负责人交接"),
                ],
                db_index=True,
                default="ordinary_attribute_change",
                max_length=40,
                verbose_name="变更场景",
            ),
        ),
        migrations.CreateModel(
            name="OwnerHandoverTask",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("operator_username", models.CharField(max_length=150)),
                ("operator_domain", models.CharField(default="domain.com", max_length=100)),
                ("from_user_id", models.IntegerField()),
                ("to_user_id", models.IntegerField()),
                ("from_label", models.CharField(default="", max_length=255)),
                ("to_label", models.CharField(default="", max_length=255)),
                ("model_ids", models.JSONField(default=list)),
                ("team_id", models.IntegerField()),
                ("include_children", models.BooleanField(default=False)),
                ("authorization", models.JSONField(default=dict)),
                ("status", models.CharField(default="queued", max_length=32)),
                ("execution_token", models.CharField(max_length=32)),
                ("idempotency_key", models.CharField(max_length=128)),
                ("request_hash", models.CharField(max_length=64)),
                ("cancel_requested", models.BooleanField(default=False)),
                ("total_count", models.PositiveIntegerField(default=0)),
                ("success_count", models.PositiveIntegerField(default=0)),
                ("skipped_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
                ("message", models.CharField(default="", max_length=512)),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="OwnerHandoverFailure",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("model_id", models.CharField(default="", max_length=128)),
                ("model_name", models.CharField(default="", max_length=128)),
                ("inst_uuid", models.CharField(default="", max_length=64)),
                ("inst_name", models.CharField(default="", max_length=255)),
                ("reason_code", models.CharField(max_length=64)),
                ("message", models.CharField(default="", max_length=200)),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="failures",
                        to="cmdb.ownerhandovertask",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="OwnerHandoverOutcome",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("inst_uuid", models.CharField(max_length=64)),
                ("result", models.CharField(max_length=16)),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="outcomes",
                        to="cmdb.ownerhandovertask",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="ownerhandovertask",
            constraint=models.UniqueConstraint(
                fields=("operator_username", "operator_domain", "idempotency_key"),
                name="cmdb_owner_handover_idempotency",
            ),
        ),
        migrations.AddIndex(
            model_name="ownerhandovertask",
            index=models.Index(fields=["from_user_id", "status"], name="cmdb_handover_from_status"),
        ),
        migrations.AddIndex(
            model_name="ownerhandovertask",
            index=models.Index(
                fields=["operator_username", "operator_domain", "created_at"],
                name="cmdb_handover_operator_date",
            ),
        ),
        migrations.AddIndex(
            model_name="ownerhandoverfailure",
            index=models.Index(fields=["task", "id"], name="cmdb_handover_failure_task"),
        ),
        migrations.AddConstraint(
            model_name="ownerhandoveroutcome",
            constraint=models.UniqueConstraint(fields=("task", "inst_uuid"), name="cmdb_owner_handover_outcome"),
        ),
    ]
