import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0019_dashboard_report_subscription"),
    ]

    operations = [
        migrations.CreateModel(
            name="DashboardReportExecution",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "等待执行"),
                            ("running", "执行中"),
                            ("succeeded", "成功"),
                            ("failed", "失败"),
                            ("unknown", "状态未知"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                        verbose_name="状态",
                    ),
                ),
                (
                    "trigger_type",
                    models.CharField(
                        choices=[("manual", "手动")],
                        default="manual",
                        max_length=16,
                        verbose_name="触发方式",
                    ),
                ),
                (
                    "failure_stage",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=64,
                        verbose_name="失败阶段",
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="错误信息",
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="开始时间",
                    ),
                ),
                (
                    "finished_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="完成时间",
                    ),
                ),
                (
                    "dashboard",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="report_executions",
                        to="operation_analysis.dashboard",
                        verbose_name="仪表盘",
                    ),
                ),
                (
                    "subscription",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="executions",
                        to="operation_analysis.dashboardreportsubscription",
                        verbose_name="报告订阅",
                    ),
                ),
            ],
            options={
                "verbose_name": "仪表盘报告执行",
                "db_table": "operation_analysis_dashboard_report_execution",
                "ordering": ["-id"],
            },
        ),
    ]
