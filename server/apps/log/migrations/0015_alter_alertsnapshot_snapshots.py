from django.db import migrations

import apps.core.fields.s3_json_field


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0014_alter_policy_collect_type_and_alert_collect_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alertsnapshot",
            name="snapshots",
            field=apps.core.fields.s3_json_field.S3JSONField(
                bucket_name="log-alert-raw-data",
                compressed=True,
                default=list,
                delete_previous_on_update=True,
                help_text="累积存储告警下所有事件的原始数据",
                max_length=500,
                upload_to=apps.core.fields.s3_json_field.s3_json_upload_path,
                verbose_name="快照数据集合",
            ),
        ),
    ]
