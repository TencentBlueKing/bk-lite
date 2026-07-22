from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cmdb", "0039_node_mgmt_sync_reconciliation")]

    operations = [
        migrations.AddField(
            model_name="collectmodels",
            name="execution_claim_token",
            field=models.CharField(
                blank=True,
                editable=False,
                help_text="采集执行内部领取令牌",
                max_length=128,
                null=True,
            ),
        ),
    ]
