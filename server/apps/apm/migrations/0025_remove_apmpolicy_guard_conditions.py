from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("apm", "0024_apmpolicy_baseline_days"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="apmpolicy",
            name="guard_conditions",
        ),
    ]
