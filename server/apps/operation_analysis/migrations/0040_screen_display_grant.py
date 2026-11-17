import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0039_canvas_carousel"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScreenDisplayGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("status", models.CharField(choices=[("active", "有效"), ("paused", "已停用")], default="active", max_length=16)),
                ("duration_days", models.PositiveSmallIntegerField()),
                ("expires_at", models.DateTimeField()),
                ("tenant_domain", models.CharField(max_length=100)),
                ("space_id", models.PositiveBigIntegerField()),
                ("sharer_username", models.CharField(max_length=100)),
                ("sharer_domain", models.CharField(max_length=100)),
                ("last_access_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "screen",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="display_grant",
                        to="operation_analysis.screen",
                    ),
                ),
            ],
            options={
                "db_table": "operation_analysis_screen_display_grant",
            },
        ),
        migrations.CreateModel(
            name="ScreenDisplaySession",
            fields=[
                ("session_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "grant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessions",
                        to="operation_analysis.screendisplaygrant",
                    ),
                ),
            ],
            options={
                "db_table": "operation_analysis_screen_display_session",
            },
        ),
    ]
