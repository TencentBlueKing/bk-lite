import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("itsm", "0009_ticketstatus_description")]
    operations = [
        migrations.AddField(
            model_name="ticketattachment",
            name="comment",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="attachments", to="itsm.ticketcomment"
            ),
        )
    ]
