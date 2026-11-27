from django.db import migrations

SUPPORTED_ACTIONS = {"table", "http", "integration", "job", "workflow", "cmdb", "job_template"}


def disable_unsupported_auto_actions(apps, schema_editor):
    Service = apps.get_model("itsm", "Service")
    for service in Service.objects.using(schema_editor.connection.alias).filter(is_enabled=True).select_related("workflow__current_version"):
        version = service.workflow.current_version
        if version is None:
            continue
        nodes = (version.design or {}).get("nodes", [])
        if any(
            node.get("type") in {"auto", "manual_trigger", "rule_trigger"} and (node.get("auto") or {}).get("kind") not in SUPPORTED_ACTIONS
            for node in nodes
        ):
            Service.objects.using(schema_editor.connection.alias).filter(pk=service.pk).update(is_enabled=False)


class Migration(migrations.Migration):
    dependencies = [("itsm", "0029_service_handler_group")]
    operations = [migrations.RunPython(disable_unsupported_auto_actions, migrations.RunPython.noop)]
