from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0068_monitorevent_claim_assign_actions"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorplugin",
            name="pack_version",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="导入的探针包版本"),
        ),
        migrations.AddField(
            model_name="monitorplugin",
            name="pack_content_sha256",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="导入包内容哈希"),
        ),
    ]
