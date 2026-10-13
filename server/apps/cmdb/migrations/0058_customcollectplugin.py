from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0057_async_transfer_tasks"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomCollectPlugin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("name", models.CharField(help_text="显示名", max_length=128)),
                ("plugin_id", models.CharField(help_text="全局唯一标识，创建后不可改", max_length=48, unique=True)),
                ("model_id", models.CharField(help_text="目标 CMDB 模型", max_length=64)),
                ("os_type", models.CharField(help_text="linux 或 windows，创建后不可改", max_length=16)),
                ("shell", models.CharField(help_text="脚本解释器", max_length=16)),
                ("content", models.TextField(help_text="脚本正文")),
                ("content_checksum", models.CharField(help_text="脚本 sha256", max_length=80)),
                ("version", models.PositiveIntegerField(default=1, help_text="脚本版本，正文变更时递增")),
                ("desc", models.CharField(blank=True, default="", help_text="描述", max_length=512)),
                ("team", models.JSONField(default=list, help_text="关联组织")),
            ],
            options={
                "verbose_name": "自定义采集插件",
            },
        ),
    ]
