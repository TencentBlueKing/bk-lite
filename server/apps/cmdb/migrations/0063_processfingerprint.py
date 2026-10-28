from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0062_portfingerprint_enabled"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessFingerprint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("target_type", models.CharField(help_text="CMDB 模型 ID", max_length=128)),
                ("linux_process", models.CharField(blank=True, default="", help_text="Linux 进程名或命令行正则", max_length=256)),
                ("windows_image", models.CharField(blank=True, default="", help_text="Windows 映像名或服务名", max_length=256)),
                ("built_in", models.BooleanField(default=False, verbose_name="是否内置")),
                ("enabled", models.BooleanField(default=True, verbose_name="是否启用")),
            ],
            options={
                "verbose_name": "进程指纹",
                "verbose_name_plural": "进程指纹",
                "unique_together": {("target_type", "linux_process", "windows_image")},
            },
        ),
    ]
