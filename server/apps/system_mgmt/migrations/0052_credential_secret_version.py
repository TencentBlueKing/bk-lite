from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0051_openapicalllog"),
    ]

    operations = [
        migrations.AddField(
            model_name="credential",
            name="secret_version",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
