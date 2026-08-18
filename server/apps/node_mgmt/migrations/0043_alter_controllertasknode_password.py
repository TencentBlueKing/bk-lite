from django.db import migrations, models


def widen_password_column(apps, schema_editor):
    controller_task_node = apps.get_model("node_mgmt", "ControllerTaskNode")
    old_field = controller_task_node._meta.get_field("password")
    new_field = models.TextField(verbose_name="密码")
    new_field.set_attributes_from_name("password")
    new_field.model = controller_task_node
    schema_editor.alter_field(controller_task_node, old_field, new_field)


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0042_controllertasknode_connectivity_observation"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    widen_password_column,
                    reverse_code=migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="controllertasknode",
                    name="password",
                    field=models.TextField(verbose_name="密码"),
                ),
            ],
        ),
    ]
