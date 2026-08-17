from django.db import migrations, models


def zero_network_topology_refresh_interval(apps, schema_editor):
    NetworkTopology = apps.get_model("operation_analysis", "NetworkTopology")
    NetworkTopology.objects.all().update(refresh_interval=0)


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0027_merge_20260813_0959"),
    ]

    operations = [
        migrations.AddField(
            model_name="dashboard",
            name="refresh_interval",
            field=models.PositiveIntegerField(default=0, verbose_name="刷新周期"),
        ),
        migrations.AddField(
            model_name="topology",
            name="refresh_interval",
            field=models.PositiveIntegerField(default=0, verbose_name="刷新周期"),
        ),
        migrations.AddField(
            model_name="screen",
            name="refresh_interval",
            field=models.PositiveIntegerField(default=0, verbose_name="刷新周期"),
        ),
        migrations.AlterField(
            model_name="networktopology",
            name="refresh_interval",
            field=models.PositiveIntegerField(default=0, verbose_name="刷新周期"),
        ),
        migrations.RunPython(zero_network_topology_refresh_interval, migrations.RunPython.noop),
    ]
