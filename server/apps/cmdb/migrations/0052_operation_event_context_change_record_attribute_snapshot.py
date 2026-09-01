from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0051_sceneview"),
    ]

    operations = [
        migrations.AddField(
            model_name="cmdboperation",
            name="event_context",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="changerecord",
            name="attribute_snapshot",
            field=models.JSONField(blank=True, default=dict, verbose_name="变更时属性定义快照"),
        ),
    ]
