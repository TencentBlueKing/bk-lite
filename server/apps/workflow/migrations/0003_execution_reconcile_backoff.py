from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workflow", "0002_async_callback"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowexecution",
            name="reconcile_attempts",
            field=models.PositiveIntegerField(default=0, verbose_name="无引擎 ID 对账尝试次数"),
        ),
        migrations.AddField(
            model_name="workflowexecution",
            name="reconcile_next_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="下次无引擎 ID 对账时间",
            ),
        ),
    ]
