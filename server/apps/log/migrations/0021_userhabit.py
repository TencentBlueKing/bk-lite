from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("log", "0020_cross_database_extractor_guards"),
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
                name="uniq_log_user_habit_key",
            ),
        ),
    ]
