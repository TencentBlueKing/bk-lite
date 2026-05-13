from django.db import migrations

import apps.core.fields.s3_json_field


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0032_collectconfig_monitor_plugin_and_custom_pull_templates"),
    ]

    operations = [
        migrations.AlterField(
            model_name="monitoralertmetricsnapshot",
            name="snapshots",
            field=apps.core.fields.s3_json_field.S3JSONField(
                bucket_name="monitor-alert-raw-data",
                compressed=True,
                default=list,
                delete_previous_on_update=True,
                max_length=500,
                upload_to=apps.core.fields.s3_json_field.s3_json_upload_path,
                verbose_name="快照数据集合",
            ),
        ),
    ]
