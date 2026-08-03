from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("apm", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="apmingestsource",
            name="last_missing_instance_identity_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        )
    ]
