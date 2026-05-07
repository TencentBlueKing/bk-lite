from django.db import migrations, models


def backfill_x86_defaults(apps, schema_editor):
    Controller = apps.get_model("node_mgmt", "Controller")
    Collector = apps.get_model("node_mgmt", "Collector")
    PackageVersion = apps.get_model("node_mgmt", "PackageVersion")

    Controller.objects.filter(cpu_architecture="").update(cpu_architecture="x86_64")
    Collector.objects.filter(cpu_architecture="").update(cpu_architecture="x86_64")
    PackageVersion.objects.filter(cpu_architecture="").update(cpu_architecture="x86_64")


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0033_collector_architecture_loader"),
    ]

    operations = [
        migrations.RunPython(backfill_x86_defaults, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="controller",
            name="cpu_architecture",
            field=models.CharField(blank=True, default="x86_64", max_length=20, verbose_name="CPU架构"),
        ),
        migrations.AlterField(
            model_name="collector",
            name="cpu_architecture",
            field=models.CharField(blank=True, default="x86_64", max_length=20, verbose_name="CPU架构"),
        ),
        migrations.AlterField(
            model_name="packageversion",
            name="cpu_architecture",
            field=models.CharField(blank=True, db_index=True, default="x86_64", max_length=20, verbose_name="CPU架构"),
        ),
    ]
