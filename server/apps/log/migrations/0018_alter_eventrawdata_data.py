import apps.core.fields.s3_json_field
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0017_systemvectorconfigstate_systemvectortoken_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="eventrawdata",
            name="data",
            field=apps.core.fields.s3_json_field.S3JSONField(
                bucket_name="log-alert-raw-data",
                compressed=True,
                delete_previous_on_update=True,
                help_text="自动压缩并存储到 MinIO/S3",
                max_length=500,
                upload_to=apps.core.fields.s3_json_field.s3_json_upload_path,
                verbose_name="原始数据",
            ),
        ),
    ]
