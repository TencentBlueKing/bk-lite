from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0035_actionrule_auto_execute"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="owners",
            field=models.JSONField(blank=True, default=list, help_text="告警责任人，成员事件责任人并集"),
        ),
    ]
