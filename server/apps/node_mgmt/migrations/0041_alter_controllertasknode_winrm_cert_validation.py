from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0040_node_module_linkage_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="controllertasknode",
            name="winrm_cert_validation",
            field=models.BooleanField(default=False, verbose_name="WinRM证书校验"),
        ),
    ]
