from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0030_clear_default_only_builtin_datasource_groups"),
    ]

    operations = [
        migrations.CreateModel(
            name="CanvasDraftCheckpoint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("resource_type", models.CharField(max_length=32)),
                ("resource_id", models.PositiveIntegerField()),
                ("username", models.CharField(max_length=255)),
                ("label", models.CharField(blank=True, default="", max_length=30)),
                ("payload", models.JSONField(default=dict)),
            ],
            options={
                "db_table": "operation_analysis_canvas_draft_checkpoint",
            },
        ),
        migrations.AddIndex(
            model_name="canvasdraftcheckpoint",
            index=models.Index(
                fields=["resource_type", "resource_id", "username", "id"],
                name="idx_canvas_draft_ckpt_owner",
            ),
        ),
    ]
