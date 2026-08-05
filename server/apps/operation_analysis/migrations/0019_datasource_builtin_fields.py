from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0018_dashboardsharelink_resource_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="datasourceapimodel",
            name="is_build_in",
            field=models.BooleanField(db_index=True, default=False, verbose_name="是否内置"),
        ),
        migrations.AddField(
            model_name="datasourceapimodel",
            name="build_in_key",
            field=models.CharField(blank=True, max_length=512, null=True, unique=True, verbose_name="内置配置稳定键"),
        ),
    ]
