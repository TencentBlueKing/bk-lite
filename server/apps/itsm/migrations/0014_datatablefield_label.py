from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("itsm", "0013_integrations")]
    operations = [
        migrations.AddField(
            model_name="datatablefield",
            name="label",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
