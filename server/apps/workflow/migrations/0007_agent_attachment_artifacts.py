from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = (("workflow", "0006_workflowexecution_locale"),)

    operations = (
        migrations.AlterField(
            model_name="executionartifact",
            name="kind",
            field=models.CharField(
                choices=[("INSPECTION_REPORT", "巡检报告"), ("AGENT_ATTACHMENT", "智能体附件")],
                default="INSPECTION_REPORT",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="executionartifact",
            name="format",
            field=models.CharField(max_length=8),
        ),
    )
