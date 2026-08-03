import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.utils.dateparse import parse_datetime


def backfill_owned_events(apps, schema_editor):
    ApmAlert = apps.get_model("apm", "ApmAlert")
    ApmEvent = apps.get_model("apm", "ApmEvent")
    ApmAlertOutbox = apps.get_model("apm", "ApmAlertOutbox")
    ApmPolicy = apps.get_model("apm", "ApmPolicy")
    ApmService = apps.get_model("apm", "ApmService")

    for outbox in ApmAlertOutbox.objects.order_by("created_at", "id").iterator():
        payload = outbox.payload if isinstance(outbox.payload, dict) else {}
        external_id = str(payload.get("external_id") or outbox.event_key.split(":", 1)[0])
        action = str(payload.get("action") or "created")
        occurred_at = parse_datetime(str(payload.get("occurred_at") or "")) or outbox.created_at
        policy_id = str(payload.get("rule_id") or "")
        resource_id = str(payload.get("resource_id") or "")
        try:
            policy = ApmPolicy.objects.filter(id=policy_id).first() if policy_id else None
        except (TypeError, ValueError):
            policy = None
        try:
            service = ApmService.objects.filter(id=resource_id).first() if resource_id else None
        except (TypeError, ValueError):
            service = None

        labels = payload.get("labels") if isinstance(payload.get("labels"), dict) else {}
        organizations = payload.get("organizations") if isinstance(payload.get("organizations"), list) else []
        status = "recovered" if action == "recovery" else "firing"
        alert, _ = ApmAlert.objects.get_or_create(
            external_id=external_id,
            defaults={
                "policy": policy,
                "service": service,
                "policy_id_snapshot": policy_id,
                "policy_name": str(labels.get("policy_name") or ""),
                "service_namespace": str(labels.get("service_namespace") or ""),
                "service_name": str(payload.get("service") or labels.get("service_name") or ""),
                "environment": str(labels.get("environment") or ""),
                "metric_type": str(payload.get("item") or "error_rate"),
                "severity": str(payload.get("severity") or "warning"),
                "status": status,
                "current_value": payload.get("value"),
                "organizations": organizations,
                "started_at": occurred_at,
                "ended_at": occurred_at if action == "recovery" else None,
                "last_event_at": occurred_at,
            },
        )
        if occurred_at >= alert.last_event_at:
            alert.status = status
            alert.current_value = payload.get("value")
            alert.organizations = organizations
            alert.last_event_at = occurred_at
            if action == "recovery":
                alert.ended_at = occurred_at
            alert.save()

        event, _ = ApmEvent.objects.get_or_create(
            event_id=outbox.event_key,
            defaults={
                "alert": alert,
                "action": action,
                "title": str(payload.get("title") or ""),
                "description": str(payload.get("description") or ""),
                "severity": str(payload.get("severity") or "warning"),
                "service": str(payload.get("service") or labels.get("service_name") or ""),
                "item": str(payload.get("item") or "error_rate"),
                "value": payload.get("value"),
                "resource_id": resource_id,
                "resource_name": str(payload.get("resource_name") or ""),
                "policy_id": policy_id,
                "environment": str(labels.get("environment") or ""),
                "organizations": organizations,
                "occurred_at": occurred_at,
                "ended_at": occurred_at if action == "recovery" else None,
            },
        )
        outbox.event = event
        # 旧投递箱没有用户选择的渠道 ID，不能继续猜测目的地；
        # 领域事件保留后停止旧任务重试。
        outbox.delivery_status = "delivered"
        outbox.next_retry_at = None
        outbox.save(update_fields=("event", "delivery_status", "next_retry_at", "updated_at"))


