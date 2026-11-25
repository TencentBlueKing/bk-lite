import django.db.models.deletion
from django.db import migrations, models


def disable_legacy_presets(apps, schema_editor):
    Workflow = apps.get_model("itsm", "Workflow")
    Service = apps.get_model("itsm", "Service")
    db = schema_editor.connection.alias
    presets = (
        Workflow.objects.using(db)
        .filter(
            domain="domain.com",
            key__in=["itsm_request", "itsm_incident", "itsm_problem"],
            current_version__version_no=1,
            current_version__created_by="system",
        )
        .values_list("pk", "current_version__design")
    )
    for workflow_id, design in presets:
        handlers = {node["id"]: node.get("assignee") for node in design.get("nodes", [])}
        if handlers.get("approve") == {"source": "users", "value": ["alice", "bob"]} and handlers.get("handle") == {
            "source": "users",
            "value": ["handler"],
        }:
            Service.objects.using(db).filter(workflow_id=workflow_id).update(is_enabled=False)


class Migration(migrations.Migration):
    dependencies = [("itsm", "0028_ticket_start_attempt")]
    operations = [
        migrations.AddField(
            model_name="service",
            name="handler_group",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="assigned_services", to="itsm.handlergroup"
            ),
        ),
        migrations.RunPython(disable_legacy_presets, migrations.RunPython.noop),
    ]
