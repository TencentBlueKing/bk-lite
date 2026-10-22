from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0083_alter_policygroupmembership_state"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="policygrouprule",
            name="push_alert_center",
        ),
    ]
