import django.utils.timezone
from django.db import migrations, models

import apps.rum.models


class Migration(migrations.Migration):
    dependencies = [
        ("rum", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RumApplication",
            fields=[
                ("name", models.CharField(max_length=128, primary_key=True, serialize=False)),
                ("tenant_id", models.CharField(max_length=128)),
                ("org_id", models.CharField(max_length=128)),
                ("enabled", models.BooleanField(default=True)),
                ("revision", models.BigIntegerField(default=0)),
                ("requests_per_minute", models.BigIntegerField(default=0)),
                ("compressed_bytes_per_minute", models.BigIntegerField(default=0)),
                ("decompressed_bytes_per_minute", models.BigIntegerField(default=0)),
                ("events_per_minute", models.BigIntegerField(default=0)),
                ("created_by", models.CharField(blank=True, default="", max_length=128)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "rum_applications"},
        ),
        migrations.CreateModel(
            name="RumApplicationOrigin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("application", models.CharField(db_index=True, max_length=128)),
                ("origin", models.CharField(max_length=256)),
            ],
            options={"db_table": "rum_application_origins"},
        ),
        migrations.AddConstraint(
            model_name="rumapplicationorigin",
            constraint=models.UniqueConstraint(fields=("application", "origin"), name="rum_app_origin_uniq"),
        ),
        migrations.CreateModel(
            name="RumApplicationKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("application", models.CharField(db_index=True, max_length=128)),
                ("key_cipher", models.TextField()),
                ("key_digest", models.CharField(max_length=64, unique=True)),
                ("status", models.CharField(default="active", max_length=16)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={"db_table": "rum_application_keys"},
        ),
        migrations.CreateModel(
            name="RumProjectionOutbox",
            fields=[
                ("id", models.CharField(default=apps.rum.models.new_id, editable=False, max_length=36, primary_key=True, serialize=False)),
                ("kind", models.CharField(max_length=32)),
                ("application", models.CharField(db_index=True, max_length=128)),
                ("revision", models.BigIntegerField(default=0)),
                ("payload_json", models.JSONField(default=dict)),
                ("status", models.CharField(db_index=True, default="pending", max_length=16)),
                ("attempts", models.IntegerField(default=0)),
                ("last_error_type", models.CharField(blank=True, default="", max_length=128)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "rum_projection_outbox"},
        ),
        migrations.AddConstraint(
            model_name="rumprojectionoutbox",
            constraint=models.UniqueConstraint(
                condition=models.Q(("kind", "application")),
                fields=("application", "revision"),
                name="rum_outbox_app_rev_uniq",
            ),
        ),
    ]
