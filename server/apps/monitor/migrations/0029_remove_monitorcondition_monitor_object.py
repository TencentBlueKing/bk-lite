from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0028_monitorcondition_monitor_object"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="monitorcondition",
            name="monitor_object",
        ),
    ]
