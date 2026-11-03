from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0062_scan_family_run_progress"),
    ]

    operations = [
        migrations.AddField(
            model_name="portfingerprint",
            name="enabled",
            field=models.BooleanField(default=True, verbose_name="是否启用"),
        ),
        migrations.AlterModelOptions(
            name="portfingerprint",
            options={"verbose_name": "端口指纹", "verbose_name_plural": "端口指纹"},
        ),
    ]
