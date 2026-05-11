from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("system_mgmt", "0029_init_portal_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="phone",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
    ]
