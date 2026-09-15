from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0044_encrypt_installer_passwords"),
    ]

    operations = [
        migrations.AddField(
            model_name="collector",
            name="imported_package_version",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="已导入探针包版本"),
        ),
        migrations.AddField(
            model_name="packageversion",
            name="sha256",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="文件SHA256"),
        ),
    ]
