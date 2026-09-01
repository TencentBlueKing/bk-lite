from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0074_llmmodel_is_multimodal"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmmodel",
            name="context_window_tokens",
            field=models.PositiveIntegerField(default=200000, verbose_name="上下文窗口(token)"),
        ),
    ]
