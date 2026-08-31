from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0024_alertescalationtask_next_escalation_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="closed_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="自动关闭、手动关闭、自动恢复或接口关闭的时间",
                null=True,
                verbose_name="关闭时间",
            ),
        ),
    ]
