import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("itsm", "0031_disable_services_with_missing_platform_api")]

    operations = [
        migrations.CreateModel(
            name="TicketFormTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("team", models.JSONField(default=list)),
                ("username", models.CharField(max_length=64)),
                ("name", models.CharField(max_length=100)),
                ("form_data", models.JSONField(default=dict)),
                (
                    "workflow",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ticket_form_templates", to="itsm.workflow"),
                ),
            ],
            options={
                "db_table": "itsm_ticket_form_template",
                "indexes": [models.Index(fields=["domain", "username", "workflow"], name="itsm_formtpl_owner_idx")],
            },
        ),
    ]
