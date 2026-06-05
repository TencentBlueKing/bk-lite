# Generated migration for adding storage_type and storage_config to MemorySpace model

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0051_memory_organization_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="memoryspace",
            name="storage_type",
            field=models.CharField(
                choices=[
                    ("local", "本地存储"),
                    ("mem0", "Mem0"),
                    ("zep", "Zep"),
                    ("custom", "自定义 API"),
                ],
                default="local",
                max_length=20,
                verbose_name="存储类型",
            ),
        ),
        migrations.AddField(
            model_name="memoryspace",
            name="storage_config",
            field=models.JSONField(blank=True, default=dict, verbose_name="存储配置"),
        ),
    ]
