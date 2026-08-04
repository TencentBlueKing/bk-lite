from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("monitor", "0055_monitorviewcolumnpreference_fixed_field_keys")]

    operations = [
        migrations.AlterField(
            model_name="monitorobject",
            name="cleanup_timeout_unit",
            field=models.CharField(
                choices=[("minute", "Minute"), ("hour", "Hour"), ("day", "Day")],
                default="day",
                max_length=10,
                verbose_name="自动发现资产超时清理时长单位",
            ),
        ),
    ]
