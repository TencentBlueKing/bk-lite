from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0083_user_webchat_preference"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmskill",
            name="run_model_call_limit",
            field=models.PositiveIntegerField(default=10, verbose_name="每步模型调用次数"),
        ),
    ]
