from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0008_userapisecret_domain"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="userapisecret",
            unique_together={("username", "domain", "team")},
        ),
    ]
