import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0016_network_topology"),
    ]

    operations = [
        migrations.CreateModel(
            name="DashboardShareLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dashboard_instance_id", models.PositiveBigIntegerField(db_index=True)),
                ("tenant_domain", models.CharField(db_index=True, max_length=100)),
                ("space_id", models.PositiveBigIntegerField(db_index=True)),
                ("sharer_username", models.CharField(max_length=100)),
                ("sharer_domain", models.CharField(max_length=100)),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("token_version", models.PositiveIntegerField(default=1)),
                ("authorization_version", models.PositiveBigIntegerField(default=1)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "有效"),
                            ("expired", "已过期"),
                            ("revoked", "已撤销"),
                            ("sharer_permission_lost", "分享者失权"),
                            ("dashboard_invalid", "画布失效"),
                        ],
                        default="active",
                        max_length=32,
                    ),
                ),
                ("invalidated_at", models.DateTimeField(blank=True, null=True)),
                ("invalidated_by", models.CharField(blank=True, default="", max_length=201)),
                ("invalidation_reason", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "dashboard",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="share_links",
                        to="operation_analysis.dashboard",
                    ),
                ),
            ],
            options={"db_table": "operation_analysis_dashboard_share_link"},
        ),
        migrations.CreateModel(
            name="DashboardShareSession",
            fields=[
                ("session_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("visitor_username", models.CharField(max_length=100)),
                ("visitor_domain", models.CharField(max_length=100)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "share_link",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessions",
                        to="operation_analysis.dashboardsharelink",
                    ),
                ),
            ],
            options={"db_table": "operation_analysis_dashboard_share_session"},
        ),
        migrations.AddConstraint(
            model_name="dashboardsharelink",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "active")),
                fields=("dashboard_instance_id", "sharer_username", "sharer_domain"),
                name="uniq_active_dashboard_share_by_sharer",
            ),
        ),
        migrations.AddIndex(
            model_name="dashboardsharelink",
            index=models.Index(fields=["status", "expires_at"], name="op_share_status_exp_idx"),
        ),
        migrations.AddIndex(
            model_name="dashboardsharesession",
            index=models.Index(
                fields=["share_link", "visitor_username", "visitor_domain"],
                name="op_share_session_visitor_idx",
            ),
        ),
    ]
