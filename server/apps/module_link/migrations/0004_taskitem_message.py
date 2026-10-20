from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("module_link", "0003_monitorcmdbtask"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorlinktaskitem",
            name="message",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="monitorcmdbtaskitem",
            name="message",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
    ]
