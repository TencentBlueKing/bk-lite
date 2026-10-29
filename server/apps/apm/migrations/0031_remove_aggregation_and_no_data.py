from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("apm", "0030_apmpolicy_slo_burn"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="apmpolicy",
            name="aggregation",
        ),
        migrations.RemoveField(
            model_name="apmpolicy",
            name="no_data_after",
        ),
        migrations.RemoveField(
            model_name="apmpolicy",
            name="no_data_alert_name",
        ),
        migrations.RemoveField(
            model_name="apmpolicy",
            name="no_data_severity",
        ),
        migrations.RemoveField(
            model_name="apmalertmetricsnapshot",
            name="aggregation",
        ),
    ]
