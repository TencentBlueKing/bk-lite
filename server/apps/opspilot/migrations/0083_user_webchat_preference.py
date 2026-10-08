from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0082_skillpackage_is_build_in"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserWebchatPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.CharField(db_index=True, max_length=36, unique=True, verbose_name="用户UUID")),
                (
                    "dock_width",
                    models.PositiveIntegerField(default=380, verbose_name="悬浮对话宽度"),
                ),
            ],
            options={
                "verbose_name": "用户悬浮对话偏好",
                "verbose_name_plural": "用户悬浮对话偏好",
                "db_table": "opspilot_user_webchat_preference",
            },
        ),
    ]
