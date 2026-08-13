from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("patch_mgmt", "0008_patch_deleted_source_snapshots")]

    operations = [
        migrations.AddField(
            model_name="scansetting",
            name="notification_enabled",
            field=models.BooleanField(default=False, verbose_name="是否启用周期评估通知"),
        ),
        migrations.AddField(
            model_name="scansetting",
            name="notification_rules",
            field=models.JSONField(default=list, verbose_name="周期评估通知规则"),
        ),
        migrations.AddField(
            model_name="governancetask",
            name="notification_snapshot",
            field=models.JSONField(default=dict, verbose_name="通知配置快照"),
        ),
        migrations.AddField(
            model_name="governancetask",
            name="trigger_source",
            field=models.CharField(
                db_index=True,
                default="manual",
                max_length=32,
                verbose_name="任务触发来源",
            ),
        ),
        migrations.AddField(
            model_name="governancetask",
            name="notification_reconciled_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="通知意图已对账时间",
            ),
        ),
        migrations.CreateModel(
            name="AssessmentNotificationDelivery",
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
                ("channel_id", models.BigIntegerField(verbose_name="通知渠道ID")),
                (
                    "channel_name",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=128,
                        verbose_name="通知渠道名称快照",
                    ),
                ),
                (
                    "channel_type",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=64,
                        verbose_name="通知渠道类型快照",
                    ),
                ),
                ("receivers", models.JSONField(default=list, verbose_name="接收人快照")),
                ("team_id", models.BigIntegerField(verbose_name="通知组织ID快照")),
                ("title", models.CharField(max_length=255, verbose_name="通知标题")),
                ("content", models.TextField(verbose_name="通知正文")),
                ("summary", models.JSONField(default=dict, verbose_name="评估汇总快照")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "待投递"),
                            ("sending", "投递中"),
                            ("retry", "待重试"),
                            ("delivered", "已投递"),
                            ("failed", "投递失败"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                        verbose_name="投递状态",
                    ),
                ),
                (
                    "attempts",
                    models.PositiveSmallIntegerField(
                        default=0,
                        verbose_name="已尝试次数",
                    ),
                ),
                (
                    "max_attempts",
                    models.PositiveSmallIntegerField(
                        default=3,
                        verbose_name="最大尝试次数",
                    ),
                ),
                (
                    "next_retry_at",
                    models.DateTimeField(
                        blank=True,
                        db_index=True,
                        null=True,
                        verbose_name="下次重试时间",
                    ),
                ),
                (
                    "delivered_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="投递完成时间",
                    ),
                ),
                (
                    "last_error",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="最后一次错误",
                    ),
                ),
                (
                    "claim_token",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        max_length=32,
                        verbose_name="投递栅栏令牌",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_deliveries",
                        to="patch_mgmt.governancetask",
                        verbose_name="周期评估任务",
                    ),
                ),
            ],
            options={
                "verbose_name": "周期评估通知投递",
                "verbose_name_plural": "周期评估通知投递",
                "db_table": "patch_assessment_notification_delivery",
            },
        ),
        migrations.AddConstraint(
            model_name="assessmentnotificationdelivery",
            constraint=models.UniqueConstraint(
                fields=("task", "channel_id"),
                name="patch_assess_notice_task_channel_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="assessmentnotificationdelivery",
            index=models.Index(
                fields=["status", "next_retry_at"],
                name="patch_assess_notice_retry_idx",
            ),
        ),
    ]
