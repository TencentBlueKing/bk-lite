from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0041_alter_controllertasknode_winrm_cert_validation"),
    ]

    operations = [
        migrations.AddField(
            model_name="controllertasknode",
            name="connectivity_observed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="节点提前回连时间"),
        ),
        migrations.AddField(
            model_name="controllertasknode",
            name="connectivity_observed_node_id",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="提前回连节点ID"),
        ),
    ]
