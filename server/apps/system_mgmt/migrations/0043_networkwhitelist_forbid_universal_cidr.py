from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0042_user_permission_version"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="networkwhitelist",
            constraint=models.CheckConstraint(
                check=~models.Q(network__in=("0.0.0.0/0", "::/0")),
                name="network_whitelist_forbid_universal_cidr",
            ),
        ),
    ]
