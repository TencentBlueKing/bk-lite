import django.db.models.deletion
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("apm", "0004_notification_targets_and_delivery_state")]

    operations = [
        migrations.CreateModel(
            name="ApmSlo",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time"),
                ),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                (
                    "updated_by_domain",
                    models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain"),
                ),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=128)),
                ("environment", models.CharField(max_length=256)),
                ("endpoint", models.CharField(blank=True, default="", max_length=512)),
                (
                    "sli_type",
                    models.CharField(
                        choices=[
                            ("availability", "可用性"),
                            ("latency_p95", "P95 时延"),
                            ("latency_p99", "P99 时延"),
                        ],
                        max_length=32,
                    ),
                ),
                ("objective", models.DecimalField(decimal_places=3, max_digits=6)),
                ("latency_threshold_ms", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "evaluation_window",
                    models.CharField(
                        choices=[
                            ("rolling7d", "滚动 7 天"),
                            ("rolling30d", "滚动 30 天"),
                            ("calendarMonth", "自然月"),
                        ],
                        max_length=32,
                    ),
                ),
                ("is_enabled", models.BooleanField(db_index=True, default=True)),
                (
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="slos",
                        to="apm.apmservice",
                    ),
                ),
            ],
            options={"verbose_name": "APM SLO", "verbose_name_plural": "APM SLO", "ordering": ("name", "id")},
        ),
        migrations.AddConstraint(
            model_name="apmslo",
            constraint=models.CheckConstraint(
                check=models.Q(("objective__gt", 0), ("objective__lte", 100)),
                name="apm_slo_objective_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="apmslo",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(("latency_threshold_ms__isnull", True), ("sli_type", "availability"))
                    | models.Q(("latency_threshold_ms__gt", 0), ("sli_type__in", ("latency_p95", "latency_p99")))
                ),
                name="apm_slo_latency_threshold_shape",
            ),
        ),
    ]
