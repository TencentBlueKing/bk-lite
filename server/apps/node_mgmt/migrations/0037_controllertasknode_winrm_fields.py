from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0036_controllertasknode_node_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="controllertasknode",
            name="winrm_scheme",
            field=models.CharField(blank=True, default="https", max_length=16, verbose_name="WinRM协议"),
        ),
        migrations.AddField(
            model_name="controllertasknode",
            name="winrm_transport",
            field=models.CharField(blank=True, default="ntlm", max_length=32, verbose_name="WinRM认证方式"),
        ),
        migrations.AddField(
            model_name="controllertasknode",
            name="winrm_cert_validation",
            field=models.BooleanField(default=True, verbose_name="WinRM证书校验"),
        ),
    ]
