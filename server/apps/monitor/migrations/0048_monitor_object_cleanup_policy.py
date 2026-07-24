from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("monitor", "0047_monitorviewcolumnpreference")]

    operations = [
        migrations.AddField(
            model_name="monitorobject",
            name="is_builtin",
            field=models.BooleanField(db_index=True, default=False, verbose_name="是否为内置对象"),
        ),
        migrations.AddField(
            model_name="monitorobject",
            name="cleanup_policy",
            field=models.CharField(
                choices=[("no_cleanup", "No cleanup"), ("timeout", "Timeout cleanup")],
                default="no_cleanup",
                max_length=20,
                verbose_name="自动发现资产清理策略",
            ),
        ),
        migrations.AddField(
            model_name="monitorobject",
            name="cleanup_timeout_days",
            field=models.PositiveSmallIntegerField(
                default=1,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(365)],
                verbose_name="自动发现资产超时清理天数",
            ),
        ),
        migrations.AddField(
            model_name="monitorobject",
            name="cleanup_policy_effective_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="清理策略生效时间"),
        ),
        migrations.AddField(
            model_name="monitorobject",
            name="last_discovery_success_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="最近一次自动发现查询成功时间"),
        ),
        migrations.AddField(
            model_name="monitorinstance",
            name="last_seen_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="自动发现最近上报时间"),
        ),
        migrations.AddField(
            model_name="monitorinstance",
            name="missing_duration_seconds",
            field=models.PositiveIntegerField(default=0, verbose_name="确认无上报累计时长"),
        ),
    ]
