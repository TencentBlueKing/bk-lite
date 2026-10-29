from django.db import migrations, models


def seed_builtin_required_apps(apps, schema_editor):
    model = apps.get_model("operation_analysis", "DataSourceAPIModel")
    from apps.operation_analysis.services.datasource_required_app import resolve_or_seed_required_app

    for row in model.objects.filter(is_build_in=True).iterator():
        required_app = resolve_or_seed_required_app(
            rest_api=row.rest_api or "",
            source_type=row.source_type,
            is_build_in=True,
        )
        if row.required_app != required_app:
            model.objects.filter(pk=row.pk).update(required_app=required_app)


def clear_builtin_required_apps(apps, schema_editor):
    model = apps.get_model("operation_analysis", "DataSourceAPIModel")
    model.objects.update(required_app=None)


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0037_excel_processing_started_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="datasourceapimodel",
            name="required_app",
            field=models.CharField(blank=True, max_length=64, null=True, verbose_name="模块许可"),
        ),
        migrations.RunPython(seed_builtin_required_apps, clear_builtin_required_apps),
    ]
