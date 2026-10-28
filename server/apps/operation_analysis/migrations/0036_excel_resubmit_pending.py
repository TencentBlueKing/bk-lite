from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0035_elasticsearch_source_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="datasourceapimodel",
            name="excel_resubmit_pending",
            field=models.BooleanField(default=False, verbose_name="Excel 重算待投递"),
        ),
    ]
