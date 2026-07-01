from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0060_alter_skillpackage_created_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="memorywritecache",
            name="processing_started_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="处理开始时间"),
        ),
    ]
