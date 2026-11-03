from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0036_excel_resubmit_pending"),
    ]

    operations = [
        migrations.AddField(
            model_name="excelmaterializationslot",
            name="processing_started_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="开始处理时间"),
        ),
    ]
