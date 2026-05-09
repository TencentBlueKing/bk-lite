from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("job_mgmt", "0004_jobexecution_scheduled_task"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobexecution",
            name="celery_task_id",
            field=models.CharField(blank=True, default="", max_length=256, verbose_name="Celery任务ID"),
        ),
    ]
