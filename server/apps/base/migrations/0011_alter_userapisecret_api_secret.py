from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0010_hash_user_api_secret"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userapisecret",
            name="api_secret",
            field=models.CharField(db_index=True, max_length=80),
        ),
    ]
