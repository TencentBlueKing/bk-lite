from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("itsm", "0017_async_ticket_export")]

    operations = [
        migrations.AddField(
            model_name="handover",
            name="results",
            field=models.JSONField(default=list),
        ),
    ]
