from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0049_scan_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanfamilyrun",
            name="progress_hosts",
            field=models.JSONField(
                default=list,
                help_text="已计入进度的主机（含失败/不可达）；清单仅保留 success",
            ),
        ),
    ]
