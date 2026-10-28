from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0035_elasticsearch_source_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="excelmaterializationslot",
            name="processing_started_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="开始处理时间"),
        ),
    ]
