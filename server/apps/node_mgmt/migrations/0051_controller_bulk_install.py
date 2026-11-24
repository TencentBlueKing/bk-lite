import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0050_drop_environment_install"),
    ]

    operations = [
        migrations.CreateModel(
            name="ControllerBulkBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("token", models.CharField(max_length=64, unique=True, verbose_name="批次令牌")),
                ("organization_id", models.PositiveIntegerField(verbose_name="组织")),
                ("package_version_id", models.PositiveIntegerField(verbose_name="控制器版本")),
                ("max_success_count", models.PositiveIntegerField(verbose_name="最多成功台数")),
                ("expires_at", models.DateTimeField(verbose_name="到期时间")),
                ("status", models.CharField(default="active", max_length=20, verbose_name="批次状态")),
                ("revoked_by", models.CharField(blank=True, default="", max_length=32, verbose_name="撤销人")),
                ("push_targets", models.JSONField(default=list, verbose_name="推送目标")),
                ("actor_scope", models.JSONField(default=dict, verbose_name="推送身份")),
                (
                    "cloud_region",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="node_mgmt.cloudregion",
                        verbose_name="云区域",
                    ),
                ),
            ],
            options={
                "verbose_name": "控制器批量安装",
                "verbose_name_plural": "控制器批量安装",
            },
        ),
        migrations.CreateModel(
            name="ControllerBulkAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("ip", models.CharField(blank=True, default="", max_length=64, verbose_name="IP地址")),
                ("node_name", models.CharField(blank=True, default="", max_length=100, verbose_name="节点名称")),
                ("cpu_architecture", models.CharField(blank=True, default="", max_length=20, verbose_name="CPU架构")),
                ("node_id", models.CharField(blank=True, default="", max_length=100, verbose_name="节点ID")),
                ("status", models.CharField(max_length=20, verbose_name="受理状态")),
                ("message", models.CharField(blank=True, default="", max_length=500, verbose_name="结果说明")),
                ("counts_toward_disable", models.BooleanField(default=False, verbose_name="计入失败停用")),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attempts",
                        to="node_mgmt.controllerbulkbatch",
                        verbose_name="批次",
                    ),
                ),
            ],
            options={
                "verbose_name": "控制器批量安装受理",
                "verbose_name_plural": "控制器批量安装受理",
                "indexes": [
                    models.Index(fields=["ip", "status"], name="nm_bulk_attempt_ip_st_idx"),
                    models.Index(fields=["batch", "status"], name="nm_bulk_attempt_batch_st_idx"),
                ],
            },
        ),
    ]
