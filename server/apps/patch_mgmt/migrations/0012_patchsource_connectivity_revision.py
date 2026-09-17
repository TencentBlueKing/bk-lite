from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("patch_mgmt", "0011_scan_setting_timezone"),
    ]

    operations = [
        migrations.AddField(
            model_name="patchsource",
            name="connectivity_revision",
            field=models.IntegerField(default=0, verbose_name="连通性配置版本"),
        ),
    ]
