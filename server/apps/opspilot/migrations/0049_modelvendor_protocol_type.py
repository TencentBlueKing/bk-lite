# Generated migration for adding protocol_type field to ModelVendor

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0048_llmskill_skill_params"),
    ]

    operations = [
        migrations.AddField(
            model_name="modelvendor",
            name="protocol_type",
            field=models.CharField(
                choices=[("openai", "OpenAI 兼容"), ("anthropic", "Anthropic 兼容")],
                default="openai",
                max_length=20,
                verbose_name="协议类型",
            ),
        ),
    ]
