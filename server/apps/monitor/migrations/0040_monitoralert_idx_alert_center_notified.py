from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0039_monitoralert_alert_center_fields"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="monitoralert",
            index=models.Index(
                fields=["alert_center_notified", "status"],
                name="idx_alert_center_notified",
            ),
        ),
    ]
