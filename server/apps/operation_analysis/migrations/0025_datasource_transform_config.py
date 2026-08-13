from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0024_data_connection"),
    ]

    operations = [
        migrations.AddField(
            model_name="datasourceapimodel",
            name="transform_config",
            field=models.JSONField(blank=True, default=dict, verbose_name="转换配置"),
        ),
    ]
