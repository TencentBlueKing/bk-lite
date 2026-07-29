from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0024_incidentimgroup_actor_fields_length"),
    ]

    operations = [
        migrations.AddField(model_name="incidentimgroup", name="delivery_lock_expires_at", field=models.DateTimeField(blank=True, null=True),),
        migrations.AddField(model_name="incidentimgroup", name="delivery_lock_token", field=models.CharField(blank=True, default="", max_length=36),),
    ]
