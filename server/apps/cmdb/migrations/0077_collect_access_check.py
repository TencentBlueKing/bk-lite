import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0076_owner_handover_field"),
    ]

    operations = [
        migrations.CreateModel(
            name="CollectAccessCheck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(max_length=16)),
                ("total_count", models.PositiveIntegerField(default=0)),
                ("finished_count", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField()),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("operator", models.CharField(blank=True, default="", max_length=150)),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                (
                    "task",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access_check",
                        to="cmdb.collectmodels",
                    ),
                ),
            ],
            options={"db_table": "cmdb_collect_access_check"},
        ),
        migrations.CreateModel(
            name="CollectAccessCheckRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField()),
                ("target", models.CharField(max_length=255)),
                ("credential_id", models.CharField(blank=True, default="", max_length=64)),
                ("credential_name", models.CharField(blank=True, default="", max_length=255)),
                ("conclusion", models.CharField(max_length=32)),
                ("detail_code", models.CharField(blank=True, default="", max_length=64)),
                ("attempted", models.BooleanField(default=False)),
                (
                    "access_check",
                    models.ForeignKey(
                        db_column="check_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rows",
                        to="cmdb.collectaccesscheck",
                    ),
                ),
            ],
            options={"db_table": "cmdb_collect_access_check_row"},
        ),
        migrations.AddConstraint(
            model_name="collectaccesscheckrow",
            constraint=models.UniqueConstraint(
                fields=("access_check", "target", "credential_id"),
                name="cmdb_collect_access_check_row_uniq",
            ),
        ),
    ]
