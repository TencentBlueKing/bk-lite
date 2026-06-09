from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0036_notice_type_id_to_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorinstance",
            name="cloud_region_id",
            field=models.IntegerField(blank=True, db_index=True, null=True, verbose_name="云区域ID"),
        ),
        migrations.AddField(
            model_name="monitorinstance",
            name="ip",
            field=models.GenericIPAddressField(blank=True, null=True, verbose_name="接入IP"),
        ),
        migrations.AddField(
            model_name="monitorinstance",
            name="fallback_sampling_rate",
            field=models.IntegerField(default=1000, verbose_name="兜底采样率"),
        ),
        migrations.AddField(
            model_name="monitorinstance",
            name="enabled_protocols",
            field=models.JSONField(default=list, verbose_name="已启用的Flow协议"),
        ),
    ]
