from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("patch_mgmt", "0005_add_requirement_assessment_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="linuxpatchdetail",
            name="packages",
            field=models.JSONField(default=list, verbose_name="关联软件包列表"),
        ),
    ]
