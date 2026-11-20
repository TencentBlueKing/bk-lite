from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("workflow", "0005_workflowexecution_execution_team_id")]

    operations = [
        migrations.AddField(
            model_name="workflowexecution",
            name="locale",
            field=models.CharField(default="zh-Hans", editable=False, max_length=7),
        ),
    ]
