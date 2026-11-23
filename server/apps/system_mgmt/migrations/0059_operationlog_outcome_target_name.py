from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0058_channel_sms_voice_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="operationlog",
            name="failure_reason",
            field=models.TextField(blank=True, default="", verbose_name="Failure Reason"),
        ),
        migrations.AddField(
            model_name="operationlog",
            name="outcome",
            field=models.CharField(
                blank=True,
                choices=[
                    ("success", "Success"),
                    ("failure", "Failure"),
                    ("accepted", "Accepted"),
                    ("", "Unrecorded"),
                ],
                db_index=True,
                default="",
                max_length=16,
                verbose_name="Outcome",
            ),
        ),
        migrations.AddField(
            model_name="operationlog",
            name="target_name",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255, verbose_name="Target Name"),
        ),
    ]
