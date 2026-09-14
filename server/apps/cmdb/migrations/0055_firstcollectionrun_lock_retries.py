from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0054_first_collection_telegraf_oneshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="firstcollectionrun",
            name="lock_retries",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
