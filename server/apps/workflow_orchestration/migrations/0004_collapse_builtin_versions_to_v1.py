from django.db import migrations


def collapse_builtin_versions(apps, schema_editor):
    from apps.workflow_orchestration.services.builtin_workflows import collapse_builtin_workflow_versions

    collapse_builtin_workflow_versions(
        workflow_model=apps.get_model("workflow_orchestration", "Workflow"),
        version_model=apps.get_model("workflow_orchestration", "WorkflowVersion"),
        execution_model=apps.get_model("workflow_orchestration", "WorkflowExecution"),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("workflow_orchestration", "0003_workflowexecution_unknown_status"),
    ]

    operations = [
        migrations.RunPython(collapse_builtin_versions, migrations.RunPython.noop),
    ]
