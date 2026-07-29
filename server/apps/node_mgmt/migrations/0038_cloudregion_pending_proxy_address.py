from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0036_controllertasknode_node_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="cloudregion",
            name="pending_proxy_address",
            field=models.CharField(
                blank=True,
                default=None,
                max_length=255,
                null=True,
                verbose_name="待生效代理地址",
            ),
        ),
        migrations.AddField(
            model_name="cloudregion",
            name="pending_proxy_address_created_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="代理地址变更发起时间",
            ),
        ),
    ]
