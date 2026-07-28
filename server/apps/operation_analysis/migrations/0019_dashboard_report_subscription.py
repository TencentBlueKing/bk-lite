from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0018_dashboardsharelink_resource_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="DashboardReportSubscription",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        verbose_name="Created Time",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="Updated Time",
                    ),
                ),
                (
                    "creator",
                    models.CharField(
                        db_index=True,
                        max_length=32,
                        verbose_name="创建者",
                    ),
                ),
                (
                    "name",
                    models.CharField(max_length=128, verbose_name="订阅名称"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "启用"),
                            ("paused", "暂停"),
                            ("terminated", "已终止"),
                        ],
                        db_index=True,
                        default="active",
                        max_length=16,
                        verbose_name="状态",
                    ),
                ),
                (
                    "recipient_email",
                    models.EmailField(
                        max_length=254,
                        verbose_name="接收邮箱",
                    ),
                ),
                (
                    "config",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        verbose_name="扩展配置",
                    ),
                ),
                (
                    "dashboard",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="report_subscriptions",
                        to="operation_analysis.dashboard",
                        verbose_name="仪表盘",
                    ),
                ),
            ],
            options={
                "verbose_name": "仪表盘报告订阅",
                "db_table": "operation_analysis_dashboard_report_subscription",
                "ordering": ["-id"],
            },
        ),
    ]
