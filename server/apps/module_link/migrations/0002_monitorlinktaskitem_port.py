from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("module_link", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorlinktaskitem",
            name="port",
            field=models.CharField(default="", max_length=32),
        ),
    ]
