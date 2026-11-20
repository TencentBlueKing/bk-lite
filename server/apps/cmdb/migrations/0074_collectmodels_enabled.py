from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0073_merge_ci_context_and_repair"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectmodels",
            name="enabled",
            field=models.BooleanField(default=True, help_text="是否启用采集。关闭后保留任务配置，不再下发节点采集配置"),
        ),
    ]
