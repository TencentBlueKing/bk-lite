import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0048_collecttaskcredentialhit_recent_result_event_ids"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScanTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                (
                    "updated_by_domain",
                    models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain"),
                ),
                ("name", models.CharField(help_text="扫描任务名称", max_length=128)),
                ("team", models.JSONField(default=list, help_text="关联组织")),
                ("access_point", models.JSONField(default=list, help_text="接入点")),
                ("ip_ranges", models.JSONField(default=list, help_text="IP 起止范围列表")),
                ("cloud_region", models.JSONField(default=dict, help_text="主机扫描云区域")),
                ("families", models.JSONField(default=list, help_text="勾选的凭据族 / 模型")),
                ("credentials", models.JSONField(default=dict, help_text="按族存储的凭据池")),
                ("auto_push_monitor", models.BooleanField(default=False, help_text="执行后自动推监控")),
                ("auto_generate_collect", models.BooleanField(default=False, help_text="执行后自动生成采集")),
                ("timeout", models.PositiveSmallIntegerField(default=0, help_text="单个 IP 超时秒数")),
            ],
            options={
                "verbose_name": "扫描任务",
                "verbose_name_plural": "扫描任务",
            },
        ),
        migrations.CreateModel(
            name="ScanExecution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "待执行"),
                            ("running", "执行中"),
                            ("finalizing", "收口中"),
                            ("completed", "已完成"),
                            ("failed", "失败"),
                            ("timed_out", "超时"),
                        ],
                        default="pending",
                        max_length=32,
                    ),
                ),
                ("claim_token", models.CharField(blank=True, default="", help_text="执行领取令牌", max_length=128)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("deadline_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("target_count", models.PositiveIntegerField(default=0)),
                ("received_count", models.PositiveIntegerField(default=0)),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="executions",
                        to="cmdb.scantask",
                    ),
                ),
            ],
            options={
                "verbose_name": "扫描执行",
                "verbose_name_plural": "扫描执行",
            },
        ),
        migrations.CreateModel(
            name="ScanFamilyRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("model_id", models.CharField(max_length=64)),
                (
                    "driver_type",
                    models.CharField(
                        choices=[("protocol", "协议采集"), ("job", "脚本采集")],
                        max_length=32,
                    ),
                ),
                ("target_count", models.PositiveIntegerField(default=0)),
                ("received_count", models.PositiveIntegerField(default=0)),
                (
                    "admit_status",
                    models.CharField(
                        choices=[
                            ("pending", "待接纳"),
                            ("accepted", "已接纳"),
                            ("duplicate", "去重跳过"),
                            ("failed", "接纳失败"),
                        ],
                        default="pending",
                        max_length=32,
                    ),
                ),
                (
                    "execution",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="family_runs",
                        to="cmdb.scanexecution",
                    ),
                ),
            ],
            options={
                "verbose_name": "扫描族执行",
                "verbose_name_plural": "扫描族执行",
                "unique_together": {("execution", "model_id", "driver_type")},
            },
        ),
        migrations.CreateModel(
            name="ScanHit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("protocol", models.CharField(max_length=32)),
                ("host", models.CharField(max_length=64)),
                ("port", models.PositiveIntegerField(default=0)),
                ("credential_id", models.CharField(blank=True, default="", max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[("success", "成功"), ("failed", "失败"), ("unreachable", "不可达")],
                        max_length=32,
                    ),
                ),
                ("soid", models.CharField(blank=True, default="", max_length=256)),
                ("cmdb_model_id", models.CharField(blank=True, default="", max_length=64)),
                ("inst_uuid", models.CharField(blank=True, default="", max_length=36)),
                ("attached_inst_uuid", models.CharField(blank=True, default="", max_length=36)),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                ("snapshot", models.JSONField(default=dict)),
                (
                    "execution",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hits",
                        to="cmdb.scanexecution",
                    ),
                ),
                (
                    "family_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hits",
                        to="cmdb.scanfamilyrun",
                    ),
                ),
            ],
            options={
                "verbose_name": "扫描命中",
                "verbose_name_plural": "扫描命中",
                "unique_together": {("family_run", "host", "port", "credential_id")},
            },
        ),
        migrations.AddIndex(
            model_name="scanexecution",
            index=models.Index(fields=["task", "status"], name="cmdb_scan_exec_task_status_idx"),
        ),
        migrations.AddIndex(
            model_name="scanhit",
            index=models.Index(fields=["execution", "status"], name="cmdb_scan_hit_exec_status_idx"),
        ),
        migrations.AddIndex(
            model_name="scanhit",
            index=models.Index(fields=["execution", "host"], name="cmdb_scan_hit_exec_host_idx"),
        ),
    ]
