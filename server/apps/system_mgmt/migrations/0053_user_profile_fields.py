import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0052_credential_secret_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="employment_status",
            field=models.CharField(
                choices=[
                    ("unspecified", "未设置"),
                    ("employed", "在职"),
                    ("resigned", "离职"),
                ],
                db_index=True,
                default="unspecified",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="job_title",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="user",
            name="job_level",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="user",
            name="employee_no",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="user",
            name="account_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="manager",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="direct_reports",
                to="system_mgmt.user",
            ),
        ),
        migrations.CreateModel(
            name="UserFieldDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64)),
                ("key", models.CharField(max_length=64, unique=True)),
                ("field_type", models.CharField(choices=[("text", "文本"), ("number", "数字"), ("date", "日期")], max_length=16)),
                ("description", models.TextField(blank=True, default="")),
                ("is_enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="UserFieldValue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("value", models.CharField(blank=True, default="", max_length=255)),
                (
                    "field",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="values",
                        to="system_mgmt.userfielddefinition",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="field_values",
                        to="system_mgmt.user",
                    ),
                ),
            ],
            options={"unique_together": {("user", "field")}},
        ),
    ]
