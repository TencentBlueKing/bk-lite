from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0029_collectoractiontask_collectoractiontasknode"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="collectoractiontask",
            index=models.Index(
                fields=["status"],
                name="nm_action_task_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="collectoractiontasknode",
            index=models.Index(
                fields=["node", "status"],
                name="nm_action_node_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="collectoractiontasknode",
            index=models.Index(
                fields=["task", "status"],
                name="nm_action_tasknode_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="controllertask",
            index=models.Index(
                fields=["type", "status"],
                name="nm_ctrl_task_type_st_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="controllertasknode",
            index=models.Index(
                fields=["ip", "status"],
                name="nm_ctrl_node_ip_st_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="controllertasknode",
            index=models.Index(
                fields=["task", "status"],
                name="nm_ctrl_tasknode_st_idx",
            ),
        ),
    ]
