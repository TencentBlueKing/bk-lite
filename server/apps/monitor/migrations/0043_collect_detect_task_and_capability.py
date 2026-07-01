from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0042_monitorpolicy_group_algorithm"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorplugin",
            name="support_collect_detect",
            field=models.BooleanField(default=False, verbose_name="是否支持接入前采集检测"),
        ),
        migrations.CreateModel(
            name="CollectDetectTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="检测状态",
                    ),
                ),
                (
                    "phase",
                    models.CharField(
                        choices=[
                            ("validate", "Validate"),
                            ("render_config", "Render Config"),
                            ("prepare_runtime", "Prepare Runtime"),
                            ("execute_once", "Execute Once"),
                            ("parse_output", "Parse Output"),
                        ],
                        default="validate",
                        max_length=40,
                        verbose_name="检测阶段",
                    ),
                ),
                ("monitor_plugin_id", models.IntegerField(verbose_name="监控插件ID")),
                ("monitor_object_id", models.IntegerField(verbose_name="监控对象ID")),
                ("collector", models.CharField(max_length=100, verbose_name="采集器")),
                ("collect_type", models.CharField(max_length=50, verbose_name="采集类型")),
                ("node_id", models.CharField(max_length=100, verbose_name="节点ID")),
                ("instance_key", models.CharField(blank=True, default="", max_length=100, verbose_name="实例行标识")),
                ("request_fingerprint", models.CharField(max_length=64, verbose_name="请求指纹")),
                ("created_by", models.CharField(max_length=150, verbose_name="发起人")),
                ("organization", models.IntegerField(verbose_name="组织ID")),
                ("request_snapshot", models.JSONField(default=dict, verbose_name="脱敏请求快照")),
                ("result", models.JSONField(default=dict, verbose_name="检测结果")),
                ("error_message", models.TextField(blank=True, default="", verbose_name="错误信息")),
                ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="开始时间")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="结束时间")),
            ],
            options={
                "verbose_name": "采集检测任务",
                "verbose_name_plural": "采集检测任务",
            },
        ),
        migrations.AddIndex(
            model_name="collectdetecttask",
            index=models.Index(
                fields=["created_by", "organization", "created_at"],
                name="monitor_col_created_c7784c_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="collectdetecttask",
            index=models.Index(fields=["status", "created_at"], name="monitor_col_status_294b82_idx"),
        ),
        migrations.AddIndex(
            model_name="collectdetecttask",
            index=models.Index(fields=["request_fingerprint"], name="monitor_col_request_d64323_idx"),
        ),
    ]
