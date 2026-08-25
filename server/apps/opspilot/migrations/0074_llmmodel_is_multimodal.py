from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0073_skillchannel_unique_skill_type_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmmodel",
            name="is_multimodal",
            field=models.BooleanField(default=True, verbose_name="支持多模态"),
        ),
    ]
