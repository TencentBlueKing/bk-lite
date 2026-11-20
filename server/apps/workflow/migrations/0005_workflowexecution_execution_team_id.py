from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("workflow", "0004_workflowexecution_caller_identity")]

    operations = [
        migrations.AddField(
            model_name="workflowexecution",
            name="execution_team_id",
            field=models.PositiveBigIntegerField(editable=False, null=True),
        ),
    ]
