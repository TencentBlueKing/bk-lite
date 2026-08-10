from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("monitor", "0046_monitorpolicy_threshold_unit"),
    ]

    operations = [
        migrations.CreateModel(
            name="MonitorViewColumnPreference",
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
                    "field_keys",
                    models.JSONField(default=list, verbose_name="展示字段及顺序"),
                ),
                (
                    "monitor_object",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="view_column_preferences",
                        to="monitor.monitorobject",
                        verbose_name="监控对象",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="monitor_view_column_preferences",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="用户",
                    ),
                ),
            ],
            options={
                "verbose_name": "监控视图个人列配置",
                "verbose_name_plural": "监控视图个人列配置",
            },
        ),
        migrations.AddConstraint(
            model_name="monitorviewcolumnpreference",
            constraint=models.UniqueConstraint(
                fields=("user", "monitor_object"),
                name="uniq_monitor_view_columns_user_object",
            ),
        ),
    ]
