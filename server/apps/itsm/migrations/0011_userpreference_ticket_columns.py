from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("itsm", "0010_ticketattachment_comment")]
    operations = [
        migrations.AddField(
            model_name="userpreference",
            name="ticket_columns",
            field=models.JSONField(default=list),
        ),
    ]
