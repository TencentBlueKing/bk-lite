from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("workflow", "0003_execution_reconcile_backoff")]

    operations = [
        migrations.AddField(
            model_name="workflowexecution",
            name="caller_identity",
            field=models.JSONField(blank=True, editable=False, null=True),
        ),
    ]
