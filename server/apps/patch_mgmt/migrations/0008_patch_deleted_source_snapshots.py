from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("patch_mgmt", "0007_patchsource_sync_in_progress")]

    operations = [
        migrations.AddField(
            model_name="patch",
            name="deleted_source_snapshots",
            field=models.JSONField(default=list, verbose_name="已删除来源快照"),
        )
    ]