class Migration(migrations.Migration):
    dependencies = [("apm", "0002_ingest_source_identity_diagnostic")]

    operations = [
        migrations.AddField(
            model_name="apmpolicy",
            name="notice",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="apmpolicy",
            name="notice_type_ids",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="apmpolicy",
            name="notice_users",
            field=models.JSONField(default=list),
        ),
        migrations.CreateModel(
            name="ApmAlert",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                (
                    "updated_by_domain",
                    models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain"),
                ),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("external_id", models.CharField(max_length=256, unique=True)),
                ("policy_id_snapshot", models.CharField(max_length=36)),
                ("policy_name", models.CharField(max_length=256)),
                ("service_namespace", models.CharField(blank=True, default="", max_length=256)),
                ("service_name", models.CharField(max_length=256)),
                ("environment", models.CharField(blank=True, default="", max_length=256)),
                (
                    "metric_type",
                    models.CharField(
                        choices=[
                            ("error_rate", "错误率"),
                            ("p95", "P95"),
                            ("p99", "P99"),
                            ("throughput", "吞吐"),
                            ("no_traffic", "无流量"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "severity",
                    models.CharField(
                        choices=[("critical", "严重"), ("error", "错误"), ("warning", "警告")],
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("firing", "告警中"), ("recovered", "已恢复")],
                        db_index=True,
                        default="firing",
                        max_length=16,
                    ),
                ),
                ("current_value", models.DecimalField(blank=True, decimal_places=6, max_digits=20, null=True)),
                ("organizations", models.JSONField(default=list)),
                ("started_at", models.DateTimeField(db_index=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("last_event_at", models.DateTimeField(db_index=True)),
                (
                    "policy",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="alerts",
                        to="apm.apmpolicy",
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="alerts",
                        to="apm.apmservice",
                    ),
                ),
            ],
            options={
                "verbose_name": "APM 告警",
                "verbose_name_plural": "APM 告警",
                "ordering": ("-last_event_at", "-id"),
            },
        ),
        migrations.CreateModel(
            name="ApmEvent",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                (
                    "updated_by_domain",
                    models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain"),
                ),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_id", models.CharField(max_length=320, unique=True)),
                (
                    "action",
                    models.CharField(
                        choices=[("created", "触发"), ("recovery", "恢复")],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("title", models.CharField(max_length=512)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "severity",
                    models.CharField(
                        choices=[("critical", "严重"), ("error", "错误"), ("warning", "警告")],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("service", models.CharField(max_length=256)),
                (
                    "item",
                    models.CharField(
                        choices=[
                            ("error_rate", "错误率"),
                            ("p95", "P95"),
                            ("p99", "P99"),
                            ("throughput", "吞吐"),
                            ("no_traffic", "无流量"),
                        ],
                        max_length=32,
                    ),
                ),
                ("value", models.DecimalField(blank=True, decimal_places=6, max_digits=20, null=True)),
                ("resource_id", models.CharField(max_length=36)),
                ("resource_name", models.CharField(max_length=512)),
                ("policy_id", models.CharField(db_index=True, max_length=36)),
                ("environment", models.CharField(blank=True, default="", max_length=256)),
                ("organizations", models.JSONField(default=list)),
                ("occurred_at", models.DateTimeField(db_index=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                (
                    "alert",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="apm.apmalert",
                    ),
                ),
            ],
            options={
                "verbose_name": "APM 告警事件",
                "verbose_name_plural": "APM 告警事件",
                "ordering": ("-occurred_at", "-id"),
            },
        ),
        migrations.AlterField(
            model_name="apmalertoutbox",
            name="event_key",
            field=models.CharField(max_length=384, unique=True),
        ),
        migrations.AddField(
            model_name="apmalertoutbox",
            name="channel_id",
            field=models.PositiveBigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="apmalertoutbox",
            name="event",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="outbox_entries",
                to="apm.apmevent",
            ),
        ),
        migrations.AddField(
            model_name="apmalertoutbox",
            name="receivers",
            field=models.JSONField(default=list),
        ),
        migrations.RunPython(backfill_owned_events, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="apmalertoutbox",
            constraint=models.UniqueConstraint(
                condition=models.Q(("channel_id__isnull", False), ("event__isnull", False)),
                fields=("event", "channel_id"),
                name="apm_outbox_event_channel_unique",
            ),
        ),
    ]
