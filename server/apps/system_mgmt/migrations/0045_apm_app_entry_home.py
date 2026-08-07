from django.db import migrations

LEGACY_APM_ENTRY_URLS = ("/apm", "/apm/", "/apm/services", "/apm/services/")
TARGET_APM_ENTRY_URL = "/apm/home"


def forward_apm_entry_home(apps, schema_editor):
    App = apps.get_model("system_mgmt", "App")
    App.objects.filter(name="apm", url__in=LEGACY_APM_ENTRY_URLS).update(url=TARGET_APM_ENTRY_URL)


def reverse_apm_entry_home(apps, schema_editor):
    App = apps.get_model("system_mgmt", "App")
    App.objects.filter(name="apm", url=TARGET_APM_ENTRY_URL).update(url="/apm")


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0044_remove_builtin_webhook_domains"),
    ]

    operations = [
        migrations.RunPython(forward_apm_entry_home, reverse_apm_entry_home),
    ]
