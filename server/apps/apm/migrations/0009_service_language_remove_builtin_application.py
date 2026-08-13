from django.db import migrations, models


def remove_builtin_application(apps, schema_editor):
    alias = schema_editor.connection.alias
    ApmApplication = apps.get_model("apm", "ApmApplication")
    ApmService = apps.get_model("apm", "ApmService")

    builtin_ids = list(
        ApmApplication.objects.using(alias).filter(is_builtin=True).values_list("id", flat=True)
    )
    if builtin_ids:
        ApmService.objects.using(alias).filter(application_id__in=builtin_ids).update(application_id=None)
        ApmApplication.objects.using(alias).filter(id__in=builtin_ids).delete()
    ApmService.objects.using(alias).filter(archive_reason="silent_timeout").update(
        archived_at=None,
        archive_reason="",
    )


class Migration(migrations.Migration):
    dependencies = [("apm", "0008_cross_database_outbox_guard")]

    operations = [
        migrations.AddField(
            model_name="apmservice",
            name="language",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.RunPython(remove_builtin_application, migrations.RunPython.noop),
    ]
