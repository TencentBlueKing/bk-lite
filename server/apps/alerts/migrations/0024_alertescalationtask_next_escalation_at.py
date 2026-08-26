from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0023_k8sinstalltoken"),
    ]

    operations = [
        migrations.AddField(
            model_name="alertescalationtask",
            name="next_escalation_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="下次升级检查时间；空值为待回填旧记录",
                null=True,
            ),
        ),
    ]
