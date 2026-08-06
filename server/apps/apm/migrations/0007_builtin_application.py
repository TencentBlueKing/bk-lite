from django.db import migrations, models


BUILTIN_APPLICATION_NAME = "未归类应用"
BUILTIN_APPLICATION_DESCRIPTION = "未设置 service.namespace 的服务"


def create_builtin_application(apps, schema_editor):
    Application = apps.get_model("apm", "ApmApplication")
    ApplicationOrganization = apps.get_model("apm", "ApmApplicationOrganization")
    Service = apps.get_model("apm", "ApmService")

    application, _ = Application.objects.get_or_create(
        application_id="",
        defaults={
            "name": BUILTIN_APPLICATION_NAME,
            "description": BUILTIN_APPLICATION_DESCRIPTION,
            "is_enabled": True,
            "is_builtin": True,
            "created_by": "migration",
            "updated_by": "migration",
        },
    )
    application.name = BUILTIN_APPLICATION_NAME
    application.description = BUILTIN_APPLICATION_DESCRIPTION
    application.is_builtin = True
    application.updated_by = "migration"
    application.save(update_fields=("name", "description", "is_builtin", "updated_by", "updated_at"))

    organization_ids = set(ApplicationOrganization.objects.values_list("organization", flat=True))
    for service in Service.objects.filter(normalized_namespace="").iterator():
        organization_ids.update(service.organization_links.values_list("organization", flat=True))
    ApplicationOrganization.objects.bulk_create(
        [
            ApplicationOrganization(
                application=application,
                organization=organization_id,
                created_by="migration",
                updated_by="migration",
            )
            for organization_id in sorted(organization_ids)
        ],
        ignore_conflicts=True,
    )
    Service.objects.filter(normalized_namespace="").update(application=application)


class Migration(migrations.Migration):
    dependencies = [("apm", "0006_application_integration")]

    operations = [
        migrations.AddField(
            model_name="apmapplication",
            name="is_builtin",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.RunPython(create_builtin_application, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="apmapplication",
            name="is_enabled",
        ),
    ]
