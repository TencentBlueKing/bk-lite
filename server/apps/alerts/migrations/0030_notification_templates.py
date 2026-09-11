import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("alerts", "0029_alert_event_enrichment_meta")]

    operations = [
        migrations.CreateModel(
            name="NotificationTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("name", models.CharField(help_text="模板名称", max_length=100)),
                ("description", models.CharField(blank=True, default="", help_text="模板说明", max_length=500)),
                ("team", models.JSONField(default=list, help_text="关联组织")),
                ("scope_key", models.CharField(db_index=True, editable=False, help_text="组织范围唯一键", max_length=70)),
                (
                    "scope",
                    models.CharField(
                        choices=[("single_alert", "单告警"), ("unassigned_summary", "未分派汇总"), ("alert_operation", "告警操作")],
                        db_index=True,
                        default="single_alert",
                        max_length=32,
                    ),
                ),
                ("is_global", models.BooleanField(db_index=True, default=False, help_text="是否为全局模板")),
                ("builtin_key", models.CharField(blank=True, db_index=True, default="", help_text="内置模板稳定标识", max_length=64)),
                ("channel_id", models.PositiveBigIntegerField(blank=True, help_text="内置告警操作模板绑定的唯一通知渠道", null=True)),
                ("revision", models.PositiveIntegerField(default=1, help_text="乐观锁版本")),
            ],
            options={"db_table": "alerts_notification_template", "ordering": ["-updated_at", "-id"]},
        ),
        migrations.CreateModel(
            name="NotificationTemplateContent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel_type", models.CharField(help_text="通知渠道类型", max_length=30)),
                ("subject_template", models.CharField(blank=True, default="", help_text="标题模板", max_length=500)),
                ("body_template", models.TextField(help_text="正文模板")),
                (
                    "template",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contents", to="alerts.notificationtemplate"),
                ),
            ],
            options={"db_table": "alerts_notification_template_content", "ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="NotificationTemplateReference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_type", models.CharField(help_text="引用来源", max_length=32)),
                ("source_id", models.CharField(help_text="来源对象 ID", max_length=100)),
                ("scene", models.CharField(default="default", help_text="通知场景", max_length=32)),
                ("channel_id", models.IntegerField(blank=True, help_text="渠道 ID", null=True)),
                ("locator", models.CharField(blank=True, default="", help_text="来源内定位", max_length=200)),
                ("is_snapshot", models.BooleanField(default=False, help_text="是否为运行快照引用")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "template",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="references", to="alerts.notificationtemplate"),
                ),
            ],
            options={"db_table": "alerts_notification_template_reference"},
        ),
        migrations.AddConstraint(
            model_name="notificationtemplate",
            constraint=models.UniqueConstraint(fields=("scope_key", "scope", "name"), name="alerts_notification_template_scope_name_uniq"),
        ),
        migrations.AddConstraint(
            model_name="notificationtemplate",
            constraint=models.UniqueConstraint(
                condition=~models.Q(("builtin_key", "")), fields=("builtin_key",), name="alerts_notification_template_builtin_key_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="notificationtemplatecontent",
            constraint=models.UniqueConstraint(fields=("template", "channel_type"), name="alerts_notification_template_channel_uniq"),
        ),
        migrations.AddIndex(
            model_name="notificationtemplatereference", index=models.Index(fields=["source_type", "source_id"], name="alerts_tpl_ref_source_idx")
        ),
        migrations.AddConstraint(
            model_name="notificationtemplatereference",
            constraint=models.UniqueConstraint(
                fields=("template", "source_type", "source_id", "scene", "channel_id", "locator"), name="alerts_notification_template_reference_uniq"
            ),
        ),
    ]
