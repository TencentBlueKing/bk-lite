from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("cmdb", "0035_cmdb_operation_outbox")]

    operations = [
        migrations.AddField(
            model_name="changerecord",
            name="operation_event_id",
            field=models.UUIDField(blank=True, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="cmdboperationoutbox",
            name="next_attempt_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
