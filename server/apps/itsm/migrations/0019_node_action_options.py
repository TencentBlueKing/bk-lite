from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("itsm", "0018_handover_results")]

    operations = [
        migrations.AddField(
            model_name="handover",
            name="opinion",
            field=models.CharField(blank=True, default="", max_length=2000),
        ),
        migrations.AddField(
            model_name="tickettask",
            name="process_instance_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
