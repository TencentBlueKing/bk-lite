from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0046_alter_configfileversion_instance_id_help_text"),
    ]

    operations = [
        migrations.AlterField(
            model_name="nodemgmtsyncconfig",
            name="auto_sync_enabled",
            field=models.BooleanField(default=True, verbose_name="是否自动同步"),
        ),
    ]
