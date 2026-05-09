"""Add scheduled_task foreign key to JobExecution for concurrency policy enforcement."""

import django.db.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("job_mgmt", "0003_jobexecution_callback_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobexecution",
            name="scheduled_task",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="job_mgmt.scheduledtask",
                verbose_name="关联定时任务",
            ),
        ),
    ]
