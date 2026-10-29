from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0036_alert_owners"),
    ]

    operations = [
        migrations.AddField(
            model_name="alertremindertask",
            name="generation",
            field=models.PositiveIntegerField(default=0, help_text="提醒计数归零后的代数，0 沿用旧幂等键"),
        ),
    ]
