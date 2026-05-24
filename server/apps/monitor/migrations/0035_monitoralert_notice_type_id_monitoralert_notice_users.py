from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0034_monitorplugin_node_selector"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitoralert",
            name="notice_type_id",
            field=models.IntegerField(default=0, verbose_name="通知方式ID"),
        ),
        migrations.AddField(
            model_name="monitoralert",
            name="notice_users",
            field=models.JSONField(default=list, verbose_name="通知人"),
        ),
    ]
