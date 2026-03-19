from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0028_add_config_section_to_childconfig"),
    ]

    operations = [
        migrations.CreateModel(
            name="CollectorActionTask",
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
                        auto_now_add=True, db_index=True, verbose_name="Created Time"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Updated Time"),
                ),
                (
                    "created_by",
                    models.CharField(default="", max_length=32, verbose_name="Creator"),
                ),
                (
                    "updated_by",
                    models.CharField(default="", max_length=32, verbose_name="Updater"),
                ),
                (
                    "domain",
                    models.CharField(
                        default="domain.com", max_length=100, verbose_name="Domain"
                    ),
                ),
                (
                    "updated_by_domain",
                    models.CharField(
                        default="domain.com",
                        max_length=100,
                        verbose_name="updated by domain",
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("start", "启动"),
                            ("restart", "重启"),
                            ("stop", "停止"),
                        ],
                        max_length=20,
                        verbose_name="动作类型",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        default="waiting", max_length=100, verbose_name="任务状态"
                    ),
                ),
                (
                    "total_count",
                    models.IntegerField(default=0, verbose_name="总节点数"),
                ),
                (
                    "success_count",
                    models.IntegerField(default=0, verbose_name="成功节点数"),
                ),
                (
                    "error_count",
                    models.IntegerField(default=0, verbose_name="失败节点数"),
                ),
                (
                    "cloud_region",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="node_mgmt.cloudregion",
                        verbose_name="云区域",
                    ),
                ),
                (
                    "collector",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="node_mgmt.collector",
                        verbose_name="采集器",
                    ),
                ),
            ],
            options={
                "verbose_name": "采集器动作任务",
                "verbose_name_plural": "采集器动作任务",
            },
        ),
        migrations.CreateModel(
            name="CollectorActionTaskNode",
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
                    "status",
                    models.CharField(
                        default="waiting", max_length=100, verbose_name="任务状态"
                    ),
                ),
                ("result", models.JSONField(default=dict, verbose_name="结果")),
                (
                    "node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="node_mgmt.node",
                        verbose_name="节点",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="node_mgmt.collectoractiontask",
                        verbose_name="任务",
                    ),
                ),
            ],
            options={
                "verbose_name": "采集器动作任务节点",
                "verbose_name_plural": "采集器动作任务节点",
                "unique_together": {("task", "node")},
            },
        ),
    ]
