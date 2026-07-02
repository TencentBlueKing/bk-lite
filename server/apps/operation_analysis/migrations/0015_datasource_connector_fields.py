from django.db import migrations, models
from django.db.models import JSONField


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0014_screen_report"),
    ]

    operations = [
        migrations.AlterField(
            model_name="datasourceapimodel",
            name="rest_api",
            field=models.CharField(blank=True, max_length=255, verbose_name="REST API URL"),
        ),
        migrations.AddField(
            model_name="datasourceapimodel",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("nats", "NATS"),
                    ("mysql", "MySQL"),
                    ("postgresql", "PostgreSQL"),
                    ("rest_api", "REST API"),
                    ("excel", "Excel"),
                ],
                default="nats",
                max_length=32,
                verbose_name="数据来源类型",
            ),
        ),
        migrations.AddField(
            model_name="datasourceapimodel",
            name="connection_config",
            field=JSONField(blank=True, default=dict, verbose_name="连接配置"),
        ),
        migrations.AddField(
            model_name="datasourceapimodel",
            name="query_config",
            field=JSONField(blank=True, default=dict, verbose_name="取数配置"),
        ),
    ]
