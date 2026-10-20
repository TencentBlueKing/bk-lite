import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

import apps.rum.models


class Migration(migrations.Migration):
    dependencies = [
        ("rum", "0002_rum_projection_authority"),
    ]

    operations = [
        migrations.DeleteModel(name="RumAlertEvent"),
        migrations.DeleteModel(name="RumAlertPolicy"),
        migrations.CreateModel(
            name="RumAlertPolicy",
            fields=[
                ("id", models.CharField(default=apps.rum.models.new_id, editable=False, max_length=36, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=128)),
                ("application", models.CharField(db_index=True, max_length=128)),
                ("metric", models.CharField(max_length=64)),
                ("severity", models.CharField(default="warning", max_length=32)),
                ("comparator", models.CharField(default=">=", max_length=8)),
                ("warn_threshold", models.FloatField(default=0)),
                ("critical_threshold", models.FloatField(default=0)),
                ("evaluation_window_minutes", models.PositiveIntegerField(default=15)),
                ("for_duration_sec", models.PositiveIntegerField(default=300)),
                ("no_data_after", models.PositiveIntegerField(default=3)),
                ("renotify_minutes", models.PositiveIntegerField(blank=True, null=True)),
                ("handlers", models.JSONField(default=list)),
                ("enabled", models.BooleanField(db_index=True, default=True)),
                ("consecutive_hits", models.PositiveIntegerField(default=0)),
                ("consecutive_recoveries", models.PositiveIntegerField(default=0)),
                ("consecutive_no_data", models.PositiveIntegerField(default=0)),
                ("evaluation_cursor", models.CharField(blank=True, default="", max_length=64)),
                ("last_succeeded_at", models.DateTimeField(blank=True, null=True)),
                ("last_failed_at", models.DateTimeField(blank=True, null=True)),
                ("last_evaluation_result", models.CharField(blank=True, default="", max_length=16)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "rum_alert_policies"},
        ),
        migrations.CreateModel(
            name="RumAlertPolicyOrganization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("organization", models.BigIntegerField(db_index=True)),
                (
                    "policy",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="organization_links", to="rum.rumalertpolicy"),
                ),
            ],
            options={
                "db_table": "rum_alert_policy_organizations",
            },
        ),
        migrations.AddConstraint(
            model_name="rumalertpolicyorganization",
            constraint=models.UniqueConstraint(fields=("policy", "organization"), name="rum_policy_org_uniq"),
        ),
        migrations.CreateModel(
            name="RumAlertPolicyNotificationTarget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel_id", models.PositiveBigIntegerField(db_index=True)),
                ("channel_name", models.CharField(blank=True, default="", max_length=100)),
                ("channel_type", models.CharField(blank=True, default="", max_length=30)),
                ("delivery_mode", models.CharField(max_length=32)),
                ("recipient_mode", models.CharField(max_length=32)),
                ("recipients", models.JSONField(default=list)),
                (
                    "policy",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notification_targets", to="rum.rumalertpolicy"),
                ),
            ],
            options={"db_table": "rum_alert_policy_targets"},
        ),
        migrations.AddConstraint(
            model_name="rumalertpolicynotificationtarget",
            constraint=models.UniqueConstraint(fields=("policy", "channel_id"), name="rum_policy_channel_uniq"),
        ),
        migrations.CreateModel(
            name="RumAlert",
            fields=[
                ("id", models.CharField(default=apps.rum.models.new_id, editable=False, max_length=36, primary_key=True, serialize=False)),
                ("policy_id_snapshot", models.CharField(db_index=True, max_length=36)),
                ("policy_name", models.CharField(max_length=128)),
                ("application", models.CharField(db_index=True, max_length=128)),
                ("metric", models.CharField(max_length=64)),
                ("comparator", models.CharField(blank=True, default="", max_length=8)),
                ("warn_threshold", models.FloatField(default=0)),
                ("critical_threshold", models.FloatField(default=0)),
                ("severity", models.CharField(blank=True, default="", max_length=32)),
                ("status", models.CharField(db_index=True, default="active", max_length=16)),
                ("current_value", models.FloatField(blank=True, null=True)),
                ("organizations", models.JSONField(default=list)),
                ("handlers", models.JSONField(default=list)),
                ("operator", models.CharField(blank=True, default="", max_length=150)),
                ("renotify_count", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(db_index=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("last_event_at", models.DateTimeField(db_index=True)),
                ("last_notified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "policy",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="alerts",
                        to="rum.rumalertpolicy",
                    ),
                ),
            ],
            options={"db_table": "rum_alerts"},
        ),
        migrations.CreateModel(
            name="RumAlertEvent",
            fields=[
                ("id", models.CharField(default=apps.rum.models.new_id, editable=False, max_length=36, primary_key=True, serialize=False)),
                ("event_key", models.CharField(max_length=320, unique=True)),
                ("action", models.CharField(db_index=True, max_length=16)),
                ("occurred_at", models.DateTimeField(db_index=True)),
                ("severity", models.CharField(blank=True, default="", max_length=32)),
                ("value", models.FloatField(blank=True, null=True)),
                ("content", models.JSONField(default=dict)),
                ("organizations", models.JSONField(default=list)),
                ("alert", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="rum.rumalert")),
            ],
            options={
                "db_table": "rum_alert_events",
                "ordering": ("occurred_at", "id"),
            },
        ),
        migrations.CreateModel(
            name="RumAlertDelivery",
            fields=[
                ("id", models.CharField(default=apps.rum.models.new_id, editable=False, max_length=36, primary_key=True, serialize=False)),
                ("delivery_key", models.CharField(max_length=384, unique=True)),
                ("channel_id", models.PositiveBigIntegerField(blank=True, db_index=True, null=True)),
                ("channel_name", models.CharField(blank=True, default="", max_length=100)),
                ("channel_type", models.CharField(blank=True, default="", max_length=30)),
                ("delivery_mode", models.CharField(blank=True, default="message", max_length=32)),
                ("recipients", models.JSONField(default=list)),
                ("title", models.CharField(blank=True, default="", max_length=512)),
                ("body", models.TextField(blank=True, default="")),
                ("payload", models.JSONField(default=dict)),
                ("status", models.CharField(db_index=True, default="pending", max_length=16)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("next_retry_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("last_error_code", models.CharField(blank=True, default="", max_length=128)),
                ("last_error_message", models.CharField(blank=True, default="", max_length=512)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "alert",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deliveries", to="rum.rumalert"),
                ),
                (
                    "event",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="deliveries",
                        to="rum.rumalertevent",
                    ),
                ),
            ],
            options={"db_table": "rum_alert_deliveries"},
        ),
        migrations.CreateModel(
            name="RumAlertDeliveryRetry",
            fields=[
                ("id", models.CharField(default=apps.rum.models.new_id, editable=False, max_length=36, primary_key=True, serialize=False)),
                ("requested_by", models.CharField(max_length=150)),
                ("previous_attempts", models.PositiveIntegerField(default=0)),
                ("previous_error_code", models.CharField(blank=True, default="", max_length=128)),
                ("previous_error_message", models.CharField(blank=True, default="", max_length=512)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "delivery",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="manual_retries", to="rum.rumalertdelivery"),
                ),
            ],
            options={"db_table": "rum_alert_delivery_retries"},
        ),
    ]
