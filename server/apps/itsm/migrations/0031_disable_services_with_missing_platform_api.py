from django.db import migrations


def _fields(fields):
    for field in fields:
        yield field
        yield from _fields(field.get("children") or [])


def _missing_platform_api(design, registry):
    schema = (design or {}).get("form_schema") or {}
    for field in _fields(schema.get("fields") or []):
        fetch = field.get("fetch") or {}
        snapshot = fetch.get("snapshot") or {}
        config = snapshot.get("config") or {}
        if snapshot.get("kind") != "api" or config.get("transport") == "external":
            continue
        service, separator, path = str(config.get("path") or "").strip("/").partition("/")
        method = str(config.get("method") or "GET").upper()
        if not separator or not registry.find(service, path, method):
            return True
    return False


def disable_services_with_missing_platform_api(apps, schema_editor):
    from apps.core.openapi.registry import default_registry

    Service = apps.get_model("itsm", "Service")
    for service in Service.objects.using(schema_editor.connection.alias).filter(is_enabled=True).select_related("workflow__current_version"):
        version = service.workflow.current_version
        if version and _missing_platform_api(version.design, default_registry):
            Service.objects.using(schema_editor.connection.alias).filter(pk=service.pk).update(is_enabled=False)


class Migration(migrations.Migration):
    dependencies = [("itsm", "0030_disable_unsupported_auto_actions")]
    operations = [migrations.RunPython(disable_services_with_missing_platform_api, migrations.RunPython.noop)]
