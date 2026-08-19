from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_column_preferences(apps, schema_editor):
    old_model = apps.get_model("monitor", "MonitorViewColumnPreference")
    habit_model = apps.get_model("monitor", "UserHabit")
    alias = schema_editor.connection.alias
    for row in old_model.objects.using(alias).iterator():
        habit_model.objects.using(alias).update_or_create(
            user_id=row.user_id,
            habit_key=f"view.columnPreference.{row.monitor_object_id}",
            defaults={
                "habit_value": {
                    "field_keys": row.field_keys,
                    "fixed_field_keys": row.fixed_field_keys or [],
                }
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("monitor", "0061_monitoralertcenterdelivery"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserHabit",
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
                ("habit_key", models.CharField(max_length=100, verbose_name="习惯键")),
                (
                    "habit_value",
                    models.JSONField(default=dict, verbose_name="习惯值"),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(app_label)s_user_habits",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="用户",
                    ),
                ),
            ],
            options={
                "verbose_name": "用户习惯",
                "verbose_name_plural": "用户习惯",
            },
        ),
        migrations.AddConstraint(
            model_name="userhabit",
            constraint=models.UniqueConstraint(
                fields=("user", "habit_key"),
                name="uniq_monitor_user_habit_key",
            ),
        ),
        migrations.RunPython(copy_column_preferences, migrations.RunPython.noop),
        migrations.DeleteModel(name="MonitorViewColumnPreference"),
    ]
