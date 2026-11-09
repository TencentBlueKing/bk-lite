import django_minio_backend.models
from django.db import migrations, models

import apps.patch_mgmt.models.scan_setting


class Migration(migrations.Migration):
    dependencies = [
        ("patch_mgmt", "0013_windowspatchdetail_package_dotnet_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="scansetting",
            name="offline_catalog_enabled",
            field=models.BooleanField(default=False, verbose_name="是否启用离线目录"),
        ),
        migrations.AddField(
            model_name="scansetting",
            name="offline_catalog_file",
            field=models.FileField(
                blank=True,
                null=True,
                storage=django_minio_backend.models.MinioBackend(bucket_name="patch-mgmt-packages"),
                upload_to=apps.patch_mgmt.models.scan_setting.offline_catalog_upload_path,
                verbose_name="离线目录文件",
            ),
        ),
        migrations.AddField(
            model_name="scansetting",
            name="offline_catalog_filename",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="离线目录文件名"),
        ),
        migrations.AddField(
            model_name="scansetting",
            name="offline_catalog_sha256",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="离线目录 SHA256"),
        ),
        migrations.AddField(
            model_name="scansetting",
            name="offline_catalog_size",
            field=models.BigIntegerField(default=0, verbose_name="离线目录大小"),
        ),
        migrations.AddField(
            model_name="scansetting",
            name="offline_catalog_uploaded_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="离线目录上传时间"),
        ),
    ]
