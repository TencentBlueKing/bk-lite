from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0037_alertremindertask_generation"),
    ]

    operations = [
        migrations.AddField(
            model_name="alertescalationtask",
            name="cycle",
            field=models.PositiveIntegerField(default=0, help_text="升级周期；新建为 0，改派重置时加 1"),
        ),
    ]
