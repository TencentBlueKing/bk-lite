from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0049_credential_vault"),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemAPIToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("system_id", models.CharField(db_index=True, max_length=32)),
                ("name", models.CharField(default="", max_length=128)),
                ("secret_hash", models.CharField(db_index=True, max_length=80)),
                ("scope", models.JSONField(blank=True, null=True)),
                ("enabled", models.BooleanField(default=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.CharField(default="", max_length=32)),
                ("created_by_domain", models.CharField(default="domain.com", max_length=100)),
            ],
        ),
        migrations.AddConstraint(
            model_name="systemapitoken",
            constraint=models.UniqueConstraint(
                fields=("system_id", "name"),
                name="uniq_systemapitoken_system_id_name",
            ),
        ),
    ]
