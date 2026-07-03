import hashlib

from django.db import migrations, models


HASH_PREFIX = "sha256$"


def hash_existing_api_secrets(apps, schema_editor):
    UserAPISecret = apps.get_model("base", "UserAPISecret")
    for secret in UserAPISecret.objects.exclude(api_secret__startswith=HASH_PREFIX).iterator():
        if not secret.api_secret:
            continue
        secret.api_secret = f"{HASH_PREFIX}{hashlib.sha256(secret.api_secret.encode()).hexdigest()}"
        secret.save(update_fields=["api_secret"])


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0009_alter_userapisecret_unique_together"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userapisecret",
            name="api_secret",
            field=models.CharField(max_length=80),
        ),
        migrations.RunPython(hash_existing_api_secrets, migrations.RunPython.noop),
    ]
