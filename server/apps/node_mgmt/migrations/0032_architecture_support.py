from django.db import migrations, models


def backfill_architecture_fields(apps, schema_editor):
    Node = apps.get_model("node_mgmt", "Node")
    Controller = apps.get_model("node_mgmt", "Controller")
    PackageVersion = apps.get_model("node_mgmt", "PackageVersion")

    Controller.objects.filter(cpu_architecture="").update(cpu_architecture="x86_64")
    PackageVersion.objects.filter(cpu_architecture="").update(cpu_architecture="x86_64")
    Node.objects.filter(cpu_architecture__isnull=True).update(cpu_architecture="")


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0031_backfill_default_cloud_region_service_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="controller",
            name="cpu_architecture",
            field=models.CharField(blank=True, default="", max_length=20, verbose_name="CPU架构"),
        ),
        migrations.AddField(
            model_name="node",
            name="cpu_architecture",
            field=models.CharField(blank=True, default="", max_length=20, verbose_name="CPU架构"),
        ),
        migrations.AddField(
            model_name="packageversion",
            name="cpu_architecture",
            field=models.CharField(blank=True, db_index=True, default="", max_length=20, verbose_name="CPU架构"),
        ),
        migrations.AddField(
            model_name="controllertasknode",
            name="cpu_architecture",
            field=models.CharField(blank=True, default="", max_length=20, verbose_name="CPU架构"),
        ),
        migrations.AddField(
            model_name="controllertasknode",
            name="resolved_package_version_id",
            field=models.IntegerField(default=0, verbose_name="解析后的控制器版本"),
        ),
        migrations.RunPython(backfill_architecture_fields, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name="controller",
            unique_together={("os", "cpu_architecture", "name")},
        ),
        migrations.AlterUniqueTogether(
            name="packageversion",
            unique_together={("os", "cpu_architecture", "object", "version")},
        ),
    ]
