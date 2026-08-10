from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0041_networkwhitelist_domain_build_in"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserPermissionVersion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("username", models.CharField(max_length=100)),
                (
                    "domain",
                    models.CharField(default="domain.com", max_length=100),
                ),
                ("version", models.PositiveBigIntegerField(default=0)),
            ],
            options={
                "unique_together": {("username", "domain")},
            },
        ),
    ]
