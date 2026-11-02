from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0038_itsm_global_integration"),
    ]

    operations = [
        migrations.AddField(
            model_name="alertitsmticket",
            name="comment_event",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="alertitsmticket",
            name="comment_error",
            field=models.CharField(blank=True, max_length=256),
        ),
    ]
