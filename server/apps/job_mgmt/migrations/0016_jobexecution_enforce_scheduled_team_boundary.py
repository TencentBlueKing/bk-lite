from django.db import migrations, models


def mark_existing_scheduled_executions(apps, schema_editor):
    job_execution = apps.get_model("job_mgmt", "JobExecution")
    job_execution.objects.filter(scheduled_task_id__isnull=False).update(
        enforce_scheduled_team_boundary=True
    )


def unmark_existing_scheduled_executions(apps, schema_editor):
    job_execution = apps.get_model("job_mgmt", "JobExecution")
    job_execution.objects.filter(enforce_scheduled_team_boundary=True).update(
        enforce_scheduled_team_boundary=False
    )


class Migration(migrations.Migration):
    dependencies = [
        ("job_mgmt", "0015_jobexecution_callback_identity"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobexecution",
            name="enforce_scheduled_team_boundary",
            field=models.BooleanField(default=False, verbose_name="执行时强制定时任务团队边界"),
        ),
        migrations.RunPython(mark_existing_scheduled_executions, unmark_existing_scheduled_executions),
    ]
