from django.db import migrations


def backfill_container_node_cpu_architecture(apps, schema_editor):
    Node = apps.get_model("node_mgmt", "Node")
    Node.objects.filter(node_type="container", cpu_architecture="").update(cpu_architecture="x86_64")


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0034_architecture_defaults_to_x86"),
    ]

    operations = [
        migrations.RunPython(backfill_container_node_cpu_architecture, migrations.RunPython.noop),
    ]
