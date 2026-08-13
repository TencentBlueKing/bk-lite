from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0042_controllertasknode_connectivity_observation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="controllertasknode",
            name="password",
            field=models.TextField(verbose_name="密码"),
        ),
    ]
