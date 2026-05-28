from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0015_incident_collaborators_incidentupdate"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="dimensions",
            field=models.JSONField(default=dict, help_text="聚合维度键值对"),
        ),
    ]
