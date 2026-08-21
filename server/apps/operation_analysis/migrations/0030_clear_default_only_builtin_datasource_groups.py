from django.db import migrations


def forwards(apps, schema_editor):
    DataSource = apps.get_model("operation_analysis", "DataSourceAPIModel")
    Group = apps.get_model("system_mgmt", "Group")
    default = Group.objects.filter(name="Default", parent_id=0).first()
    default_id = default.id if default else None
    for datasource in DataSource.objects.filter(is_build_in=True).iterator():
        groups = datasource.groups or []
        if not groups or (default_id is not None and list(groups) == [default_id]):
            datasource.groups = []
            datasource.save(update_fields=["groups"])


def backwards(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0029_report_refresh_interval"),
        ("system_mgmt", "0003_initial"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
