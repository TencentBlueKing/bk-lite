from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("itsm", "0019_node_action_options")]

    operations = [
        migrations.AddField(
            model_name="ticketsurvey",
            name="answers",
            field=models.JSONField(default=list),
        ),
    ]
