from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0034_architecture_refresh_interval"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dataconnection",
            name="connection_type",
            field=models.CharField(
                choices=[
                    ("mysql", "MySQL"),
                    ("postgresql", "PostgreSQL"),
                    ("rest_api", "REST API"),
                    ("elasticsearch", "Elasticsearch"),
                ],
                max_length=32,
                verbose_name="连接类型",
            ),
        ),
        migrations.AlterField(
            model_name="datasourceapimodel",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("nats", "NATS"),
                    ("mysql", "MySQL"),
                    ("postgresql", "PostgreSQL"),
                    ("rest_api", "REST API"),
                    ("excel", "Excel"),
                    ("prometheus", "Prometheus"),
                    ("elasticsearch", "Elasticsearch"),
                ],
                default="nats",
                max_length=32,
                verbose_name="数据来源类型",
            ),
        ),
    ]
