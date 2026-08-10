from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("patch_mgmt", "0006_linuxpatchdetail_packages")]

    operations = [
        migrations.AddField(
            model_name="patchsource",
            name="sync_in_progress",
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name="是否正在同步",
            ),
        )
    ]
